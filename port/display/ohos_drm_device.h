/* SPDX-License-Identifier: Apache-2.0
 * Share the same internal-display selection between composer and allocator.
 */
#ifndef OHOS_DRM_DEVICE_H
#define OHOS_DRM_DEVICE_H
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
#include <xf86drm.h>
#include <xf86drmMode.h>

static inline int OhosOpenInternalDrm(char *selected, size_t selected_size)
{
    for (unsigned card = 0; card < 64; card++) {
        char path[64];
        snprintf(path, sizeof(path), "/dev/dri/card%u", card);
        int fd = open(path, O_RDWR | O_CLOEXEC);
        if (fd < 0) continue;
        uint64_t dumb = 0;
        if (drmGetCap(fd, DRM_CAP_DUMB_BUFFER, &dumb) || !dumb) {
            close(fd);
            continue;
        }
        drmModeRes *resources = drmModeGetResources(fd);
        int internal = 0;
        if (resources) {
            for (int index = 0; index < resources->count_connectors; index++) {
                drmModeConnector *connector = drmModeGetConnector(fd, resources->connectors[index]);
                if (!connector) continue;
                internal = connector->connector_type == DRM_MODE_CONNECTOR_DSI &&
                           connector->connection == DRM_MODE_CONNECTED && connector->count_modes > 0;
                drmModeFreeConnector(connector);
                if (internal) break;
            }
            drmModeFreeResources(resources);
        }
        if (internal) {
            if (selected && selected_size) snprintf(selected, selected_size, "%s", path);
            return fd;
        }
        close(fd);
    }
    errno = ENODEV;
    return -1;
}
#endif
