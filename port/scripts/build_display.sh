#!/usr/bin/env bash
# Build only the adapted OHOS display HALs, never a kernel or Android image.
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
export SYSROOT="$task_root/work/ohos-sdk"
task_headers="$task_root/work/ohos-headers"
task_source="$task_root/port/display/src"
task_output="$task_root/out/display"
mkdir -p "$task_output/obj"
python3 "$task_root/port/scripts/prepare_display.py"
# The donor exports SetHardwareCursorPosition, not the 5.1 UpdateHardwareCursor
# and FastPresent interface. Match its 5.0.x VDI shape rather than changing the
# virtual table to satisfy newer headers.
mkdir -p "$task_root/work/display-abi/include"
mkdir -p "$task_root/work/display-abi/include/v1_2/include"
cp "$task_root/work/abi-headers/OpenHarmony-v5.0.3-Release/drivers_peripheral/display/composer/hdi_service/include/idisplay_composer_vdi_v1_1.h" \
    "$task_root/work/display-abi/include/"
cp "$task_root/work/abi-headers/OpenHarmony-v5.0.3-Release/drivers_interface/display/composer/v1_2/include/idisplay_composer_interface.h" \
    "$task_root/work/display-abi/include/"
cp "$task_root/work/display-abi/include/idisplay_composer_interface.h" \
    "$task_root/work/display-abi/include/v1_2/include/"
python3 - "$task_root" <<'PY'
from pathlib import Path
import shutil,sys
root=Path(sys.argv[1]); source=root/'work/ohos-runtime/system/system/lib64'; out=root/'work/ohos-sdk/usr/lib'
names=['libc++.so','libdrm.so','libhilog.so','libhdf_utils.z.so','libsec_shared.z.so','libhitrace_meter.so','libutils.z.so']
for name in names:
    candidates=[p for p in source.rglob(name) if p.is_file()]
    if not candidates: raise SystemExit('missing donor link library: '+name)
    shutil.copy2(candidates[0],out/name)
shutil.copy2(root/'work/ohos-runtime/system/system/lib/ld-musl-aarch64.so.1',out/'libc.so')
PY
chmod +x "$task_root/work/reference-source/build/ohos-clang" "$task_root/work/reference-source/build/ohos-clang++"
task_cxx="$task_root/work/reference-source/build/ohos-clang++"
task_flags=(-std=c++17 -O2 -fPIC -Wno-everything -I"$task_root/work/display-abi/include")
for task_include in \
    "$task_source/common" "$task_source/hdi-gen" "$task_source/hdi-gen/display" \
    "$task_source/hdi-gen/display/buffer" "$task_source/hdi-gen/display/composer" \
    "$task_source/hdi-gen/display/graphic/common" "$task_source/composer/include" \
    "$task_headers/drivers_interface/display/composer/hdifd_parcelable" \
    "$task_headers/drivers_interface/display/composer" "$task_headers/drivers_interface/display" \
    "$task_headers/drivers_interface/display/composer/common/include" \
    "$task_headers/drivers_peripheral/display/buffer/hdi_service/include" \
    "$task_headers/drivers_peripheral/display/composer/hdi_service/include" \
    "$task_headers/drivers_peripheral/display/utils/include" \
    "$task_headers/graphic_graphic_surface/interfaces/inner_api/utils" \
    "$task_headers/hdf_core/interfaces/inner_api/utils" \
    "$task_headers/hdf_core/interfaces/inner_api/osal/shared" \
    "$task_headers/hdf_core/interfaces/inner_api/osal/uhdf" \
    "$task_headers/hdf_core/interfaces/inner_api/hdi" \
    "$task_headers/hdf_core/interfaces/inner_api/hdi/base" \
    "$task_headers/hdf_core/interfaces/inner_api/ipc" \
    "$task_headers/hdf_core/interfaces/inner_api/core" \
    "$task_headers/communication_ipc/interfaces/innerkits/ipc_core/include" \
    "$task_headers/commonlibrary_c_utils/base/include" \
    "$task_headers/hiviewdfx_hilog/interfaces/native/innerkits/include" \
    "$task_headers/hiviewdfx_hitrace/interfaces/native/innerkits/include/hitrace_meter" \
    "$task_headers/third_party_libdrm" "$task_headers/third_party_libdrm/include" "$task_headers/third_party_libdrm/include/drm" \
    "$task_headers/third_party_bounds_checking_function/include"; do
    task_flags+=(-I"$task_include")
done
"$task_cxx" "${task_flags[@]}" -shared -Wl,--no-undefined \
    -o "$task_output/libdisplay_buffer_vdi_impl.z.so" "$task_source/buffer/sweet_buffer_vdi.cpp" \
    -Wl,-soname,libdisplay_buffer_vdi_impl.z.so -ldrm -lhilog -lc++ -lc
for task_file in "$task_source"/composer/src/*.cpp; do
    "$task_cxx" "${task_flags[@]}" -c "$task_file" -o "$task_output/obj/$(basename "${task_file%.cpp}").o"
done
"$task_cxx" -shared -Wl,--no-undefined -o "$task_output/libdisplay_composer_vdi_impl.z.so" \
    "$task_output"/obj/*.o -Wl,-soname,libdisplay_composer_vdi_impl.z.so \
    -L"$task_output" -ldisplay_buffer_vdi_impl.z -ldrm -lhilog -lhdf_utils.z -lsec_shared.z -lhitrace_meter -lutils.z -lc++ -lc
llvm-strip "$task_output/"*.so
"$task_cxx" "${task_flags[@]}" "$task_root/port/display/abi_test.cpp" \
    -o "$task_output/display-abi-test" -lc++ -lc
"$task_cxx" "${task_flags[@]}" "$task_root/port/display/mode_test.cpp" \
    -o "$task_output/display-mode-test" -L"$task_output" \
    -Wl,-rpath-link,"$SYSROOT/usr/lib" \
    -ldisplay_composer_vdi_impl.z -ldisplay_buffer_vdi_impl.z -lhilog -lc++ -lc
sha256sum "$task_output/"*.so > "$task_output/SHA256SUMS"
file "$task_output/"*.so
