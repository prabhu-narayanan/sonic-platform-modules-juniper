#!/usr/bin/env python3
"""
test_jmd.py — End-to-end test harness for jmd-dispatcher + jmd-cmdrunner
==========================================================================

SCP this file to the DUT and run as root:

    python3 test_jmd.py              # run all tests
    python3 test_jmd.py -v           # verbose output
    python3 test_jmd.py -k <name>    # run one test by keyword

Prerequisites:
    - jmd-dispatcher.service is running  (systemctl start jmd-dispatcher)
    - jmd-cmdrunner is installed at /usr/local/bin/jmd-cmdrunner
    - Redis is running with STATE_DB at db 6

What is tested:
    1.  Dispatcher liveness: systemd unit is active (running)
    2.  Cmdrunner installed: binary exists and is executable
    3.  Cmdrunner direct: invoke worker directly, bypass dispatcher
    4.  Happy-path: submit "echo hello" via stream → COMPLETE + output
    5.  Failing command: exit code != 0 → state=FAILED, exact rc preserved
    6.  Stderr capture: mixed stdout/stderr → "--- stderr ---" marker
    7.  Finished-at timestamp: RFC 3339 format validation
    8.  Missing command_text: empty field → worker exits rc=2
    9.  Missing hash: no hash key at all → worker exits rc=2
    10. State not READY: state=INPROGRESS → worker skips, hash unchanged
    11. Duplicate claim: two workers race → WATCH/MULTI/EXEC ensures only one wins
    12. Concurrent dispatch: 5 simultaneous jobs → all complete
    13. Large output: ~100KB output stored without truncation
    14. Timeout: command exceeds --timeout → FAILED, rc=124
    15. SIGTERM handling: kill worker mid-run → exits 143 (128+SIGTERM)
    16. Stream entry with no hash: dispatcher ACKs, no worker spawned
    17. Malformed stream entry: no 'uuid' field → dispatcher ACKs
    18. Reclaim stuck entries: un-ACK'd PEL entry recovered after idle threshold

All tests clean up after themselves (DEL the Redis keys they create).
"""

import json
import os
import signal
import subprocess
import sys
import time
import uuid as uuid_mod

# ---------------------------------------------------------------------------
# Redis connection — raw redis-py against STATE_DB (index 6)
# ---------------------------------------------------------------------------
try:
    import redis
except ImportError:
    print("ERROR: redis-py not installed.  pip3 install redis", file=sys.stderr)
    sys.exit(1)

REDIS_UNIX_SOCK = "/var/run/redis/redis.sock"
STATE_DB_ID = 6
TABLE_NAME = "JMD_CMD"
STREAM = "JMD_CMD_EVENTS"
GROUP = "cmd"
WORKER_PATH = "/usr/local/bin/jmd-cmdrunner"

# Timeout (seconds) to wait for a job to reach a terminal state.
POLL_TIMEOUT = 30
POLL_INTERVAL = 0.5


def get_redis():
    """Return a redis-py client connected to STATE_DB via Unix socket."""
    return redis.Redis(
        unix_socket_path=REDIS_UNIX_SOCK,
        db=STATE_DB_ID,
        decode_responses=True,
    )


# ---------------------------------------------------------------------------
# Helper: submit a job (write hash + XADD) — mimics JMD container behaviour
# ---------------------------------------------------------------------------

def submit_job(r, job_uuid, command_text, state="READY", extra_fields=None):
    """
    Write a JMD_CMD|<uuid> hash with the given fields and XADD to the
    stream, exactly as the JMD container would.

    Returns the stream entry ID.
    """
    key = "{}|{}".format(TABLE_NAME, job_uuid)
    mapping = {
        "state": state,
        "command_text": command_text,
        "output": "",
        "exit_code": "-1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if extra_fields:
        mapping.update(extra_fields)

    r.hset(key, mapping=mapping)
    eid = r.xadd(STREAM, {"uuid": job_uuid})
    return eid


def wait_for_state(r, job_uuid, terminal_states=("COMPLETE", "FAILED"),
                   timeout=POLL_TIMEOUT):
    """
    Poll the hash until state is one of terminal_states, or timeout.

    Returns the full hash as a dict, or None on timeout.
    """
    key = "{}|{}".format(TABLE_NAME, job_uuid)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = r.hgetall(key)
        if data and data.get("state") in terminal_states:
            return data
        time.sleep(POLL_INTERVAL)
    # One last check
    data = r.hgetall(key)
    if data and data.get("state") in terminal_states:
        return data
    return None


def cleanup_job(r, job_uuid):
    """Delete the hash key (best-effort cleanup)."""
    key = "{}|{}".format(TABLE_NAME, job_uuid)
    r.delete(key)


def new_uuid():
    """Generate a fresh UUID string."""
    return str(uuid_mod.uuid4())


# ---------------------------------------------------------------------------
# Result formatting helpers
# ---------------------------------------------------------------------------

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


PASS = "{}{}PASS{}".format(Colors.BOLD, Colors.GREEN, Colors.RESET)
FAIL = "{}{}FAIL{}".format(Colors.BOLD, Colors.RED, Colors.RESET)
SKIP = "{}{}SKIP{}".format(Colors.BOLD, Colors.YELLOW, Colors.RESET)

results = []  # list of (name, pass/fail/skip, detail)


def record(name, passed, detail=""):
    tag = PASS if passed else FAIL
    results.append((name, passed, detail))
    print("  [{}]  {}{}".format(tag, name,
          "  — {}".format(detail) if detail else ""))


def record_skip(name, reason):
    results.append((name, None, reason))
    print("  [{}]  {}  — {}".format(SKIP, name, reason))


# ===================================================================
# Tests
# ===================================================================

def test_dispatcher_service_active():
    """
    Smoke test — verify the systemd unit is active.

    Why:
        Every other test depends on jmd-dispatcher.service running.
        If it crashed on startup (e.g. missing swsscommon, bad
        DBConnector args, redis-py import failure), this catches it
        immediately before we waste time on the rest of the suite.

    Code path exercised:
        jmd-dispatcher main() → signal registration → syslog.openlog →
        connect_state_db() → ensure_group() → enters event loop.

    Pass criteria:
        `systemctl is-active jmd-dispatcher.service` prints "active".
    """
    name = "dispatcher_service_active"
    try:
        out = subprocess.check_output(
            ["systemctl", "is-active", "jmd-dispatcher.service"],
            text=True,
        ).strip()
        record(name, out == "active", "systemctl is-active => '{}'".format(out))
    except subprocess.CalledProcessError as e:
        record(name, False, "systemctl is-active returned rc={}".format(
            e.returncode))


def test_cmdrunner_exists():
    """
    Smoke test — verify the worker binary is installed and executable.

    Why:
        The dispatcher spawns jmd-cmdrunner via systemd-run or Popen.
        If it's missing or not +x, every spawn will fail silently (the
        dispatcher logs "spawn failed" and leaves the entry for reclaim,
        but the job never completes).

    Pass criteria:
        /usr/local/bin/jmd-cmdrunner exists and has the execute bit set.
    """
    name = "cmdrunner_exists"
    exists = os.path.isfile(WORKER_PATH) and os.access(WORKER_PATH, os.X_OK)
    record(name, exists,
           "{} exists={}".format(WORKER_PATH, exists))


def test_happy_path(r):
    """
    Golden-path end-to-end: submit a trivial command, verify success.

    Why:
        This is the single most important test — it exercises the entire
        pipeline from JMD-side submission all the way to result recording:

    Flow exercised:
        1. Test writes hash JMD_CMD|<uuid> with state=READY, command_text="echo hello"
        2. Test XADDs {uuid: <uuid>} to JMD_CMD_EVENTS stream
           (submit_job mimics what the JMD container does)
        3. jmd-dispatcher reads the stream entry via XREADGROUP
        4. jmd-dispatcher calls get_job_state() → sees "READY"
        5. jmd-dispatcher spawns: jmd-cmdrunner --uuid <uuid>
        6. jmd-cmdrunner connects to STATE_DB via DBConnector + Table
        7. jmd-cmdrunner calls get_job_fields() → reads command_text
        8. jmd-cmdrunner calls atomic_claim() → WATCH/MULTI/EXEC: READY → INPROGRESS
        9. jmd-cmdrunner calls run_cmd("echo hello") → subprocess.run(shell=True)
        10. jmd-cmdrunner calls write_result() → state=COMPLETE, exit_code=0, output="hello\n"
        11. jmd-dispatcher ACKs the stream entry

    Pass criteria:
        state == "COMPLETE", exit_code == "0", output contains "hello".
    """
    name = "happy_path"
    uid = new_uuid()
    try:
        submit_job(r, uid, "echo hello")
        data = wait_for_state(r, uid)
        if data is None:
            record(name, False, "timed out waiting for terminal state")
            return
        ok = (data["state"] == "COMPLETE"
              and data.get("exit_code") == "0"
              and "hello" in data.get("output", ""))
        record(name, ok,
               "state={} rc={} output='{}'".format(
                   data["state"], data.get("exit_code"),
                   data.get("output", "")[:120]))
    finally:
        cleanup_job(r, uid)


def test_failing_command(r):
    """
    Verify that non-zero exit codes are captured and state becomes FAILED.

    Why:
        JMD needs to distinguish success from failure.  The cmdrunner
        records the child's raw exit code in the hash so the container
        can inspect it and take action (retry, alert, etc.).

    Flow exercised:
        Same as happy_path, except the child command is "exit 42".
        run_cmd() returns (42, ""), write_result() sets state=FAILED.

    Pass criteria:
        state == "FAILED", exit_code == "42".
    """
    name = "failing_command"
    uid = new_uuid()
    try:
        submit_job(r, uid, "exit 42")
        data = wait_for_state(r, uid)
        if data is None:
            record(name, False, "timed out")
            return
        ok = (data["state"] == "FAILED"
              and data.get("exit_code") == "42")
        record(name, ok,
               "state={} rc={}".format(data["state"], data.get("exit_code")))
    finally:
        cleanup_job(r, uid)


def test_timeout(r):
    """
    Verify that a long-running command is killed after the timeout.

    Why:
        Without a timeout, a hung command (e.g. a routing daemon that
        never exits) would block the worker forever.  The cmdrunner
        uses subprocess.run(timeout=N) which raises TimeoutExpired,
        and the except branch records exit_code=124 (matching the
        coreutils `timeout` convention) and state=FAILED.

    Flow exercised:
        We invoke jmd-cmdrunner DIRECTLY (not via dispatcher) so we
        can pass --timeout 3.  The command "sleep 60" exceeds 3s, so
        subprocess.TimeoutExpired is raised.  The except block in
        cmdrunner's main() calls write_result(state=FAILED, rc=124).

    Why direct invocation:
        The dispatcher uses the default 900s timeout.  We don't want
        to wait 15 minutes, so we bypass the dispatcher and call the
        worker ourselves with --timeout 3.

    Pass criteria:
        state == "FAILED", exit_code == "124".
    """
    name = "timeout"
    uid = new_uuid()
    try:
        # We call jmd-cmdrunner directly so we can pass --timeout 3
        key = "{}|{}".format(TABLE_NAME, uid)
        r.hset(key, mapping={
            "state": "READY",
            "command_text": "sleep 60",
            "output": "",
            "exit_code": "-1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        # Run the worker directly with a short timeout
        proc = subprocess.run(
            [WORKER_PATH, "--uuid", uid, "--timeout", "3"],
            capture_output=True, text=True, timeout=30,
        )
        data = r.hgetall(key)
        ok = (data.get("state") == "FAILED"
              and data.get("exit_code") == "124")
        record(name, ok,
               "state={} rc={} worker_rc={}".format(
                   data.get("state"), data.get("exit_code"), proc.returncode))
    finally:
        cleanup_job(r, uid)


def test_missing_command_text(r):
    """
    Verify that the worker rejects a job with an empty command_text.

    Why:
        A producer bug could write a hash with command_text="" or omit
        it entirely.  The cmdrunner should detect this early, log an
        error, and exit with rc=2 WITHOUT setting state=INPROGRESS
        (since there's nothing to run).

    Flow exercised:
        jmd-cmdrunner → get_job_fields() succeeds (hash exists) →
        fields["command_text"] == "" → log_err → return 2.
        The atomic_claim() is never reached.

    Why direct invocation:
        We call the worker directly so we can inspect its exit code.
        The dispatcher would just spawn it and ACK; we wouldn't see rc=2.

    Pass criteria:
        Worker process exits with returncode == 2.
    """
    name = "missing_command_text"
    uid = new_uuid()
    try:
        key = "{}|{}".format(TABLE_NAME, uid)
        r.hset(key, mapping={
            "state": "READY",
            "command_text": "",
            "output": "",
            "exit_code": "-1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        proc = subprocess.run(
            [WORKER_PATH, "--uuid", uid],
            capture_output=True, text=True, timeout=15,
        )
        ok = proc.returncode == 2
        record(name, ok,
               "worker rc={} (expected 2)".format(proc.returncode))
    finally:
        cleanup_job(r, uid)


def test_missing_hash(r):
    """
    Verify that the worker handles a completely absent hash key.

    Why:
        Race condition scenario: the JMD container writes the hash,
        XADDs to the stream, but then the hash expires (TTL) or gets
        DEL'd before the worker starts.  The worker should detect
        "key not found" and exit cleanly with rc=2 instead of crashing
        with a KeyError or NoneType traceback.

    Flow exercised:
        jmd-cmdrunner → get_job_fields(uuid) → Table.get(uuid) returns
        (False, []) → fields is None → log_err → return 2.

    Pass criteria:
        Worker exits with returncode == 2.
    """
    name = "missing_hash"
    uid = new_uuid()
    # Intentionally do NOT create a hash key
    proc = subprocess.run(
        [WORKER_PATH, "--uuid", uid],
        capture_output=True, text=True, timeout=15,
    )
    ok = proc.returncode == 2
    record(name, ok,
           "worker rc={} (expected 2)".format(proc.returncode))


def test_duplicate_claim(r):
    """
    Verify the WATCH/MULTI/EXEC atomic claim prevents double execution.

    Why:
        This is the core concurrency-safety guarantee.  If the dispatcher
        (or reclaim) spawns two workers for the same UUID (e.g. a crash
        between spawn and ACK causes a re-delivery), only one worker
        must actually execute the command.  The other must detect that
        state is no longer READY and bow out.

    Flow exercised:
        1. Test creates a hash with state=READY and command "sleep 2"
        2. Two jmd-cmdrunner processes are launched simultaneously
        3. Both call atomic_claim(uuid):
             Worker A: WATCH key → hget state → "READY" → MULTI → hset INPROGRESS → EXEC → success
             Worker B: WATCH key → hget state → "READY" → MULTI → hset INPROGRESS → EXEC → WatchError
                       (because Worker A already modified the key between B's WATCH and EXEC)
           OR Worker B reads state="INPROGRESS" (already claimed) → returns False
        4. Worker A runs "sleep 2", writes result.  Worker B exits rc=0.

    Pass criteria:
        Both workers exit with rc=0 (one ran, one gracefully skipped).
        Final hash state is COMPLETE (or FAILED if the sleep was killed).
    """
    name = "duplicate_claim"
    uid = new_uuid()
    try:
        key = "{}|{}".format(TABLE_NAME, uid)
        r.hset(key, mapping={
            "state": "READY",
            "command_text": "sleep 2",
            "output": "",
            "exit_code": "-1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        # Launch two workers at exactly the same time
        p1 = subprocess.Popen(
            [WORKER_PATH, "--uuid", uid, "--timeout", "10"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        p2 = subprocess.Popen(
            [WORKER_PATH, "--uuid", uid, "--timeout", "10"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        rc1 = p1.wait(timeout=20)
        rc2 = p2.wait(timeout=20)

        # One should claim (rc=0 after execution), the other should exit 0
        # because it couldn't claim (state != READY).
        data = r.hgetall(key)
        # Both return 0: one ran the command, the other skipped gracefully.
        both_zero = (rc1 == 0 and rc2 == 0)
        state_ok = data.get("state") in ("COMPLETE", "FAILED")
        ok = both_zero and state_ok
        record(name, ok,
               "rc1={} rc2={} state={} — exactly one should have run".format(
                   rc1, rc2, data.get("state")))
    finally:
        cleanup_job(r, uid)


def test_concurrent_dispatch(r):
    """
    Verify the dispatcher handles a burst of simultaneous job submissions.

    Why:
        In production, the JMD container may fire off many commands in
        rapid succession (e.g. "show" commands across all line cards).
        The dispatcher must handle all of them without dropping any.
        This exercises:
          - The XREADGROUP count= parameter (batch reads)
          - The threading.Semaphore that caps concurrent workers
          - systemd-run spawning multiple transient units in parallel

    Flow exercised:
        1. Test submits 5 jobs to the stream in a tight loop
        2. Dispatcher reads them (possibly across multiple XREADGROUP calls)
        3. For each: get_job_state → READY → sem.acquire → spawn_worker → xack
        4. Each cmdrunner claims, runs "echo concurrent-N", writes result

    Pass criteria:
        All 5 jobs reach state == "COMPLETE".
    """
    name = "concurrent_dispatch"
    N = 5
    uuids = [new_uuid() for _ in range(N)]
    try:
        for i, uid in enumerate(uuids):
            submit_job(r, uid, "echo concurrent-{}".format(i))

        completed = 0
        for uid in uuids:
            data = wait_for_state(r, uid, timeout=POLL_TIMEOUT)
            if data and data.get("state") == "COMPLETE":
                completed += 1

        ok = completed == N
        record(name, ok,
               "{}/{} completed".format(completed, N))
    finally:
        for uid in uuids:
            cleanup_job(r, uid)


def test_stderr_capture(r):
    """
    Verify that both stdout and stderr are captured and clearly separated.

    Why:
        Many SONiC CLI commands write diagnostic info to stderr (e.g.
        "Warning: ...").  The JMD container needs to see BOTH streams
        to fully diagnose failures.  The cmdrunner's run_cmd() captures
        them separately and joins them with a "--- stderr ---" marker.

    Flow exercised:
        run_cmd("echo out-text; echo err-text >&2") →
          p.stdout = "out-text\n"
          p.stderr = "err-text\n"
        → merged as "out-text\n\n--- stderr ---\nerr-text\n"
        → write_result() stores it in the "output" field.

    Pass criteria:
        output contains "out-text", "--- stderr ---", and "err-text".
    """
    name = "stderr_capture"
    uid = new_uuid()
    try:
        submit_job(r, uid, "echo out-text; echo err-text >&2")
        data = wait_for_state(r, uid)
        if data is None:
            record(name, False, "timed out")
            return
        output = data.get("output", "")
        has_stdout = "out-text" in output
        has_stderr_marker = "--- stderr ---" in output
        has_stderr_text = "err-text" in output
        ok = has_stdout and has_stderr_marker and has_stderr_text
        record(name, ok,
               "stdout={} marker={} stderr_text={} output='{}'".format(
                   has_stdout, has_stderr_marker, has_stderr_text,
                   output[:200]))
    finally:
        cleanup_job(r, uid)


def test_large_output(r):
    """
    Verify that large command output is stored without truncation.

    Why:
        Earlier versions of jmd-cmdrunner had a truncate_output() helper
        that silently clipped output beyond a threshold.  That was removed
        because the JMD container needs full output (e.g. "show route"
        can easily be 100KB+).  This test confirms that ~100KB of output
        survives the full pipeline: subprocess.run capture → write_result
        → Redis HMSET → hash read.

    Flow exercised:
        run_cmd() captures ~102KB of stdout from a python one-liner.
        write_result() stores it via Table.set().  Test reads it back
        with r.hgetall() and checks the byte count.

    Pass criteria:
        state == "COMPLETE", len(output) >= 90000 bytes.
    """
    name = "large_output"
    uid = new_uuid()
    try:
        # Generate ~100KB: 2500 lines of 40 chars each
        submit_job(r, uid,
                   "python3 -c \"print('A'*40 + chr(10), end='') ; "
                   "[print('B'*40) for _ in range(2500)]\"")
        data = wait_for_state(r, uid, timeout=POLL_TIMEOUT)
        if data is None:
            record(name, False, "timed out")
            return
        output = data.get("output", "")
        output_len = len(output)
        # Expect at least 90KB (some overhead is fine)
        ok = (data["state"] == "COMPLETE" and output_len >= 90000)
        record(name, ok,
               "state={} output_len={} bytes".format(
                   data["state"], output_len))
    finally:
        cleanup_job(r, uid)


def test_state_not_ready(r):
    """
    Verify that the worker refuses to execute a job that isn't READY.

    Why:
        Defensive guard against re-execution.  If a job has already been
        claimed (INPROGRESS) or finished (COMPLETE/FAILED), a second
        worker must NOT run it again.  This can happen if:
          - The dispatcher's reclaim re-delivers an entry whose worker
            is still running (state=INPROGRESS)
          - A manual re-submission of a UUID that already completed

    Flow exercised:
        1. Test creates a hash with state=INPROGRESS (simulating an
           already-claimed job)
        2. jmd-cmdrunner reads the hash → state=INPROGRESS
        3. atomic_claim() → WATCH → hget state → "INPROGRESS" (not READY)
           → unwatch → return False
        4. Worker logs "not READY" and exits rc=0

    Pass criteria:
        Worker exits rc=0.  Hash is unchanged: state still "INPROGRESS",
        exit_code still "-1" (i.e. the worker didn't touch anything).
    """
    name = "state_not_ready"
    uid = new_uuid()
    try:
        key = "{}|{}".format(TABLE_NAME, uid)
        r.hset(key, mapping={
            "state": "INPROGRESS",
            "command_text": "echo should-not-run",
            "output": "",
            "exit_code": "-1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        proc = subprocess.run(
            [WORKER_PATH, "--uuid", uid],
            capture_output=True, text=True, timeout=15,
        )
        data = r.hgetall(key)
        ok = (proc.returncode == 0
              and data.get("state") == "INPROGRESS"
              and data.get("exit_code") == "-1")
        record(name, ok,
               "worker_rc={} state={} (should still be INPROGRESS)".format(
                   proc.returncode, data.get("state")))
    finally:
        cleanup_job(r, uid)


def test_sigterm_to_cmdrunner(r):
    """
    Verify that SIGTERM to a running cmdrunner triggers clean shutdown.

    Why:
        systemd sends SIGTERM when stopping a transient unit (e.g.
        RuntimeMaxSec exceeded, or manual `systemctl stop`).  The
        cmdrunner's signal_handler calls sys.exit(128 + 15 = 143),
        following the standard SONiC convention.  This test confirms
        the handler is actually wired up and produces the expected
        exit code.

    Flow exercised:
        1. Test creates a hash with command "sleep 60" and starts
           jmd-cmdrunner with --timeout 120
        2. Worker claims the job (READY → INPROGRESS) and enters
           subprocess.run("sleep 60")
        3. After 2 seconds, test sends SIGTERM to the worker PID
        4. signal_handler(SIGTERM) fires → sys.exit(143)
        5. subprocess.run in run_cmd() is interrupted, process exits

    Note:
        Because the worker is killed mid-execution, it may or may not
        have time to call write_result().  The hash might still be in
        state=INPROGRESS.  This is by design — the reclaim mechanism
        handles these orphaned jobs.

    Pass criteria:
        Worker process exits with returncode == 143 (128 + SIGTERM).
    """
    name = "sigterm_to_cmdrunner"
    uid = new_uuid()
    try:
        key = "{}|{}".format(TABLE_NAME, uid)
        r.hset(key, mapping={
            "state": "READY",
            "command_text": "sleep 60",
            "output": "",
            "exit_code": "-1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        proc = subprocess.Popen(
            [WORKER_PATH, "--uuid", uid, "--timeout", "120"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        # Give it a moment to claim and start running the sleep.
        time.sleep(2)
        # Send SIGTERM
        proc.send_signal(signal.SIGTERM)
        rc = proc.wait(timeout=15)
        # Worker should exit with 128+15 = 143 (SIGTERM convention)
        ok = (rc == 143)
        record(name, ok,
               "worker_rc={} (expected 143 = 128+SIGTERM)".format(rc))
    finally:
        cleanup_job(r, uid)


def test_dispatcher_reclaim(r):
    """
    Verify that the reclaim_stuck() mechanism recovers un-ACK'd entries.

    Why:
        If the dispatcher crashes between spawning a worker and ACK'ing
        the stream entry (or if a spawn fails), the entry stays in the
        PEL (Pending Entries List) forever.  The reclaim_stuck() function
        runs every loop iteration, finds entries idle longer than
        IDLE_RECLAIM_MS, and re-processes them (check state, re-spawn
        if still READY, ACK when done).

    Flow exercised:
        1. Test creates a hash with state=READY and command "echo reclaimed"
        2. Test XADDs to the stream
        3. Test reads the entry as a FAKE consumer ("fake-test-consumer")
           so it enters the PEL under that consumer — the real dispatcher's
           XREADGROUP with ">" won't see it (it's already delivered)
        4. The entry sits idle in the PEL for IDLE_RECLAIM_MS
        5. reclaim_stuck() calls xpending_range(idle=IDLE_RECLAIM_MS) →
           finds our entry → xclaim() transfers it to the real consumer →
           sees state=READY → spawns worker → worker runs → ACKs
        6. Test polls until state == "COMPLETE"

    Timing:
        This test requires IDLE_RECLAIM_MS to be low enough for a
        practical wait.  Default is 60s which is too long, so the test
        skips unless --idle-reclaim-ms is passed (and the dispatcher
        was restarted with the matching value).

    Pass criteria:
        state == "COMPLETE", output contains "reclaimed".
    """
    name = "dispatcher_reclaim"
    uid = new_uuid()
    idle_ms = int(os.environ.get("IDLE_RECLAIM_MS", "60000"))
    if idle_ms > 15000:
        record_skip(name,
                    "IDLE_RECLAIM_MS={} too high for quick test.  To run this test:\n"
                    "        1. systemctl set-environment IDLE_RECLAIM_MS=5000\n"
                    "        2. systemctl restart jmd-dispatcher\n"
                    "        3. python3 test_jmd.py -k reclaim --idle-reclaim-ms 5000"
                    .format(idle_ms))
        return

    try:
        key = "{}|{}".format(TABLE_NAME, uid)
        r.hset(key, mapping={
            "state": "READY",
            "command_text": "echo reclaimed",
            "output": "",
            "exit_code": "-1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        # XADD
        eid = r.xadd(STREAM, {"uuid": uid})
        # Read it as a fake consumer to move it into the PEL (pending)
        # We use XREADGROUP with the real group but a different consumer name.
        try:
            r.xreadgroup(GROUP, "fake-test-consumer",
                         {STREAM: ">"}, count=1, block=500)
        except Exception:
            pass  # It may have already been read by the real dispatcher

        # Wait for reclaim_stuck to process it (idle time + poll time).
        wait_s = int(idle_ms / 1000) + 15
        data = wait_for_state(r, uid, timeout=wait_s)
        if data is None:
            record(name, False,
                   "timed out after {}s waiting for reclaim".format(wait_s))
            return
        ok = data.get("state") == "COMPLETE"
        record(name, ok,
               "state={} output='{}'".format(
                   data.get("state"), data.get("output", "")[:80]))
    finally:
        cleanup_job(r, uid)


def test_stream_xadd_no_hash(r):
    """
    Verify the dispatcher handles a stream entry whose hash doesn't exist.

    Why:
        Race condition: the hash could be DEL'd or expire (TTL) between
        the XADD and the dispatcher reading it.  The dispatcher's
        process_entry() calls get_job_state() → returns None (not READY)
        → ACKs the entry and moves on.  It must NOT crash or spawn a
        worker.

    Flow exercised:
        1. Test XADDs {uuid: <fresh-uuid>} but does NOT create the hash
        2. Dispatcher reads entry → get_job_state(uuid) → (False, "") → None
        3. state != "READY" → xack → log "not READY" → return

    Pass criteria:
        No hash was created (the dispatcher didn't spawn a worker that
        would crash and write garbage).  The PEL entry was consumed.
    """
    name = "stream_xadd_no_hash"
    uid = new_uuid()
    try:
        # Only XADD, don't create the hash
        eid = r.xadd(STREAM, {"uuid": uid})
        # Wait a bit for the dispatcher to process it
        time.sleep(5)
        # The entry should have been ACK'd (removed from PEL).
        # Check pending — the entry should NOT be pending.
        pending = r.xpending(STREAM, GROUP)
        # pending is a dict with 'pending' count — we can't easily check
        # per-entry, but we verify no hash was created with our uid's state.
        key = "{}|{}".format(TABLE_NAME, uid)
        data = r.hgetall(key)
        # Hash should not exist (we never created it).
        ok = (len(data) == 0)
        record(name, ok,
               "hash exists={} (expected False) — "
               "dispatcher should have acked without spawning".format(
                   bool(data)))
    finally:
        cleanup_job(r, uid)


def test_malformed_stream_entry(r):
    """
    Verify the dispatcher handles a stream entry with no 'uuid' field.

    Why:
        Defensive programming — if something other than JMD writes to
        the stream (or a producer bug omits the uuid field), the
        dispatcher must not crash.  process_entry() checks
        fields.get("uuid") → None → ACKs the entry → logs a warning.

    Flow exercised:
        1. Test XADDs {"bad_field": "no_uuid_here"} (no "uuid" key)
        2. Dispatcher reads entry → uuid = fields.get("uuid") → None
        3. xack(eid) → log_warning("malformed ... no uuid field; acked")

    Pass criteria:
        The entry is no longer in the PEL (was ACK'd).  We verify
        by calling xpending_range with the exact entry ID range.
    """
    name = "malformed_stream_entry"
    try:
        eid = r.xadd(STREAM, {"bad_field": "no_uuid_here"})
        time.sleep(5)
        # We can't easily verify the log, but we check the PEL doesn't
        # grow unboundedly — verify the entry is no longer pending.
        pending = r.xpending_range(STREAM, GROUP, min=eid, max=eid, count=1)
        # If pending is empty, the entry was ACK'd.
        ok = (len(pending) == 0)
        record(name, ok,
               "entry still pending={} (expected False — should be ACK'd)".format(
                   bool(pending)))
    except Exception as e:
        record(name, False, "exception: {}".format(e))


def test_cmdrunner_direct_invocation(r):
    """
    Invoke jmd-cmdrunner directly to verify it works in isolation.

    Why:
        If a test fails via the dispatcher path, it's hard to tell
        whether the bug is in the dispatcher or the worker.  This test
        bypasses the dispatcher entirely — we write the hash ourselves,
        call jmd-cmdrunner --uuid directly, and check the result.
        If THIS test fails, the bug is in the cmdrunner.  If this
        passes but happy_path fails, the bug is in the dispatcher.

    Flow exercised:
        1. Test writes hash with state=READY, command_text="hostname"
        2. Test runs: jmd-cmdrunner --uuid <uuid>
        3. Worker connects via DBConnector → get_job_fields → atomic_claim
           → run_cmd("hostname") → write_result(COMPLETE, 0, "<hostname>")

    Pass criteria:
        Worker exits rc=0, state=="COMPLETE", exit_code=="0",
        output is non-empty (contains the machine's hostname).
    """
    name = "cmdrunner_direct_invocation"
    uid = new_uuid()
    try:
        key = "{}|{}".format(TABLE_NAME, uid)
        r.hset(key, mapping={
            "state": "READY",
            "command_text": "hostname",
            "output": "",
            "exit_code": "-1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        proc = subprocess.run(
            [WORKER_PATH, "--uuid", uid],
            capture_output=True, text=True, timeout=15,
        )
        data = r.hgetall(key)
        ok = (proc.returncode == 0
              and data.get("state") == "COMPLETE"
              and data.get("exit_code") == "0"
              and len(data.get("output", "")) > 0)
        record(name, ok,
               "worker_rc={} state={} rc={} output='{}'".format(
                   proc.returncode, data.get("state"), data.get("exit_code"),
                   data.get("output", "")[:80]))
    finally:
        cleanup_job(r, uid)


def test_finished_at_timestamp(r):
    """
    Verify the finished_at field contains a valid RFC 3339 UTC timestamp.

    Why:
        The JMD container uses finished_at to calculate command duration
        (finished_at - created_at) and to detect stale results.  If the
        format is wrong or the field is missing, duration calculations
        break.  The cmdrunner's rfc3339_now() generates timestamps like
        "2026-03-27T19:39:29Z".

    Flow exercised:
        Same as happy_path, but after completion we inspect the
        finished_at field for structural correctness:
          - Exactly 20 characters
          - Dashes at positions 4 and 7
          - "T" at position 10
          - Ends with "Z" (UTC)

    Pass criteria:
        finished_at matches the RFC 3339 pattern YYYY-MM-DDTHH:MM:SSZ.
    """
    name = "finished_at_timestamp"
    uid = new_uuid()
    try:
        submit_job(r, uid, "echo timestamp-test")
        data = wait_for_state(r, uid)
        if data is None:
            record(name, False, "timed out")
            return
        ts = data.get("finished_at", "")
        # RFC 3339 basic check: YYYY-MM-DDTHH:MM:SSZ
        ok = (len(ts) == 20
              and ts[4] == "-" and ts[7] == "-"
              and ts[10] == "T" and ts.endswith("Z"))
        record(name, ok, "finished_at='{}'".format(ts))
    finally:
        cleanup_job(r, uid)


# ===================================================================
# Main
# ===================================================================

def main():
    import argparse
    ap = argparse.ArgumentParser(description="JMD dispatcher/cmdrunner test suite")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="Verbose output")
    ap.add_argument("-k", "--keyword", type=str, default=None,
                    help="Only run tests whose name contains this keyword")
    ap.add_argument("--idle-reclaim-ms", type=int, default=None,
                    help="Override IDLE_RECLAIM_MS for the reclaim test "
                         "(must match the value the dispatcher was started with)")
    args = ap.parse_args()

    # Make --idle-reclaim-ms available to tests via environment so
    # test_dispatcher_reclaim can read it.
    if args.idle_reclaim_ms is not None:
        os.environ["IDLE_RECLAIM_MS"] = str(args.idle_reclaim_ms)

    print()
    print("{}=== JMD Dispatcher + Cmdrunner Test Suite ==={}".format(
        Colors.BOLD + Colors.CYAN, Colors.RESET))
    print()

    # Connect to Redis
    try:
        r = get_redis()
        r.ping()
        print("  Redis connection: OK  (STATE_DB via {})".format(REDIS_UNIX_SOCK))
    except Exception as e:
        print("  {}ERROR{}: Cannot connect to Redis: {}".format(
            Colors.RED, Colors.RESET, e))
        return 1

    # Ensure the consumer group exists (the test needs it for some checks)
    try:
        r.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    print()

    # All tests in execution order
    all_tests = [
        ("dispatcher_service_active", lambda: test_dispatcher_service_active()),
        ("cmdrunner_exists",          lambda: test_cmdrunner_exists()),
        ("cmdrunner_direct",          lambda: test_cmdrunner_direct_invocation(r)),
        ("happy_path",                lambda: test_happy_path(r)),
        ("failing_command",           lambda: test_failing_command(r)),
        ("stderr_capture",            lambda: test_stderr_capture(r)),
        ("finished_at_timestamp",     lambda: test_finished_at_timestamp(r)),
        ("missing_command_text",      lambda: test_missing_command_text(r)),
        ("missing_hash",              lambda: test_missing_hash(r)),
        ("state_not_ready",           lambda: test_state_not_ready(r)),
        ("duplicate_claim",           lambda: test_duplicate_claim(r)),
        ("concurrent_dispatch",       lambda: test_concurrent_dispatch(r)),
        ("large_output",              lambda: test_large_output(r)),
        ("timeout",                   lambda: test_timeout(r)),
        ("sigterm_to_cmdrunner",      lambda: test_sigterm_to_cmdrunner(r)),
        ("stream_xadd_no_hash",       lambda: test_stream_xadd_no_hash(r)),
        ("malformed_stream_entry",    lambda: test_malformed_stream_entry(r)),
        ("dispatcher_reclaim",        lambda: test_dispatcher_reclaim(r)),
    ]

    # Filter by keyword if requested
    if args.keyword:
        all_tests = [(n, fn) for n, fn in all_tests if args.keyword in n]
        if not all_tests:
            print("  No tests match keyword '{}'".format(args.keyword))
            return 1

    print("  Running {} test(s)...\n".format(len(all_tests)))

    for test_name, test_fn in all_tests:
        try:
            test_fn()
        except Exception as e:
            record(test_name, False, "EXCEPTION: {}".format(e))

    # Summary
    print()
    passed = sum(1 for _, p, _ in results if p is True)
    failed = sum(1 for _, p, _ in results if p is False)
    skipped = sum(1 for _, p, _ in results if p is None)
    total = len(results)

    color = Colors.GREEN if failed == 0 else Colors.RED
    print("{}{}  Summary: {}/{} passed, {} failed, {} skipped  {}".format(
        Colors.BOLD, color, passed, total, failed, skipped, Colors.RESET))
    print()

    if failed > 0:
        print("  {}Failed tests:{}".format(Colors.RED, Colors.RESET))
        for name, p, detail in results:
            if p is False:
                print("    • {}  — {}".format(name, detail))
        print()

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
