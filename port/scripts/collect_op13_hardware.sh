#!/usr/bin/env bash
# Read mounted Android files/sysfs only; no root, partition writes or flashing.
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
task_output="$task_root/work/device-hardware/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$task_output"
adb get-state
adb shell getprop > "$task_output/getprop.txt"
adb shell uname -a > "$task_output/uname.txt" 2>&1 || true
adb shell cat /proc/modules > "$task_output/modules.txt" 2>&1 || true
adb shell cat /proc/mounts > "$task_output/mounts.txt" 2>&1 || true
adb shell 'for p in /sys/class/drm/card*-DSI-*/modes /sys/class/drm/card*-DSI-*/status /sys/class/backlight/*/max_brightness /sys/class/backlight/*/brightness; do echo "$p"; cat "$p"; done' \
    > "$task_output/display-sysfs.txt" 2>&1 || true
adb shell ls -l /dev/dri /dev/kgsl-3d0 /dev/dma_heap /dev/ion \
    > "$task_output/graphics-devices.txt" 2>&1 || true
adb shell dumpsys display > "$task_output/display.txt" 2>&1 || true
adb shell 'find /vendor/firmware /vendor/firmware_mnt/image -maxdepth 2 -type f' \
    > "$task_output/firmware-files.txt" 2>&1 || true
for task_source in /vendor/etc/vintf /vendor/etc/init /vendor_dlkm/lib/modules /vendor/lib/modules /system_dlkm/lib/modules /lib/modules; do
    task_name=${task_source#/}
    task_name=${task_name//\//_}
    adb pull -a "$task_source" "$task_output/$task_name" \
        > "$task_output/$task_name-pull.log" 2>&1 || true
done
printf 'Read-only hardware capture saved to %s\n' "$task_output"
