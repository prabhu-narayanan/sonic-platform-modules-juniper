import os
import subprocess
from pathlib import Path

import pytest


BASE_DIR = Path(__file__).resolve().parent.parent
POSTINST = BASE_DIR / "debian" / "sonic-platform-juniper-common.postinst"


def run_install_prefix(tmp_path, wheel_present):
    source_dir = tmp_path / "x86_64-juniper_common"
    source_dir.mkdir()
    if wheel_present:
        (source_dir / "sonic_platform-1.0-py3-none-any.whl").touch()

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pip_log = tmp_path / "pip.log"
    pip = bin_dir / "pip3"
    pip.write_text(
        "#!/bin/sh\n"
        "echo \"$*\" >> \"$PIP_LOG\"\n"
        "[ \"$1\" != show ]\n"
    )
    pip.chmod(0o755)

    script = POSTINST.read_text().replace(
        "SRC_DIR=/usr/share/sonic/device/x86_64-juniper_common/",
        f"SRC_DIR={source_dir}/",
    )
    script = script.split("# Ensure scripts are executable", 1)[0]
    env = os.environ.copy()
    env.update({"PATH": f"{bin_dir}:{env['PATH']}", "PIP_LOG": str(pip_log)})
    result = subprocess.run(
        ["bash", "-c", script],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, pip_log


def test_installs_wheel_without_onie_platform(tmp_path):
    result, pip_log = run_install_prefix(tmp_path, wheel_present=True)

    assert result.returncode == 0
    assert "install --root-user-action=ignore --no-deps" in pip_log.read_text()
    assert "installed sonic_platform system-wide only" in result.stdout


def test_missing_wheel_fails_package_configuration(tmp_path):
    result, pip_log = run_install_prefix(tmp_path, wheel_present=False)

    assert result.returncode == 1
    assert "install " not in pip_log.read_text()
    assert "sonic_platform wheel not found" in result.stderr


def test_qfx5241_manifest_installs_platform_utils_and_service():
    manifest = (BASE_DIR / "debian" / "sonic-platform-juniper-qfx5241.install").read_text()
    assert "qfx5241/utils/qfx5241_platform_init.py usr/local/bin" in manifest
    assert "qfx5241/utils/qfx5241_post_pddf_init.py usr/local/bin" in manifest
    assert "qfx5241/service/pddf-platform-init.service etc/systemd/system" in manifest
    rules = (BASE_DIR / "debian" / "rules").read_text()
    assert "MODULE_DIRS  ?= qfx5241" in rules
    assert 'cp $$WHL debian/$${pkg}/$${PLAT_DESTDIR}/;' in rules
    assert 'cp $$WHL debian/$${pkg}/$${PLAT_DESTDIR}/pddf/;' in rules


@pytest.mark.parametrize("include_jma", ["0", "n", "1", "y"])
def test_jma_staging_honors_build_option(tmp_path, include_jma):
    result = subprocess.run(
        ["make", "-n", "-o", "build", "-o", "build-indep", "-f",
         "debian/rules", "binary-indep"],
        cwd=BASE_DIR,
        text=True,
        capture_output=True,
        check=True,
    )
    staging = result.stdout.split(
        "# ===== dc-jma container + jmd-dispatcher (Juniper Mist Agent) =====", 1
    )[1].split("# Platform specific debian package", 1)[0]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    command_log = tmp_path / "commands.log"
    for command in ("dh_installdirs", "cp"):
        stub = bin_dir / command
        stub.write_text('#!/bin/sh\necho "$*" >> "$COMMAND_LOG"\n')
        stub.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "PATH": f"{bin_dir}:{env['PATH']}",
        "COMMAND_LOG": str(command_log),
        "INCLUDE_DC_JMA": include_jma,
    })
    subprocess.run(["bash", "-e", "-c", staging], env=env, check=True)
    assert command_log.exists() == (include_jma in ("1", "y"))


def test_common_postinst_skips_jma_database_update_without_config(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    redis_log = tmp_path / "redis.log"
    redis = bin_dir / "redis-cli"
    redis.write_text('#!/bin/sh\necho "$*" >> "$REDIS_LOG"\necho PONG\n')
    redis.chmod(0o755)
    script = POSTINST.read_text().split(
        "# For upgrades: add dc-jma to running CONFIG_DB if accessible", 1
    )[1]
    env = os.environ.copy()
    env.update({
        "PATH": f"{bin_dir}:{env['PATH']}",
        "REDIS_LOG": str(redis_log),
        "DC_JMA_FEATURE_JSON": str(tmp_path / "absent-feature.json"),
    })
    subprocess.run(["bash", "-e", "-c", script], env=env, check=True)
    assert not redis_log.exists()