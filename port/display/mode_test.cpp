/* SPDX-License-Identifier: Apache-2.0 */
#include <atomic>
#include <cstdio>
#include "drm_display.h"
#include "drm_connector.h"
#include "drm_crtc.h"

namespace OHOS::HDI::DISPLAY {
extern std::atomic<uint64_t> g_hmosVsyncPeriodNs;
}
using namespace OHOS::HDI::DISPLAY;

int main()
{
    drmModeModeInfo modes[3]{};
    const unsigned rates[] = {120, 60, 90};
    for (unsigned i = 0; i < 3; ++i) {
        modes[i].hdisplay = 1440;
        modes[i].vdisplay = 3168;
        modes[i].vrefresh = rates[i];
    }
    drmModeConnector raw{};
    raw.connector_type = DRM_MODE_CONNECTOR_DSI;
    raw.connection = DRM_MODE_CONNECTED;
    raw.count_modes = 3;
    raw.modes = modes;
    FdPtr fd = std::make_shared<HdiFd>();
    auto connector = std::make_shared<DrmConnector>(raw, fd);
    drmModeCrtc raw_crtc{};
    auto crtc = std::make_shared<DrmCrtc>(&raw_crtc, 0);
    DrmDisplay display(connector, crtc, nullptr);
    uint32_t count = 0, active = 99;
    DisplayModeInfo reported[3]{};
    if (!display.GetDisplaySupportedModes(nullptr, nullptr)) return 1;
    if (display.GetDisplaySupportedModes(&count, reported) || count != 3) return 2;
    for (unsigned i = 0; i < count; ++i) {
        auto mode = reported[i];
        if (mode.width != 1440 || mode.height != 3168) return 3;
        if (display.SetDisplayMode(mode.id) || display.GetDisplayMode(&active) || active != mode.id) return 4;
        if (crtc->GetActiveModeId() != static_cast<int>(mode.id) || !crtc->NeedModeSet()) return 5;
        if (g_hmosVsyncPeriodNs.load() != 1000000000ULL / mode.freshRate) return 6;
        crtc->ClearModeSet();
        if (display.SetDisplayMode(mode.id) || crtc->NeedModeSet()) return 7;
    }
    if (!display.SetDisplayMode(99) || !crtc->SetActivieMode(-1)) return 8;
    if (display.GetDisplayMode(&active) || active >= count) return 9;
    raw.count_modes = 1;
    auto single = std::make_shared<DrmConnector>(raw, fd);
    DrmDisplay single_display(single, crtc, nullptr);
    if (single_display.GetDisplaySupportedModes(&count, nullptr) || count != 1) return 10;
    puts("PASS real mode IDs, 1440x3168 dimensions, 60/90/120 Hz timing, invalid modes, no fake mode");
    return 0;
}
