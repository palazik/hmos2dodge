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
mkdir -p "$task_fixture/donor/sys_prod/etc/init" \
    "$task_fixture/hmos/overrides/sys_prod/etc/window/resources" \
    "$task_fixture/hmos/overrides/sys_prod/etc/graphic"
printf 'must be hidden' > "$task_fixture/donor/sys_prod/etc/init/unsafe.cfg"
printf 'op13-config' > "$task_fixture/hmos/overrides/sys_prod/etc/window/resources/display_manager_config.xml"
printf 'op13-config' > "$task_fixture/hmos/overrides/sys_prod/etc/graphic/hgm_policy_config.xml"
cp "$task_root/work/test-stage2-mounts" "$task_fixture/test"
chroot "$task_fixture" /test
