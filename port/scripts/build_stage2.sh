#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
task_sysroot="$task_root/work/musl-cross"
task_stage="$task_root/work/stage2-root"
task_output="$task_root/out/experiments/stage2"
task_profile=${1:-minimal}
if [[ "$task_profile" == framework ]]; then
    task_stage="$task_root/work/stage2-framework-root"
    task_output="$task_root/out/experiments/stage2-framework"
    task_native=$(python3 "$task_root/port/scripts/prepare_native_framework.py")
    task_config="$task_native/etc"
else
    task_config=$(python3 "$task_root/port/scripts/prepare_init_lab.py" --profile "$task_profile")
fi
task_cleanup_payload_links() {
    python3 - "$task_stage/hmos/images" "$task_root/hmos5" <<'PY'
from pathlib import Path
import sys
stage, original = map(Path, sys.argv[1:])
for name in ('system', 'vendor', 'chip_prod', 'sys_prod', 'cust', 'patch'):
    path, source = stage / (name + '.img'), original / (name + '.img')
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
    task_data="$task_stage/hmos/bootstrap/data.ext4"
    python3 - "$task_data" <<'PY'
import os, stat, sys
path = sys.argv[1]
if os.path.lexists(path) and not stat.S_ISREG(os.lstat(path).st_mode):
    raise SystemExit('Refusing non-regular RAM-data template path')
fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
if not stat.S_ISREG(os.fstat(fd).st_mode):
    raise SystemExit('Refusing to format non-regular RAM-data template')
os.ftruncate(fd, 128 * 1024 * 1024)
os.close(fd)
PY
    mkfs.ext4 -q -F -m 0 -U 5dc8c93c-079d-4dbc-92ab-fc077d500013 "$task_data"
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
for task_part in system vendor chip_prod sys_prod cust patch; do
    ln -f "$task_root/hmos5/$task_part.img" "$task_stage/hmos/images/$task_part.img"
done
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
"$task_root/bin/Linux/x86_64/mkfs.erofs" -T 0 --all-root \
    --file-contexts "$task_root/work/stage2-file-contexts" "$task_output/system.img" "$task_stage"
python3 "$task_root/port/scripts/sign_probe.py" --image "$task_output/system.img"
sha256sum "$task_output/system.img" > "$task_output/SHA256SUMS"
python3 "$task_root/port/scripts/record_stage2_build.py" --profile "$task_profile"
printf 'Experimental RAM-only HarmonyOS init image: %s\n' "$task_output/system.img"
