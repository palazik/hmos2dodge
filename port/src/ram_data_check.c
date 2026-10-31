/* SPDX-License-Identifier: MIT
 * Negative tests only on the host. The positive loop/mount path runs in the
 * diskless kernel guest, never against host devices.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/loop.h>
#include <stdio.h>
#include <stddef.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>
#include "ram_data.h"
_Static_assert(sizeof(struct hmos_ram_loop_info64) == sizeof(struct loop_info64), "host loop UAPI size");
_Static_assert(offsetof(struct hmos_ram_loop_info64, flags) == offsetof(struct loop_info64, lo_flags),
               "host loop UAPI flags offset");

static int reject(const char *path)
{
    errno = 0;
    int result = hmos_mount_ram_data(path, "/unused-hmos-data-target", "/missing-hmos-test-device-directory");
    if (result != -1 || errno != EINVAL) {
        fprintf(stderr, "Unexpected RAM-data rejection result for %s: %d errno=%d\n", path, result, errno);
        return 1;
    }
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    struct statfs fs;
    struct stat st;
    if (statfs(argv[1], &fs) || stat(argv[1], &st) || !S_ISREG(st.st_mode) ||
        st.st_size != 16 * 1024 * 1024 || fs.f_type == 0x01021994 || fs.f_type == 0x858458f6) {
        fputs("The negative fixture must be a 16 MiB regular file on a non-RAM filesystem\n", stderr);
        return 2;
    }
    if (reject(argv[1]) || reject("/dev/null")) return 1;
    puts("PASS physical-filesystem backing and non-regular device rejected before loop setup");
    return 0;
}
