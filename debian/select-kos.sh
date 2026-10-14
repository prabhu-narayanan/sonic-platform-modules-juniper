#!/bin/bash
#
# select-kos.sh -- pick the kernel modules a platform package must ship.
#
# usage: select-kos.sh <drivers-dir> <pddf-device.json> [extra.json ...]
#
# Prints, one absolute path per line, the .ko files to install for the
# platform described by the supplied JSON files.  When a platform ships
# multiple cooling/SKU variants (e.g. QFX5250 air-cooled 64-OE and
# liquid-cooled 64-OE-L) pass all variant pddf-device.json files so every
# variant's custom_kos entries are included in the package.
#
# We deliberately do NOT ship every module we build.  A platform package
# must contain only that platform's drivers:
#
#   - shipping another platform's modules is dead weight in the image, and
#   - it is unsafe.  Two boards' variants of the same driver can claim one
#     platform driver name -- e.g. several "leds-i2cs" implementations for
#     compatible "jnx,leds-i2cs".  With both present udev can autoload the
#     wrong one, and the right one then fails to register with -EBUSY.
#
# Equally, we cannot just copy the names listed in pddf-device.json.  That
# list says what PDDF *loads*; it never names a module that is pulled in
# only as a dependency.  qfx5241-leds-jnx-i2cs calls jnx_schedule_work(),
# which lives in jnx-wq, and no platform lists jnx-wq as a dependency of
# it.  Omitting jnx-wq.ko made modprobe fail on the unresolved jnx_wq
# symbol and took down pddf-platform-init.service.
#
# So: seed from the JSON, then close over the dependencies that modinfo
# reports in the modules we actually built.
#
set -u

DRV=${1:-}
if [ ! -d "$DRV" ]; then
	echo "ERROR: select-kos.sh: no such drivers directory: $DRV" >&2
	exit 1
fi
shift
# All remaining args are JSON files to seed from (primary first, then any
# HWSKU-variant overrides).  Collect only the ones that actually exist.
json_files=()
for _j in "$@"; do
	[ -f "$_j" ] && json_files+=("$_j")
done

# Resolve a module name to a built .ko.  depmod/modinfo report dependency
# names with underscores ("jnx_wq") while the files on disk use dashes
# ("jnx-wq.ko"), so try both spellings.
resolve() {
	local n=$1 f
	for f in "$DRV/$n.ko" "$DRV/${n//_/-}.ko" "$DRV/${n//-/_}.ko"; do
		if [ -f "$f" ]; then
			echo "$f"
			return 0
		fi
	done
	return 1
}

# A platform with no pddf-device.json has no machine-readable driver list,
# so fall back to shipping everything rather than shipping nothing.
if [ ${#json_files[@]} -eq 0 ]; then
	echo "NOTE: select-kos.sh: no JSON files found, shipping all built modules" >&2
	ls "$DRV"/*.ko 2>/dev/null
	exit 0
fi

# Seed with every module named across all JSON files.  Names seen in more
# than one file (e.g. shared std_kos entries) are de-duplicated.  Entries
# that we do not build are in-tree kernel modules (i2c-dev, lm75, optoe, …)
# shipped by linux-image, so they are skipped rather than treated as errors.
seed=$(python3 -c '
import json, sys
seen = set()
names = []
for path in sys.argv[1:]:
    try:
        plat = json.load(open(path)).get("PLATFORM", {})
    except Exception as e:
        print(f"WARNING: cannot parse {path}: {e}", file=sys.stderr)
        continue
    for key in ("perm_kos", "std_kos", "pddf_drv_kos", "custom_kos"):
        for n in plat.get(key, []):
            if n not in seen:
                seen.add(n)
                names.append(n)
print("\n".join(names))
' "${json_files[@]}") || exit 1

pending=$seed
selected=""
missing=""

while [ -n "$pending" ]; do
	next=""
	for name in $pending; do
		ko=$(resolve "$name") || {
			# not built here: in-tree module, or a genuine typo in the
			# JSON.  Record it so the build log shows what was skipped.
			case " $missing " in
				*" $name "*) ;;
				*) missing="$missing $name" ;;
			esac
			continue
		}

		# Deduplicate on the resolved file, not the name: the JSON says
		# "jnx-wq" while modinfo says "jnx_wq", and both are jnx-wq.ko.
		case " $selected " in
			*" $ko "*) continue ;;
		esac
		selected="$selected $ko"
		echo "$ko"

		# Pull in whatever this module links against.  modinfo prints a
		# comma-separated list, empty for a leaf module.
		deps=$(modinfo -F depends "$ko" 2>/dev/null | tr ',' ' ')
		for dep in $deps; do
			[ -n "$dep" ] || continue
			resolve "$dep" >/dev/null 2>&1 || continue
			next="$next $dep"
		done
	done
	pending=$next
done

if [ -n "$missing" ]; then
	echo "NOTE: select-kos.sh: not built here (expected in-tree):$missing" >&2
fi
