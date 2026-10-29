/* SPDX-License-Identifier: Apache-2.0 */
#include <cstdio>
#include <dlfcn.h>
#include "idisplay_buffer_vdi.h"
#include "idisplay_composer_vdi_v1_1.h"

using OHOS::HDI::Display::Buffer::V1_0::IDisplayBufferVdi;
using OHOS::HDI::Display::Composer::IDisplayComposerVdiV1_1;

int main()
{
    void *buffer_lib = dlopen("/vendor/lib64/libdisplay_buffer_vdi_impl.z.so", RTLD_NOW | RTLD_LOCAL);
    void *composer_lib = dlopen("/vendor/lib64/libdisplay_composer_vdi_impl.z.so", RTLD_NOW | RTLD_LOCAL);
    if (!buffer_lib || !composer_lib) { fprintf(stderr, "FAIL libraries: %s\n", dlerror()); return 1; }
    auto buffer_create = reinterpret_cast<IDisplayBufferVdi *(*)()>(dlsym(buffer_lib, "CreateDisplayBufferVdi"));
    auto buffer_destroy = reinterpret_cast<void (*)(IDisplayBufferVdi *)>(dlsym(buffer_lib, "DestroyDisplayBufferVdi"));
    auto composer_create = reinterpret_cast<IDisplayComposerVdiV1_1 *(*)()>(dlsym(composer_lib, "CreateComposerVdiV1_1"));
    auto composer_destroy = reinterpret_cast<void (*)(IDisplayComposerVdiV1_1 *)>(dlsym(composer_lib, "DestroyComposerVdiV1_1"));
    if (!buffer_create || !buffer_destroy || !composer_create || !composer_destroy) return 2;
    auto *buffer = buffer_create();
    auto *composer = composer_create();
    if (!buffer || !composer) return 3;
    OHOS::HDI::Display::Buffer::V1_0::AllocInfo allocation{};
    BufferHandle *handle = nullptr;
    int result = buffer->AllocMem(allocation, handle);
    if (result != -5 || handle) { fprintf(stderr, "FAIL allocator virtual ABI: %d\n", result); return 4; }
    OHOS::HDI::Display::Composer::V1_0::HDRCapability hdr{};
    result = composer->GetHDRCapabilityInfos(0, hdr);
    if (result || hdr.formatCount || !hdr.formats.empty()) { fprintf(stderr, "FAIL HDR virtual ABI\n"); return 5; }
    result = composer->SetHardwareCursorPosition(0, 1, 2);
    if (!result) { fprintf(stderr, "FAIL cursor should be unsupported\n"); return 6; }
    buffer_destroy(buffer);
    composer_destroy(composer);
    puts("PASS typed VDI calls: invalid allocation, HDR vector layout, legacy cursor slot, destruction");
    // Keep the libraries resident; explicit unload is separately unverified.
    return 0;
}
