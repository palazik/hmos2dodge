#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
kernel_dir="$task_root/kernel_workspace/common"
export PATH="$task_root/kernel_workspace/zyc-clang/bin:$PATH"
if [[ -x "$task_root/work/host-tools/usr/bin/ccache" ]]; then
    export PATH="$task_root/work/host-tools/usr/bin:$PATH"
    export LD_LIBRARY_PATH="$task_root/work/host-tools/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    export CCACHE_DIR="$task_root/work/ccache"
    export CCACHE_MAXSIZE=2G
    kernel_cc='ccache clang'
else
    kernel_cc=clang
fi
export LDCACHE_DIR="$task_root/work/kernel-lto-cache"
mkdir -p "$LDCACHE_DIR" "$task_root/out/kernel" "$task_root/work/logs"
cd "$kernel_dir"
# Keep the user's original config, including localversion and GKI KMI options.
cp -n kout/.config "$task_root/work/kernel-baseline/original.config" || true
build_args=(-j"$(nproc --all)" LLVM=1 LLVM_IAS=1 ARCH=arm64
    CC="$kernel_cc"
    PERL="$task_root/port/scripts/perl_host.sh"
    CROSS_COMPILE=aarch64-linux-gnu- LD="$kernel_dir/ld-wrapper"
    HOSTLD="$kernel_dir/ld-wrapper" O="$kernel_dir/kout")
base_flags='-O2 -pipe -Wno-error -Wno-implicit-function-declaration -Wno-implicit-int -Wno-default-const-init-var-unsafe -Wno-format -Wno-unknown-warning-option'
make "${build_args[@]}" KCFLAGS="$base_flags" gki_defconfig 2>&1 | tee "$task_root/work/logs/kernel-config.log"
scripts/kconfig/merge_config.sh -m -O "$kernel_dir/kout" "$kernel_dir/kout/.config" arch/arm64/configs/hmos_dsu.config
make "${build_args[@]}" KCFLAGS="$base_flags" olddefconfig 2>&1 | tee -a "$task_root/work/logs/kernel-config.log"
make "${build_args[@]}" KCFLAGS="$base_flags -mcpu=oryon-1" Image 2>&1 | tee "$task_root/work/logs/kernel-build.log"
cp kout/arch/arm64/boot/Image "$task_root/out/kernel/Image"
cp kout/.config "$task_root/out/kernel/config"
cp kout/vmlinux.symvers "$task_root/out/kernel/vmlinux.symvers"
sha256sum "$task_root/out/kernel/Image" > "$task_root/out/kernel/SHA256SUMS"
printf 'Kernel built: %s\n' "$task_root/out/kernel/Image"
