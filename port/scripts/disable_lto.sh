#!/usr/bin/env bash
# Run after saving the completed ThinLTO image. Does not rebuild the Image.
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
kernel_dir="$task_root/kernel_workspace/common"
test -s "$task_root/out/kernel/Image"
mkdir -p "$task_root/work/kernel-baseline/arch/arm64/configs"
cp -n "$kernel_dir/arch/arm64/configs/gki_defconfig" \
    "$task_root/work/kernel-baseline/arch/arm64/configs/gki_defconfig" || true
for task_config in "$kernel_dir/arch/arm64/configs/gki_defconfig" "$kernel_dir/kout/.config"; do
    "$kernel_dir/scripts/config" --file "$task_config" \
        --disable LTO_CLANG_THIN --disable LTO_CLANG_FULL --enable LTO_NONE
done
export PATH="$task_root/kernel_workspace/zyc-clang/bin:$PATH"
export LDCACHE_DIR="$task_root/work/kernel-lto-cache"
make -C "$kernel_dir" LLVM=1 LLVM_IAS=1 ARCH=arm64 \
    LD="$kernel_dir/ld-wrapper" HOSTLD="$kernel_dir/ld-wrapper" \
    O="$kernel_dir/kout" olddefconfig > "$task_root/work/logs/disable-lto.log" 2>&1
cp "$kernel_dir/kout/.config" "$task_root/out/kernel/next-build.config"
rg '^CONFIG_LTO_NONE=y$|^# CONFIG_LTO_CLANG_THIN is not set$' "$kernel_dir/kout/.config"
