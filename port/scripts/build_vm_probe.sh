#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
task_sysroot="$task_root/work/musl-cross"
task_stage="$task_root/work/system-vm/probe-root"
task_output="$task_root/out/vm"
mkdir -p "$task_stage/dev" "$task_stage/sys" "$task_stage/proc" "$task_output"
clang --target=aarch64-linux-musl -fuse-ld=lld -static -nostdinc -nostdlib \
    -isystem "$task_sysroot/include" -Wall -Wextra -Werror -O2 \
    "$task_sysroot/lib/crt1.o" "$task_sysroot/lib/crti.o" \
    "$task_root/port/src/vm_init.c" -Wl,--start-group "$task_sysroot/lib/libc.a" \
    "$task_root/work/cross-runtime/usr/lib/gcc-cross/aarch64-linux-gnu/14/libgcc.a" \
    -Wl,--end-group "$task_sysroot/lib/crtn.o" -o "$task_stage/init"
llvm-strip "$task_stage/init"
(cd "$task_stage" && find . -print0 | LC_ALL=C sort -z | \
    cpio --null -o --format=newc --owner=0:0 2>/dev/null | gzip -1) > "$task_output/probe.cpio.gz"
printf '%s\n' "$task_output/probe.cpio.gz"
