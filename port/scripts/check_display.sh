#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
mkdir -p "$task_root/work/display-check/include"
c++ -std=c++17 -Wall -Wextra -Werror -I/usr/include/libdrm \
    "$task_root/port/display/test_drm_selection.cpp" -o "$task_root/work/display-check/test_drm_selection"
"$task_root/work/display-check/test_drm_selection"
cp /usr/include/xf86drm.h /usr/include/xf86drmMode.h "$task_root/work/display-check/include/"
cp -a /usr/include/libdrm/. "$task_root/work/display-check/include/"
cat > "$task_root/work/display-check/selector.c" <<'EOF'
#include "ohos_drm_device.h"
int OpenDisplay(char *path, size_t size) { return OhosOpenInternalDrm(path, size); }
EOF
clang --target=aarch64-linux-ohos -nostdinc -isystem "$task_root/work/ohos-sdk/usr/include" \
    -isystem "$(clang -print-resource-dir)/include" -I"$task_root/work/display-check/include" \
    -I"$task_root/port/display" -Wall -Wextra -Werror -O2 -fPIC -c \
    "$task_root/work/display-check/selector.c" -o "$task_root/work/display-check/selector-aarch64.o"
file "$task_root/work/display-check/selector-aarch64.o"
