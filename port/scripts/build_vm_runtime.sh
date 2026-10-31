#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
task_profile=${1:-core}
case "$task_profile" in core|framework|foundation|native) ;; *) exit 2 ;; esac
task_stage="$task_root/work/system-vm/runtime-root-$task_profile"
mkdir -p "$task_root/work/logs"
if [[ "$task_profile" == foundation || "$task_profile" == native ]]; then
    mkdir -p "$task_root/work/framework-assets"
    "$task_root/bin/Linux/x86_64/extract.erofs" -i "$task_root/hmos5/system.img" \
        -X /system/app/SystemResources -s -o "$task_root/work/framework-assets" \
        > "$task_root/work/logs/vm-framework-resources-extract.log" 2>&1
    mkdir -p "$task_root/work/huks-inspect"
    for task_library in libhuks_ca_hdi.z.so libhuks_hdi_service_1.1.z.so libhuks_ext_hdi_service_1.0.z.so; do
        "$task_root/bin/Linux/x86_64/extract.erofs" -i "$task_root/hmos5/vendor.img" \
            -X "/lib64/chipsetsdk/$task_library" -s -o "$task_root/work/huks-inspect" \
            >> "$task_root/work/logs/vm-framework-resources-extract.log" 2>&1
    done
fi
bash "$task_root/port/scripts/build_vm_probe.sh"
bash "$task_root/port/scripts/build_vm_sa_query.sh"
if [[ "$task_profile" == native ]]; then
    python3 "$task_root/port/scripts/prepare_vm_runtime.py" --profile foundation
    python3 "$task_root/port/scripts/prepare_native_framework.py"
    python3 "$task_root/port/scripts/prepare_native_vm.py"
    task_data="$task_stage/hmos/bootstrap/data.ext4"
else
    python3 "$task_root/port/scripts/prepare_vm_runtime.py" --profile "$task_profile"
    task_data="$task_stage/vm/data.ext4"
fi
# Format only a newly generated regular file. It enters cpio and becomes a
# guest-RAM loop filesystem; it is never attached as a host disk.
rm -f -- "$task_data"
truncate -s 128M "$task_data"
mkfs.ext4 -q -F -m 0 -U 5dc8c93c-079d-4dbc-92ab-fc077d500013 "$task_data"
python3 "$task_root/port/scripts/vm_file_list.py" --profile "$task_profile" > "$task_root/work/system-vm/core-files.list"
(
    cd "$task_stage"
    cpio --null -o --format=newc --owner=0:0 < ../core-files.list \
        2> "$task_root/work/logs/vm-core-compact-cpio.log" | gzip -1
) > "$task_root/out/vm/${task_profile}-compact.cpio.gz"
sha256sum "$task_root/out/vm/${task_profile}-compact.cpio.gz" > "$task_root/out/vm/${task_profile}-compact.sha256"
