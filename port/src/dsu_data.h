/* SPDX-License-Identifier: MIT
 * Persistent DSU data only. No physical-userdata fallback or formatter.
 * Uses the same exact AOSP userdata_gsi identity as the DSU probe.
 */
#ifndef HMOS_DSU_DATA_H
#define HMOS_DSU_DATA_H
static int mount_dsu_data(const char *node, const char *target)
{
    const char *prefix = "/dev/block/";
    if (strncmp(node, prefix, strlen(prefix)) || !dm_basename_valid(node + strlen(prefix))) {
        errno = EINVAL; return -1;
    }
    char path[256], name[64], numbers[64];
    const char *device = node + strlen(prefix);
    if (strlen(device) > 32) { errno = EINVAL; return -1; }
    snprintf(path, sizeof(path), "/sys/block/%.32s/dm/name", device);
    if (read_text(path, name, sizeof(name)) || !is_dsu_data(name)) { errno = ENODEV; return -1; }
    snprintf(path, sizeof(path), "/sys/block/%.32s/dev", device);
    unsigned int major_number, minor_number;
    if (read_text(path, numbers, sizeof(numbers)) ||
        sscanf(numbers, "%u:%u", &major_number, &minor_number) != 2) return -1;
    int fd = open(node, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    struct stat st;
    if (fd < 0) return -1;
    if (fstat(fd, &st) || !S_ISBLK(st.st_mode) ||
        st.st_rdev != makedev(major_number, minor_number)) {
        close(fd); errno = ENODEV; return -1;
    }
    /* Hold the verified node open across mounting. The first-stage device
       namespace is private and never exposed to HarmonyOS applications. */
    int result = mount(node, target, "ext4", MS_NOSUID | MS_NODEV, NULL);
    int saved = errno;
    close(fd);
    errno = saved;
    return result;
}
#endif
