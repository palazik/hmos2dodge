#!/usr/bin/env python3
"""Stage OP13 display changes; keep the fetched upstream source untouched."""
from pathlib import Path
import difflib
import shutil

ROOT = Path(__file__).resolve().parents[2]
original = ROOT / 'work/reference-source/src/display'
target = ROOT / 'port/display/src'
target.mkdir(parents=True, exist_ok=True)
shutil.copytree(original, target, dirs_exist_ok=True)
shutil.copy2(ROOT / 'port/display/ohos_drm_device.h', target / 'common/ohos_drm_device.h')


def replace(name, old, new):
    p = target / name
    data = p.read_text()
    if data.count(old) != 1:
        raise RuntimeError(f'expected one anchor in {name}')
    p.write_text(data.replace(old, new))


replace('composer/src/drm_device.cpp', '#include "drm_device.h"',
        '#include "drm_device.h"\n#include "ohos_drm_device.h"')
replace('composer/src/drm_device.cpp', '''        const std::string name("rockchip");
        int drmFd = open("/dev/dri/card0", O_RDWR | O_CLOEXEC); // drmOpen(name.c_str(), nullptr);''',
        '''        char node[64] = {};
        const std::string name("internal DSI display");
        int drmFd = OhosOpenInternalDrm(node, sizeof(node));''')
replace('composer/src/drm_device.cpp', 'DISPLAY_LOGD("the drm fd is %{public}d", drmFd);',
        'DISPLAY_LOGI("using %{public}s fd %{public}d", node, drmFd);')
replace('buffer/sweet_buffer_vdi.cpp', '#include "sweet_log.h"',
        '#include "sweet_log.h"\n#include "ohos_drm_device.h"')
p = target / 'buffer/sweet_buffer_vdi.cpp'
data = p.read_text()
start = data.index('int DrmFd()\n{')
end = data.index('\nstruct MetaKey', start)
data = data[:start] + '''int DrmFd()
{
    static int fd = -1;
    static std::mutex lock;
    std::lock_guard<std::mutex> guard(lock);
    if (fd >= 0) return fd;
    char node[64] = {};
    fd = OhosOpenInternalDrm(node, sizeof(node));
    if (fd >= 0) {
        if (drmIsMaster(fd)) drmDropMaster(fd);
        SLOGI("using %{public}s fd %{public}d", node, fd);
    } else {
        SLOGE("internal DSI primary with dumb buffers unavailable: %{public}d", errno);
    }
    /* Retry a failed discovery on the next allocation: DRM may appear late. */
    return fd;
}
''' + data[end:]
p.write_text(data)
replace('composer/src/hdi_drm_composition.cpp', '    int w = 1080, h = 2400;', '''    int w = 0, h = 0;
    drmModeCrtc *active = drmModeGetCrtc(fd, mCrtc->GetId());
    if (active) {
        if (active->mode_valid) { w = active->mode.hdisplay; h = active->mode.vdisplay; }
        drmModeFreeCrtc(active);
    }''')
replace('composer/src/hdi_drm_composition.cpp',
        '    if (!mCompLayers.empty() && mCompLayers[0]->GetCurrentBuffer() != nullptr) {',
        '    if ((w <= 0 || h <= 0) && !mCompLayers.empty() && mCompLayers[0]->GetCurrentBuffer() != nullptr) {')
replace('composer/src/hdi_drm_composition.cpp', '    if (blackFb == 0 || bw != w || bh != h) {', '''    if (w <= 0 || h <= 0) {
        DISPLAY_LOGE("blank: active mode dimensions unavailable");
        return;
    }
    if (blackFb == 0 || bw != w || bh != h) {''')

# The donor's synthetic mode 1 and half-vblank trick are specific to sweet's
# single 120 Hz mode. OP13 capture shows real 60/90/120 Hz modes.
p = target / 'composer/src/drm_display.cpp'
data = p.read_text()
start = data.index('/*\n * sweet: the panel exposes one DRM mode')
end = data.index('\nint32_t DrmDisplay::GetDisplayPowerStatus', start)
data = data[:start] + '''// Expose only actual connector modes; IDs retain their DRM meaning.
int32_t DrmDisplay::GetDisplaySupportedModes(uint32_t *num, DisplayModeInfo *modes)
{
    return mConnector->GetDisplaySupportedModes(num, modes);
}

int32_t DrmDisplay::GetDisplayMode(uint32_t *modeId)
{
    DISPLAY_CHK_RETURN((modeId == nullptr), DISPLAY_NULL_PTR, DISPLAY_LOGE("modeId is null"));
    int32_t active = mCrtc->GetActiveModeId();
    DISPLAY_CHK_RETURN((active < 0), DISPLAY_FAILURE, DISPLAY_LOGE("no selected mode"));
    *modeId = static_cast<uint32_t>(active);
    return DISPLAY_SUCCESS;
}

int32_t DrmDisplay::SetDisplayMode(uint32_t modeId)
{
    DrmMode mode;
    if (mConnector->GetModeFromId(modeId, mode) != DISPLAY_SUCCESS) return DISPLAY_PARAM_ERR;
    DisplayModeInfo info{};
    mode.ConvertToHdiMode(info);
    if (!info.freshRate) return DISPLAY_PARAM_ERR;
    int32_t ret = mCrtc->SetActivieMode(modeId);
    if (ret == DISPLAY_SUCCESS) {
        g_hmosVsyncPeriodNs.store(1000000000ULL / info.freshRate);
        DISPLAY_LOGI("selected real mode %{public}u at %{public}u Hz", modeId, info.freshRate);
    }
    return ret;
}
''' + data[end:]
data = data.replace('extern std::atomic<int> g_hmosVirtualMode;',
                    'extern std::atomic<uint64_t> g_hmosVsyncPeriodNs;')
p.write_text(data)
replace('composer/src/drm_crtc.cpp',
        'DISPLAY_CHK_RETURN((id > 0), DISPLAY_PARAM_ERR, DISPLAY_LOGE("id %{public}d is invalid ", id));',
        'DISPLAY_CHK_RETURN((id < 0), DISPLAY_PARAM_ERR, DISPLAY_LOGE("id %{public}d is invalid ", id));')
replace('composer/src/hdi_drm_composition.cpp', 'std::atomic<int> g_hmosVirtualMode{0};',
        'std::atomic<uint64_t> g_hmosVsyncPeriodNs{16666667};')
p = target / 'composer/src/drm_vsync_worker.cpp'
data = p.read_text().replace('extern std::atomic<int> g_hmosVirtualMode;',
                           'extern std::atomic<uint64_t> g_hmosVsyncPeriodNs;')
data = data.replace('const uint64_t PERIOD = g_hmosVirtualMode.load() == 1 ? 16666667 : 8333333;',
                    'const uint64_t PERIOD = g_hmosVsyncPeriodNs.load();')
start = data.index('        if (!synthetic && g_hmosVirtualMode.load() == 1) {')
end = data.index('        if (mCallBack != nullptr)', start)
data = data[:start] + data[end:]
data = data.replace('        bool synthetic = (time == 0);\n', '')
data = data.replace('steady 120 Hz software vsync', 'software vsync at the selected refresh rate')
p.write_text(data)

diff = []
for path in sorted(target.rglob('*')):
    if not path.is_file(): continue
    name = path.relative_to(target)
    before_path = original / name
    before = before_path.read_text() if before_path.exists() else ''
    after = path.read_text()
    if before != after:
        diff.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                    fromfile='a/src/display/' + str(name) if before_path.exists() else '/dev/null',
                    tofile='b/src/display/' + str(name)))
(ROOT / 'port/display/0001-discover-internal-drm-and-active-mode.patch').write_text(''.join(diff))
print('Staged display changes; full HAL build and OP13 display test still required')
