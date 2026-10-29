#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
export SYSROOT="$task_root/work/ohos-sdk"
lab_root="$task_root/work/display-load-lab"
lab_log=${HMOS_DISPLAY_TEST_LOG:-$task_root/work/logs/display-load-test.log}
mkdir -p "$lab_root" "$task_root/work/logs"
if [[ ${1:-} != --inside ]]; then
    if [[ -n ${HMOS_DISPLAY_TEST_PROGRAM:-} ]]; then
        cp "$HMOS_DISPLAY_TEST_PROGRAM" "$lab_root/display-load-test.next"
        mv -f "$lab_root/display-load-test.next" "$lab_root/display-load-test"
    else
        "$task_root/work/reference-source/build/ohos-clang" -O2 "$task_root/port/display/load_test.c" \
            -o "$lab_root/display-load-test" -lc
    fi
    chmod 0755 "$lab_root/display-load-test"
    timeout --signal=KILL 15s unshare --user --map-root-user --mount --pid --fork \
        --kill-child=KILL --net "$0" --inside > "$lab_log" 2>&1
    cat "$lab_log"
    exit 0
fi
mount --make-rprivate /
for task_dir in system dev proc sys data vendor/lib64; do mkdir -p "$lab_root/$task_dir"; done
ln -sfn system/lib "$lab_root/lib"
ln -sfn system/lib64 "$lab_root/lib64"
ln -sfn system/etc "$lab_root/etc"
mount --bind "$task_root/work/ohos-runtime/system/system" "$lab_root/system"
mount -o remount,bind,ro "$lab_root/system"
mount --bind "${HMOS_DISPLAY_LIB_DIR:-$task_root/out/display}" "$lab_root/vendor/lib64"
mount -o remount,bind,ro "$lab_root/vendor/lib64"
mount -t proc proc "$lab_root/proc"
mount -t tmpfs -o mode=0755 tmpfs "$lab_root/dev"
mount -t tmpfs -o mode=0755 tmpfs "$lab_root/sys"
for task_device in null zero random urandom; do
    touch "$lab_root/dev/$task_device"
    mount --bind "/dev/$task_device" "$lab_root/dev/$task_device"
done
cp "$task_root/work/host-tools/usr/bin/qemu-aarch64-static" "$lab_root/qemu-aarch64.next"
mv -f "$lab_root/qemu-aarch64.next" "$lab_root/qemu-aarch64"
exec chroot "$lab_root" /qemu-aarch64 /display-load-test
