#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
task_sysroot="$task_root/work/musl-cross"
task_stage="$task_root/work/stage2-root"
task_output="$task_root/out/experiments/stage2"
task_profile=${1:-framework}
task_build_mode=${2:-}
if [[ -n "$task_build_mode" && "$task_build_mode" != --prepare-only ]]; then
    echo 'Second argument must be --prepare-only or omitted' >&2
    exit 2
fi
if [[ "$task_profile" == framework ]]; then
    task_stage="$task_root/work/stage2-framework-root"
    task_output="$task_root/out/experiments/stage2-framework"
    task_native=$(python3 "$task_root/port/scripts/prepare_native_framework.py")
    task_config="$task_native/etc"
else
    task_config=$(python3 "$task_root/port/scripts/prepare_init_lab.py" --profile "$task_profile")
fi
task_cleanup_payload_links() {
    python3 - "$task_stage/hmos/images" "$task_root" "$task_profile" <<'PY'
from pathlib import Path
import sys
stage, root = map(Path, sys.argv[1:3])
sys.path.insert(0, str(root / 'port/scripts'))
from stage2_sources import payload_sources
for name, source in payload_sources(sys.argv[3]).items():
    path = stage / name
    if path.exists() and source.exists() and path.samefile(source):
        path.unlink()
PY
}
trap task_cleanup_payload_links EXIT
mkdir -p "$task_stage" "$task_output" "$task_root/work/logs"
cp -a "$task_root/work/probe-root/." "$task_stage/"
mkdir -p "$task_stage/hmos/images" "$task_stage/hmos/bootstrap/etc"
chmod -R u+w "$task_stage/hmos/bootstrap/etc"
cp -a "$task_config/." "$task_stage/hmos/bootstrap/etc/"
printf '%s\n' "$task_profile" > "$task_stage/hmos/bootstrap/profile"
if [[ "$task_profile" == framework ]]; then
    mkdir -p "$task_stage/hmos/bootstrap/vendor_etc" "$task_stage/hmos/bootstrap/init_modules"
    chmod -R u+w "$task_stage/hmos/bootstrap/vendor_etc" "$task_stage/hmos/bootstrap/init_modules"
    cp -a "$task_native/vendor_etc" "$task_native/init_modules" "$task_stage/hmos/bootstrap/"
    cp "$task_native/data-directories" "$task_stage/hmos/bootstrap/data-directories"
    # Persistent data comes from DSU's userdata_gsi mapping. Retire only
    # this builder's old RAM seed; never format a device at startup.
    rm -f -- "$task_stage/hmos/bootstrap/data.ext4"
fi
mkdir -p "$task_stage/hmos/overrides/vendor/lib64"
python3 "$task_root/port/scripts/prepare_ui_config.py"
cp -a "$task_root/out/ui-config/overrides/sys_prod" "$task_stage/hmos/overrides/"
for task_library in libdisplay_buffer_vdi_impl.z.so libdisplay_composer_vdi_impl.z.so; do
    if [[ -f "$task_root/out/display/$task_library" ]]; then
        cp "$task_root/out/display/$task_library" "$task_stage/hmos/overrides/vendor/lib64/$task_library"
        chmod 0644 "$task_stage/hmos/overrides/vendor/lib64/$task_library"
    fi
done
cat > "$task_root/work/stage2-file-contexts" <<'EOF'
/.* u:object_r:rootfs:s0
/system/bin/init u:object_r:init_exec:s0
/hmos/overrides/vendor/lib64/.* u:object_r:vendor_lib_file:s0
/hmos/overrides/sys_prod/.* u:object_r:sys_prod_file:s0
EOF
if [[ "$task_profile" == framework ]]; then
    cp "$task_native/file-contexts" "$task_root/work/stage2-file-contexts"
fi
python3 - "$task_stage/hmos/images" "$task_root" "$task_profile" <<'PY'
from pathlib import Path
import sys
stage, root = map(Path, sys.argv[1:3])
sys.path.insert(0, str(root / 'port/scripts'))
from stage2_sources import payload_sources, verify_sources
verify_sources(sys.argv[3])
for name, source in payload_sources(sys.argv[3]).items():
    target = stage / name
    if target.exists():
        if not target.samefile(source):
            raise SystemExit('Refusing unexpected staging image: ' + str(target))
        target.unlink()
    target.hardlink_to(source)
PY
gcc -Wall -Wextra -Werror -O2 "$task_root/port/src/dsu_stage2.c" -o "$task_root/work/dsu-stage2-host"
"$task_root/work/dsu-stage2-host" --selftest
clang --target=aarch64-linux-musl -fuse-ld=lld -static -nostdinc -nostdlib \
    -isystem "$task_sysroot/include" -Wall -Wextra -Werror -O2 \
    "$task_sysroot/lib/crt1.o" "$task_sysroot/lib/crti.o" \
    "$task_root/port/src/dsu_stage2.c" -Wl,--start-group "$task_sysroot/lib/libc.a" \
    "$task_root/work/cross-runtime/usr/lib/gcc-cross/aarch64-linux-gnu/14/libgcc.a" \
    -Wl,--end-group "$task_sysroot/lib/crtn.o" -o "$task_stage/system/bin/init"
llvm-strip "$task_stage/system/bin/init"
"$task_root/work/host-tools/usr/bin/qemu-aarch64-static" "$task_stage/system/bin/init" --selftest
if [[ "$task_build_mode" == --prepare-only ]]; then
    echo 'Stage2 prepared and compiled; no full image packed. Source hardlinks removed on exit.'
    exit 0
fi
"$task_root/bin/Linux/x86_64/mkfs.erofs" -T 0 --all-root \
    --file-contexts "$task_root/work/stage2-file-contexts" "$task_output/system.img" "$task_stage"
python3 "$task_root/port/scripts/sign_probe.py" --image "$task_output/system.img"
sha256sum "$task_output/system.img" > "$task_output/SHA256SUMS"
python3 "$task_root/port/scripts/record_stage2_build.py" --profile "$task_profile"
printf 'Experimental RAM-only HarmonyOS init image: %s\n' "$task_output/system.img"
