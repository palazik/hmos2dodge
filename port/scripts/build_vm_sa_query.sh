#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
python3 "$task_root/port/scripts/prepare_vm_sa_headers.py"
export SYSROOT="$task_root/work/ohos-sdk"
task_headers="$task_root/work/ohos-headers"
task_flags=()
for task_directory in "$task_root/work/ohos-runtime/system/system/lib64" \
    "$task_root/work/ohos-runtime/system/system/lib64/platformsdk" \
    "$task_root/work/ohos-runtime/system/system/lib64/chipset-sdk" \
    "$task_root/work/ohos-runtime/system/system/lib64/chipset-pub-sdk"; do
    task_flags+=(-L"$task_directory" -Wl,-rpath-link,"$task_directory")
done
mkdir -p "$task_root/out/vm"
"$task_root/work/reference-source/build/ohos-clang++" -std=c++17 -O2 \
    -I"$task_headers/systemabilitymgr_samgr/interfaces/innerkits/samgr_proxy/include" \
    -I"$task_headers/communication_ipc/interfaces/innerkits/ipc_core/include" \
    -I"$task_headers/commonlibrary_c_utils/base/include" \
    -I"$task_headers/third_party_bounds_checking_function/include" \
    "$task_root/port/src/vm_sa_query.cpp" "${task_flags[@]}" \
    -Wl,--allow-shlib-undefined -lsamgr_proxy.z -lipc_core.z -lutils.z -lc++ -lc \
    -o "$task_root/out/vm/sa-query"
