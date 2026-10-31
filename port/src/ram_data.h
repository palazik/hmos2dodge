/* SPDX-License-Identifier: MIT
 * Shared experimental /data helper. Backing storage must be a regular file
 * on tmpfs/ramfs; physical filesystems and block devices are rejected.
 */
#ifndef HMOS_RAM_DATA_H
#define HMOS_RAM_DATA_H
#include <stdint.h>
#include <string.h>
#include <sys/vfs.h>
#ifndef LO_FLAGS_AUTOCLEAR
#define LO_FLAGS_AUTOCLEAR 4
#endif
struct hmos_ram_loop_info64 {
    uint64_t device, inode, rdevice, offset, sizelimit;
    uint32_t number, encrypt_type, encrypt_key_size, flags;
    uint8_t file_name[64], crypt_name[64], encrypt_key[32];
    uint64_t init[2];
};
_Static_assert(sizeof(struct hmos_ram_loop_info64) == 232, "loop_info64 UAPI size");

static int hmos_mount_ram_data(const char *backing, const char *target, const char *device_root)
{
    if (strlen(device_root) > 256) { errno = ENAMETOOLONG; return -1; }
    int image = open(backing, O_RDWR | O_CLOEXEC | O_NOFOLLOW);
    struct stat st;
    struct statfs fs;
    if (image < 0) return -1;
    if (fstat(image, &st) || !S_ISREG(st.st_mode) || st.st_size < 16 * 1024 * 1024 ||
        st.st_size > 2LL * 1024 * 1024 * 1024 || fstatfs(image, &fs) ||
        (fs.f_type != 0x01021994 && fs.f_type != 0x858458f6)) {
        close(image);
        errno = EINVAL;
        return -1;
    }
    char control_path[512];
    snprintf(control_path, sizeof(control_path), "%.*s/hmos-loop-control", 256, device_root);
    if (mknod(control_path, S_IFCHR | 0600, makedev(10, 237))) { close(image); return -1; }
    int control = open(control_path, O_RDWR | O_CLOEXEC | O_NOFOLLOW);
    int number = control < 0 ? -1 : ioctl(control, LOOP_CTL_GET_FREE);
    if (control >= 0) close(control);
    if (number < 0) { close(image); return -1; }
    char node[512];
    snprintf(node, sizeof(node), "%.*s/hmos-data-loop%d", 256, device_root, number);
    if (mknod(node, S_IFBLK | 0600, makedev(7, number))) { close(image); return -1; }
    int loop = open(node, O_RDWR | O_CLOEXEC | O_NOFOLLOW);
    struct hmos_ram_loop_info64 info = {.flags = LO_FLAGS_AUTOCLEAR};
    int result = -1;
    if (loop >= 0 && ioctl(loop, LOOP_SET_FD, image) == 0 &&
        ioctl(loop, LOOP_SET_STATUS64, &info) == 0 &&
        mount(node, target, "ext4", MS_NOSUID | MS_NODEV, NULL) == 0) result = 0;
    if (result && loop >= 0) ioctl(loop, LOOP_CLR_FD, 0);
    if (loop >= 0) close(loop);
    close(image);
    return result;
}
#endif
