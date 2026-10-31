#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
if [[ ${1:-} != --inside ]]; then
    mkdir -p "$task_root/work/mount-regression"
    gcc -static -Wall -Wextra -Werror -O2 "$task_root/port/src/test_stage2_mounts.c" \
        -o "$task_root/work/test-stage2-mounts"
    exec unshare --user --map-root-user --mount --net bash "$0" --inside
fi
mount --make-rprivate /
task_fixture="$task_root/work/mount-regression"
mount -t tmpfs -o mode=0755,size=16M tmpfs "$task_fixture"
mkdir -p "$task_fixture/donor" "$task_fixture/source/sys_prod/etc/init" "$task_fixture/source/vendor" \
    "$task_fixture/stock/vendor/bin" "$task_fixture/stock/vendor/lib64" \
    "$task_fixture/stock/vendor/firmware" "$task_fixture/stock/vendor/etc/init" "$task_fixture/stock/odm" \
    "$task_fixture/ohos-runtime/bin" "$task_fixture/ohos-runtime/lib64" \
    "$task_fixture/hmos/overrides/sys_prod/etc/window/resources" \
    "$task_fixture/hmos/overrides/sys_prod/etc/graphic"
printf 'must be hidden' > "$task_fixture/source/sys_prod/etc/init/unsafe.cfg"
printf 'must be hidden' > "$task_fixture/stock/vendor/etc/init/stock.rc"
printf 'android-runtime' > "$task_fixture/stock/vendor/lib64/libandroid-test.so"
printf 'ohos-runtime' > "$task_fixture/ohos-runtime/lib64/libhdi-test.so"
printf 'op13-stock' > "$task_fixture/stock/vendor/firmware/op13.bin"
printf 'op13-stock' > "$task_fixture/stock/odm/op13.cfg"
printf 'op13-config' > "$task_fixture/hmos/overrides/sys_prod/etc/window/resources/display_manager_config.xml"
printf 'op13-config' > "$task_fixture/hmos/overrides/sys_prod/etc/graphic/hgm_policy_config.xml"
cp "$task_root/work/test-stage2-mounts" "$task_fixture/test"
chroot "$task_fixture" /test
