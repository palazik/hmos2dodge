/* SPDX-License-Identifier: MIT
 * OP13 hardware partitions with a separate OHOS-native vendor runtime.
 * All source trees remain read-only; no Android init/HAL service is started.
 */
#ifndef HMOS_VENDOR_LAYOUT_H
#define HMOS_VENDOR_LAYOUT_H

static int readonly_bind(const char *source, const char *target)
{
    return mount(source, target, NULL, MS_BIND, NULL) ||
        mount(NULL, target, NULL, MS_REMOUNT | MS_BIND | MS_RDONLY | MS_NOSUID | MS_NODEV, NULL);
}

/* The donor system root lacks /odm. Construct only a small root skeleton in
 * RAM, binding its existing directories/files without copying their contents.
 * This permits a real /odm mountpoint without editing the original image.
 */
static int system_root_view(const char *source)
{
    if (mount("tmpfs", newroot, "tmpfs", MS_NOSUID | MS_NODEV, "mode=0755,size=1M")) return -1;
    DIR *directory = opendir(source);
    if (!directory) return -1;
    struct dirent *entry;
    int result = 0;
    while ((entry = readdir(directory))) {
        if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..")) continue;
        char original[1024], target[1024]; struct stat st;
        int n = snprintf(original, sizeof(original), "%s/%s", source, entry->d_name);
        int m = snprintf(target, sizeof(target), "%s/%s", newroot, entry->d_name);
        if (n < 0 || n >= (int)sizeof(original) || m < 0 || m >= (int)sizeof(target) ||
            lstat(original, &st)) { result = -1; break; }
        if (S_ISLNK(st.st_mode)) {
            char link[4096];
            ssize_t size = readlink(original, link, sizeof(link) - 1);
            if (size < 0 || size == (ssize_t)sizeof(link) - 1) { result = -1; break; }
            link[size] = 0;
            if (symlink(link, target)) { result = -1; break; }
        } else if (S_ISDIR(st.st_mode)) {
            if (mkdir(target, st.st_mode & 0777) || readonly_bind(original, target)) { result = -1; break; }
        } else if (S_ISREG(st.st_mode)) {
            int fd = open(target, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
            if (fd < 0) { result = -1; break; }
            close(fd);
            if (readonly_bind(original, target)) { result = -1; break; }
        } else { errno = EINVAL; result = -1; break; }
    }
    closedir(directory);
    if (result) return -1;
    char odm[1024];
    snprintf(odm, sizeof(odm), "%s/odm", newroot);
    /* Refuse donor symlinks here rather than following them out of this root. */
    struct stat st;
    if (!lstat(odm, &st)) return S_ISDIR(st.st_mode) ? 0 : -1;
    if (errno != ENOENT) return -1;
    return mkdir(odm, 0755);
}

static int ohos_vendor_runtime(const char *source)
{
    /* Native OHOS libraries use musl/HDI, unlike OP13's Bionic/HIDL/AIDL
       libraries. Overlay their runtime directories; retain stock firmware,
       module and ODM assets. The curated /vendor/etc is installed later. */
    const char *directories[] = {"bin", "lib64"};
    for (size_t i = 0; i < sizeof(directories) / sizeof(directories[0]); i++) {
        char original[1024], target[1024];
        snprintf(original, sizeof(original), "%s/%s", source, directories[i]);
        snprintf(target, sizeof(target), "%s/vendor/%s", newroot, directories[i]);
        struct stat st;
        if (lstat(original, &st) || !S_ISDIR(st.st_mode) ||
            lstat(target, &st) || !S_ISDIR(st.st_mode) || readonly_bind(original, target)) return -1;
    }
    return 0;
}
#endif
