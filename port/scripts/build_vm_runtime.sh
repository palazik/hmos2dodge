#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
mkdir -p "$task_root/work/logs"
bash "$task_root/port/scripts/build_vm_probe.sh"
bash "$task_root/port/scripts/build_vm_sa_query.sh"
python3 "$task_root/port/scripts/prepare_vm_runtime.py"
task_data="$task_root/work/system-vm/runtime-root/vm/data.ext4"
# Format only a newly generated regular file. It enters cpio and becomes a
# guest-RAM loop filesystem; it is never attached as a host disk.
rm -f -- "$task_data"
truncate -s 128M "$task_data"
mkfs.ext4 -q -F -m 0 -U 5dc8c93c-079d-4dbc-92ab-fc077d500013 "$task_data"
python3 "$task_root/port/scripts/vm_file_list.py" > "$task_root/work/system-vm/core-files.list"
(
    cd "$task_root/work/system-vm/runtime-root"
    cpio --null -o --format=newc --owner=0:0 < ../core-files.list \
        2> "$task_root/work/logs/vm-core-compact-cpio.log" | gzip -1
) > "$task_root/out/vm/core-compact.cpio.gz"
sha256sum "$task_root/out/vm/core-compact.cpio.gz" > "$task_root/out/vm/core-compact.sha256"
