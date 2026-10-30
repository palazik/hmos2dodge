#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Diskless QEMU virt; no host drives, shares, networking or device passthrough.
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
task_profile=${1:-probe}
case "$task_profile" in
    probe) task_initrd="$task_root/out/vm/probe.cpio.gz"; task_memory=1024 ;;
    core) task_initrd="$task_root/out/vm/core-compact.cpio.gz"; task_memory=2048 ;;
    framework) task_initrd="$task_root/out/vm/framework-compact.cpio.gz"; task_memory=4096 ;;
    *) printf 'Expected probe, core or framework\n' >&2; exit 2 ;;
esac
task_initrd=${HMOS_VM_INITRD:-"$task_initrd"}
task_timeout=${HMOS_VM_TIMEOUT:-300}
task_kernel=${HMOS_VM_KERNEL:-"$task_root/out/baseline-android/Image"}
test -s "$task_kernel"
task_qemu=${HMOS_QEMU:-$(command -v qemu-system-aarch64 || true)}
if [[ -z "$task_qemu" ]]; then task_qemu="$task_root/work/system-vm/tools/usr/bin/qemu-system-aarch64"; fi
test -x "$task_qemu"
test -s "$task_initrd"
mkdir -p "$task_root/work/logs"
exec 9>"$task_root/work/system-vm/run.lock"
flock -n 9 || { printf 'Another VM lab is running\n' >&2; exit 2; }
if [[ "$task_profile" != probe ]]; then
    python3 "$task_root/port/scripts/record_vm_launch.py" --profile "$task_profile" \
        --kernel "$task_kernel" --initrd "$task_initrd"
fi
task_log="$task_root/work/logs/vm-$task_profile.log"
task_libraries="$task_root/work/system-vm/tools/usr/lib/x86_64-linux-gnu:$task_root/work/system-vm/tools/lib/x86_64-linux-gnu"
set +e
LD_LIBRARY_PATH="$task_libraries${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
timeout --signal=TERM --kill-after=5s "${task_timeout}s" "$task_qemu" \
    -machine virt,gic-version=3 -cpu max -smp 4 -m "$task_memory" \
    -accel tcg,thread=multi -nodefaults -display none -monitor none \
    -serial stdio -nic none -no-reboot \
    -kernel "$task_kernel" -initrd "$task_initrd" \
    -append 'console=ttyAMA0 earlycon=pl011,0x9000000 nokaslr panic=-1' \
    > "$task_log" 2>&1
task_status=$?
set -e
printf 'VM %s exit=%s; log: %s\n' "$task_profile" "$task_status" "$task_log"
exit "$task_status"
