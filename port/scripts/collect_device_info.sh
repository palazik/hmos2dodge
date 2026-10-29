#!/usr/bin/env bash
# Read-only evidence collection. Run while Android is booted.
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
report_dir="$task_root/work/device-info/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$report_dir"
adb get-state
adb shell getprop > "$report_dir/getprop.txt"
adb shell uname -a > "$report_dir/uname.txt"
adb shell cat /proc/version > "$report_dir/proc-version.txt"
adb shell cat /proc/mounts > "$report_dir/mounts.txt"
adb shell cat /proc/modules > "$report_dir/modules.txt"
adb shell ls -l /dev/block/by-name > "$report_dir/partitions.txt" 2>&1 || true
adb shell ls -l /dev/dri /dev/dma_heap /dev/kgsl-3d0 > "$report_dir/graphics-devices.txt" 2>&1 || true
adb shell ls -l /sys/class/drm /sys/class/backlight > "$report_dir/display-sysfs.txt" 2>&1 || true
adb shell cat /proc/bootconfig > "$report_dir/bootconfig.txt" 2>&1 || true
adb shell cat /proc/cmdline > "$report_dir/cmdline.txt" 2>&1 || true
adb shell gsi_tool status > "$report_dir/dsu-status.txt" 2>&1 || true
printf 'Device evidence: %s\n' "$report_dir"
