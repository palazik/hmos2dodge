#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
task_sysroot="$task_root/work/musl-cross"
if [[ -d "$task_root/work/probe-root/hmos" ]]; then
    printf 'Stale donor payload in work/probe-root/hmos; clear generated probe staging first\n' >&2
    exit 2
fi
task_cleanup_payload_links() {
    python3 - "$task_root/work/mount-probe-root/hmos/images" "$task_root/hmos5" <<'PY'
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
mkdir -p "$task_root/out/dsu" "$task_root/work/probe-root/system/bin" "$task_root/work/probe-root/system/etc"
gcc -Wall -Wextra -Werror -O2 "$task_root/port/src/dsu_probe.c" -o "$task_root/work/dsu-probe-host"
"$task_root/work/dsu-probe-host" --selftest
clang --target=aarch64-linux-musl -fuse-ld=lld -static -nostdinc -nostdlib \
    -isystem "$task_sysroot/include" -Wall -Wextra -Werror -O2 \
    "$task_sysroot/lib/crt1.o" "$task_sysroot/lib/crti.o" \
    "$task_root/port/src/dsu_probe.c" -Wl,--start-group "$task_sysroot/lib/libc.a" \
    "$task_root/work/cross-runtime/usr/lib/gcc-cross/aarch64-linux-gnu/14/libgcc.a" \
    -Wl,--end-group "$task_sysroot/lib/crtn.o" \
    -o "$task_root/work/probe-root/system/bin/init"
llvm-strip "$task_root/work/probe-root/system/bin/init"
chmod 0755 "$task_root/work/probe-root/system/bin/init"
cat > "$task_root/work/probe-root/system/etc/prop.default" <<'EOF'
ro.product.device=op13_dsu_probe
ro.product.cpu.abi=arm64-v8a
ro.build.version.sdk=36
ro.build.version.security_patch=2026-07-01
ro.build.type=userdebug
EOF
cp "$task_root/work/probe-root/system/etc/prop.default" "$task_root/work/probe-root/system/build.prop"
for task_dir in dev proc sys data metadata mnt vendor product system_ext odm; do
    mkdir -p "$task_root/work/probe-root/$task_dir"
done
ln -sfn /system/bin/init "$task_root/work/probe-root/init"
"$task_root/bin/Linux/x86_64/mkfs.erofs" -T 0 --all-root \
    "$task_root/out/dsu/op13-dsu-probe.img" "$task_root/work/probe-root"
gzip -n -c "$task_root/out/dsu/op13-dsu-probe.img" > "$task_root/out/dsu/op13-dsu-probe.img.gz"
if [[ ${1:-} == --with-donor ]]; then
    mkdir -p "$task_root/work/mount-probe-root"
    cp -a "$task_root/work/probe-root/." "$task_root/work/mount-probe-root/"
    mkdir -p "$task_root/work/mount-probe-root/hmos/images"
    for part in system vendor chip_prod sys_prod cust patch; do
        ln -f "$task_root/hmos5/$part.img" "$task_root/work/mount-probe-root/hmos/images/$part.img"
    done
    "$task_root/bin/Linux/x86_64/mkfs.erofs" -T 0 --all-root \
        "$task_root/out/dsu/op13-hmos-mount-probe.img" "$task_root/work/mount-probe-root"
fi
python3 "$task_root/port/scripts/sign_probe.py"
gzip -n -c "$task_root/out/dsu/op13-dsu-probe.img" > "$task_root/out/dsu/op13-dsu-probe.img.gz"
sha256sum "$task_root/out/dsu/"*.img > "$task_root/out/dsu/SHA256SUMS"
file "$task_root/work/probe-root/system/bin/init" "$task_root/out/dsu/"*.img
