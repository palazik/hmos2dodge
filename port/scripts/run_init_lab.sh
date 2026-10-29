#!/usr/bin/env bash
# Isolated user/PID/mount/network namespaces; no phone or host block devices.
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
lab_profile=${HMOS_LAB_PROFILE:-minimal}
lab_config=$(python3 "$task_root/port/scripts/prepare_init_lab.py" --profile "$lab_profile")
lab_prefix=ohos-init
if [[ "$lab_profile" != minimal ]]; then lab_prefix="ohos-init-$lab_profile"; fi
mkdir -p "$task_root/work/init-lab" "$task_root/work/logs"
if [[ ${1:-} != --inside ]]; then
    set +e
    timeout --signal=TERM --kill-after=2s 12s unshare \
        --user --map-root-user --mount --pid --fork --kill-child=KILL --net \
        "$0" --inside > "$task_root/work/logs/$lab_prefix-lab.log" 2>&1
    task_status=$?
    set -e
    printf 'Offline init lab exited: %s (124 means timed out)\n' "$task_status"
    tail -50 "$task_root/work/logs/$lab_prefix-lab.log"
    python3 "$task_root/port/scripts/check_init_lab.py" --prefix "$lab_prefix"
    exit 0
fi
lab_root="$task_root/work/init-lab"
mount --make-rprivate /
for task_dir in system dev proc sys data mnt config metadata vendor sys_prod chip_prod cust patch_hw storage; do
    mkdir -p "$lab_root/$task_dir"
done
for task_link in bin etc lib lib64; do
    ln -sfn "system/$task_link" "$lab_root/$task_link"
done
mount --bind "$task_root/work/ohos-runtime/system/system" "$lab_root/system"
mount -o remount,bind,ro "$lab_root/system"
mount --bind "$lab_config" "$lab_root/system/etc"
mount -o remount,bind,ro "$lab_root/system/etc"
mount -t tmpfs -o mode=0555 tmpfs "$lab_root/system/lib64/init"
mount -t proc proc "$lab_root/proc"
mount -t tmpfs -o mode=0755 tmpfs "$lab_root/sys"
mount -t tmpfs -o mode=0755 tmpfs "$lab_root/dev"
mkdir -p "$lab_root/dev/socket" "$lab_root/dev/shm" "$lab_root/dev/pts"
for task_device in null zero random urandom; do
    touch "$lab_root/dev/$task_device"
    mount --bind "/dev/$task_device" "$lab_root/dev/$task_device"
done
touch "$lab_root/dev/kmsg" "$lab_root/dev/hmos-init-stage2"
: > "$task_root/work/logs/$lab_prefix-kmsg.txt"
: > "$task_root/work/logs/$lab_prefix-marker.txt"
: > "$task_root/work/logs/$lab_prefix-processes.txt"
mount --bind "$task_root/work/logs/$lab_prefix-kmsg.txt" "$lab_root/dev/kmsg"
mount --bind "$task_root/work/logs/$lab_prefix-marker.txt" "$lab_root/dev/hmos-init-stage2"
cp "$task_root/work/host-tools/usr/bin/qemu-aarch64-static" "$lab_root/qemu-aarch64.next"
mv -f "$lab_root/qemu-aarch64.next" "$lab_root/qemu-aarch64"
if [[ "$lab_profile" != minimal ]]; then
    mkdir -p "$lab_root/binfmt"
    mount -t binfmt_misc binfmt_misc "$lab_root/binfmt"
    python3 "$task_root/port/scripts/register_lab_binfmt.py" "$lab_root/binfmt" "$lab_root/qemu-aarch64"
fi
(
    sleep 1
    cat "$lab_root/proc/1/status" > "$task_root/work/logs/$lab_prefix-pid1-status.txt"
    if [[ "$lab_profile" != minimal ]]; then
        chroot "$lab_root" /system/bin/hilog -h > "$task_root/work/logs/$lab_prefix-hilog-help.txt" 2>&1 || true
        lab_hilog_status=0
        chroot "$lab_root" /system/bin/hilog -x > "$task_root/work/logs/$lab_prefix-hilog-dump.txt" 2>&1 || lab_hilog_status=$?
        printf '%s\n' "$lab_hilog_status" > "$task_root/work/logs/$lab_prefix-hilog-status.txt"
    fi
    for ((lab_tick=0; lab_tick<7; lab_tick++)); do
        for lab_process in "$lab_root"/proc/[0-9]*/cmdline; do
            [[ -f "$lab_process" ]] || continue
            tr '\0' ' ' < "$lab_process" >> "$task_root/work/logs/$lab_prefix-processes.txt" || true
            printf '\n' >> "$task_root/work/logs/$lab_prefix-processes.txt"
        done
        sleep 1
    done
) &
exec chroot "$lab_root" /qemu-aarch64 /system/bin/init --second-stage 0
