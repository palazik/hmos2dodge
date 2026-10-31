/* SPDX-License-Identifier: MIT
 * Opt-in native framework setup. No physical userdata/block devices enter
 * the new /dev. Phone /data uses the exact persistent userdata_gsi mapping;
 * the RAM helper is retained only for the diskless test fixture.
 */
#ifndef HMOS_NATIVE_FRAMEWORK_H
#define HMOS_NATIVE_FRAMEWORK_H
#include <sys/xattr.h>
#include <sys/mman.h>
#include "native_storage.h"
#include "dsu_data.h"
static bool native_persistent_data;

static int native_node(const char *name, mode_t mode, dev_t device)
{
    char target[1024];
    snprintf(target, sizeof(target), "%s/dev/%s", newroot, name);
    return mknod(target, S_IFCHR | mode, device) || chmod(target, mode);
}

static int native_devices(void)
{
    if (root_mount("tmpfs", "/dev", "tmpfs", MS_NOSUID, "mode=0755,size=16M")) return -1;
    static const struct { const char *name; unsigned int major, minor; mode_t mode; } basic[] = {
        {"null", 1, 3, 0666}, {"zero", 1, 5, 0666}, {"random", 1, 8, 0666},
        {"urandom", 1, 9, 0666}, {"console", 5, 1, 0600}, {"kmsg", 1, 11, 0600}
    };
    for (size_t i = 0; i < sizeof(basic) / sizeof(basic[0]); i++)
        if (native_node(basic[i].name, basic[i].mode, makedev(basic[i].major, basic[i].minor))) return -1;
    const char *misc[] = {"access_token_id", "ashmem"};
    for (size_t i = 0; i < sizeof(misc) / sizeof(misc[0]); i++) {
        char path[256], numbers[64]; unsigned int major_number, minor_number;
        snprintf(path, sizeof(path), "/sys/class/misc/%s/dev", misc[i]);
        if (read_text(path, numbers, sizeof(numbers)) ||
            sscanf(numbers, "%u:%u", &major_number, &minor_number) != 2 ||
            native_node(misc[i], 0666, makedev(major_number, minor_number))) return -1;
    }
    char ashmem_path[1024];
    snprintf(ashmem_path, sizeof(ashmem_path), "%s/dev/ashmem", newroot);
    int ashmem = open(ashmem_path, O_RDWR | O_CLOEXEC);
    if (ashmem < 0 || ioctl(ashmem, _IOW(0x77, 3, size_t), (size_t)4096)) return -1;
    volatile unsigned int *shared = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, ashmem, 0);
    if (shared == MAP_FAILED) { close(ashmem); return -1; }
    *shared = 0x484d4f53;
    int shared_ok = *shared == 0x484d4f53;
    munmap((void *)shared, 4096); close(ashmem);
    if (!shared_ok) return -1;
    logmsg("native ashmem size ioctl and shared mapping passed");
    const char *binder[] = {"binder", "hwbinder", "vndbinder"};
    for (size_t i = 0; i < sizeof(binder) / sizeof(binder[0]); i++) {
        char source[256], target[1024]; struct stat st;
        snprintf(source, sizeof(source), "/dev/%s", binder[i]);
        snprintf(target, sizeof(target), "%s/dev/%s", newroot, binder[i]);
        if (stat(source, &st) || !S_ISCHR(st.st_mode)) return -1;
        int placeholder = open(target, O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0600);
        if (placeholder < 0) return -1;
        close(placeholder);
        if (mount(source, target, NULL, MS_BIND, NULL) || chmod(target, 0666)) return -1;
    }
    const char *directories[] = {"socket", "unix", "unix/socket", "__parameters__", "shm"};
    for (size_t i = 0; i < sizeof(directories) / sizeof(directories[0]); i++) {
        char target[1024];
        snprintf(target, sizeof(target), "%s/dev/%s", newroot, directories[i]);
        mode_t mode = i == 4 ? 01777 : 0755;
        if (mkdir(target, mode) || chmod(target, mode)) return -1;
    }
    char target[1024];
    snprintf(target, sizeof(target), "%s/dev/console", newroot);
    int console = open(target, O_RDWR | O_CLOEXEC);
    if (console < 0) return -1;
    dup2(console, STDIN_FILENO); dup2(console, STDOUT_FILENO); dup2(console, STDERR_FILENO);
    if (console > 2) close(console);
    snprintf(target, sizeof(target), "%s/dev/kmsg", newroot);
    if (klogfd >= 0) close(klogfd);
    klogfd = open(target, O_WRONLY | O_CLOEXEC);
    struct stat pmsg;
    if (!stat("/dev/pmsg0", &pmsg) && S_ISCHR(pmsg.st_mode)) {
        if (native_node("pmsg0", 0600, pmsg.st_rdev)) return -1;
        snprintf(target, sizeof(target), "%s/dev/pmsg0", newroot);
        if (pmsgfd >= 0) close(pmsgfd);
        pmsgfd = open(target, O_WRONLY | O_CLOEXEC);
    }
    /* No /dev/block, firmware/TEE nodes, module autoloading or raw-disk alias.
       Hardware exposure is deliberately not part of this framework profile. */
    return 0;
}

static inline int native_ram_data(void)
{
    if (root_mount("tmpfs", "/mnt", "tmpfs", MS_NOSUID | MS_NODEV, "mode=0755,size=256M")) return -1;
    char backing[1024], target[1024], devices[1024];
    snprintf(backing, sizeof(backing), "%s/mnt/hmos-data.ext4", newroot);
    snprintf(target, sizeof(target), "%s/data", newroot);
    snprintf(devices, sizeof(devices), "%s/dev", newroot);
    int source = open("/hmos/bootstrap/data.ext4", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    struct stat st;
    if (source < 0 || fstat(source, &st) || !S_ISREG(st.st_mode) || st.st_size != 128 * 1024 * 1024) {
        if (source >= 0) close(source);
        return -1;
    }
    int output = open(backing, O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (output < 0) { close(source); return -1; }
    char buffer[65536];
    ssize_t count;
    while ((count = read(source, buffer, sizeof(buffer))) != 0) {
        if (count < 0) { if (errno == EINTR) continue; close(source); close(output); return -1; }
        ssize_t written = 0;
        while (written < count) {
            ssize_t part = write(output, buffer + written, (size_t)(count - written));
            if (part < 0 && errno == EINTR) continue;
            if (part <= 0) { close(source); close(output); return -1; }
            written += part;
        }
    }
    close(source); close(output);
    return hmos_mount_ram_data(backing, target, devices);
}

static int native_context(const char *context)
{
    int fd = open("/proc/self/attr/current", O_WRONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    size_t length = strlen(context);
    int result = write(fd, context, length) == (ssize_t)length ? 0 : -1;
    close(fd);
    return result;
}

static int native_policy_and_storage(void)
{
    if (root_mount("selinuxfs", "/sys/fs/selinux", "selinuxfs", MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL)) return -1;
    char path[1024], enforce[16];
    snprintf(path, sizeof(path), "%s/sys/fs/selinux/enforce", newroot);
    if (read_text(path, enforce, sizeof(enforce)) || strcmp(enforce, "0")) return -1;
    snprintf(path, sizeof(path), "%s/sys/fs/selinux/class/process/index", newroot);
    if (!access(path, F_OK)) { errno = EBUSY; return -1; } /* never replace an existing Android policy */
    snprintf(path, sizeof(path), "%s/vendor/etc/selinux/prebuild_sepolicy/policy.31", newroot);
    int source = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    struct stat st;
    if (source < 0 || fstat(source, &st) || !S_ISREG(st.st_mode) || st.st_size < 1 || st.st_size > 16 * 1024 * 1024) {
        if (source >= 0) close(source);
        return -1;
    }
    char *policy = malloc((size_t)st.st_size);
    if (!policy) { close(source); return -1; }
    size_t total = 0;
    while (total < (size_t)st.st_size) {
        ssize_t count = read(source, policy + total, (size_t)st.st_size - total);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) { close(source); free(policy); return -1; }
        total += (size_t)count;
    }
    close(source);
    snprintf(path, sizeof(path), "%s/sys/fs/selinux/load", newroot);
    int loader = open(path, O_WRONLY | O_CLOEXEC);
    ssize_t loaded = loader < 0 ? -1 : write(loader, policy, total);
    if (loader >= 0) close(loader);
    free(policy);
    if (loaded != (ssize_t)total) return -1;
    snprintf(path, sizeof(path), "%s/mnt/hmos-data.ext4", newroot);
    const char label[] = "u:object_r:hmos_ram_data_file:s0";
    if ((!native_persistent_data && setxattr(path, "security.selinux", label, sizeof(label), 0)) ||
        hmos_provision_storage(newroot, "/hmos/bootstrap/data-directories") ||
        native_context("u:r:init:s0")) return -1;
    const char *paths[] = {"/system", "/vendor", "/dev", "/data", "/mnt", "/storage"};
    for (size_t i = 0; i < sizeof(paths) / sizeof(paths[0]); i++) {
        pid_t child = fork();
        if (!child) {
            if (chroot(newroot) || chdir("/")) _exit(125);
            clearenv(); setenv("PATH", "/system/bin:/vendor/bin", 1);
            char *const args[] = {"/system/bin/restorecon", (char *)paths[i], NULL};
            execv(args[0], args); _exit(126);
        }
        int status;
        if (child < 0 || waitpid(child, &status, 0) < 0 || !WIFEXITED(status) || WEXITSTATUS(status)) return -1;
    }
    snprintf(path, sizeof(path), "%s/mnt/hmos-data.ext4", newroot);
    if (!native_persistent_data && setxattr(path, "security.selinux", label, sizeof(label), 0)) return -1;
    logmsg("native framework %s storage and donor labels prepared; init will enable enforcing mode",
           native_persistent_data ? "persistent DSU" : "guest RAM");
    return 0;
}
#endif
