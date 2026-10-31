#!/usr/bin/env bash
# Exercise the supplied HMOS Mesa libraries under QEMU user mode, no GPU.
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
export SYSROOT="$task_root/work/ohos-sdk"
task_egl="$task_root/work/egl-smoke"
mkdir -p "$task_egl/headers" "$task_egl/extracted" "$task_egl/libraries" "$task_root/work/logs"
# EGL/GLES headers are platform-neutral; libc headers still come from OHOS.
cp -a /usr/include/EGL /usr/include/GLES2 /usr/include/KHR "$task_egl/headers/"
for task_name in libEGL_impl.so libGLESv2_impl.so libgallium-26.1.0-devel.so; do
    "$task_root/bin/Linux/x86_64/extract.erofs" -s -i "$task_root/hmos5/vendor.img" \
        -X "/lib64/chipsetsdk/$task_name" -o "$task_egl/extracted" > /dev/null
    mv -f "$task_egl/extracted/vendor/lib64/chipsetsdk/$task_name" "$task_egl/libraries/$task_name"
done
"$task_root/work/reference-source/build/ohos-clang" -Wall -Wextra -Werror -O2 \
    -I"$task_egl/headers" "$task_root/port/display/egl_smoke.c" -o "$task_egl/egl-smoke" -lc
HMOS_DISPLAY_TEST_PROGRAM="$task_egl/egl-smoke" \
HMOS_DISPLAY_LIB_DIR="$task_egl/libraries" \
HMOS_DISPLAY_TEST_LOG="$task_root/work/logs/egl-smoke.log" \
    bash "$task_root/port/scripts/test_display_load.sh" > /dev/null
rg '^PASS HMOS EGL' "$task_root/work/logs/egl-smoke.log"
python3 - "$task_root" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
files = root / 'work/egl-smoke/libraries'
report = {
    'test': 'Supplied HMOS Mesa surfaceless EGL/GLES pbuffer rendering under QEMU user mode',
    'result': 'pass', 'renderer': 'softpipe', 'clear_rgba': [255, 0, 0, 255],
    'compiled_linked_shader_triangle_rgba': [0, 255, 0, 255],
    'libraries_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files.glob('*.so'))},
    'host_graphics_exposed': False, 'physical_device_accessed': False,
    'op13_display_tested': False, 'kgsl_acceleration_tested': False,
    'ohos_native_window_and_dma_buf_tested': False, 'sceneboard_tested': False,
}
(root / 'out/display/egl-smoke-result.json').write_text(json.dumps(report, indent=2) + '\n')
PY
