/* SPDX-License-Identifier: MIT
 * DSU first-stage handoff and read-only HarmonyOS image-mount probe.
 * Deliberately stops before invoking donor init or any donor services.
 */
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <unistd.h>

/* Linux loop UAPI, kept local so cross-building only needs libc headers. */
#define LOOP_CTL_GET_FREE 0x4C82
#define LOOP_SET_FD 0x4C00
#define LOOP_CLR_FD 0x4C01
#define LOOP_SET_STATUS64 0x4C04
#define LO_FLAGS_READ_ONLY 1
struct loop_info64 {
    uint64_t device, inode, rdevice, offset, sizelimit;
    uint32_t number, encrypt_type, encrypt_key_size, flags;
    uint8_t file_name[64], crypt_name[64], encrypt_key[32];
    uint64_t init[2];
};
struct binder_feature_set { uint64_t feature_set; };
struct binderfs_device { char name[256]; uint32_t major, minor; };
#define BINDER_CTL_ADD _IOWR('b', 1, struct binderfs_device)
#define BINDER_FEATURE_SET _IOWR('b', 30, struct binder_feature_set)
#define TOKEN_GET _IOR('A', 1, unsigned long long)
#define TOKEN_SET _IOW('A', 2, unsigned long long)

static int klogfd = -1, pmsgfd = -1, reportfd = -1;
static int failures;

static void logmsg(const char *fmt, ...)
{
    char line[2048];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof(line), fmt, ap);
    va_end(ap);
    dprintf(STDERR_FILENO, "hmos-dsu: %s\n", line);
    if (klogfd >= 0) dprintf(klogfd, "<3>hmos-dsu: %s\n", line);
    if (pmsgfd >= 0) dprintf(pmsgfd, "hmos-dsu: %s\n", line);
    if (reportfd >= 0) dprintf(reportfd, "%s\n", line);
}

static int read_text(const char *path, char *buf, size_t len)
{
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    ssize_t n = read(fd, buf, len - 1);
    close(fd);
    if (n < 0) return -1;
    buf[n] = 0;
    while (n > 0 && (buf[n - 1] == '\n' || buf[n - 1] == '\r')) buf[--n] = 0;
    return 0;
}

static void dump_file(const char *path)
{
    char buf[16384];
    if (read_text(path, buf, sizeof(buf)) == 0) logmsg("%s:\n%s", path, buf);
    else logmsg("%s: %s", path, strerror(errno));
}

static void dump_dir(const char *path)
{
    DIR *d = opendir(path);
    struct dirent *e;
    if (!d) { logmsg("%s: %s", path, strerror(errno)); return; }
    while ((e = readdir(d))) {
        if (e->d_name[0] == '.') continue;
        logmsg("device %s/%s", path, e->d_name);
    }
    closedir(d);
}

static bool dm_basename_valid(const char *name)
{
    if (strncmp(name, "dm-", 3) || !name[3]) return false;
    for (const char *p = name + 3; *p; p++)
        if (*p < '0' || *p > '9') return false;
    return true;
}

static bool is_dsu_data(const char *name)
{
    /* Exact AOSP libgsi name; never fall back to physical userdata. */
    return !strcmp(name, "userdata_gsi");
}

static bool find_dsu(char *data_node, size_t data_len)
{
    bool system_found = false;
    DIR *d = opendir("/sys/block");
    struct dirent *e;
    if (!d) return false;
    while ((e = readdir(d))) {
        if (!dm_basename_valid(e->d_name)) continue;
        char path[512], name[256], dev[64];
        snprintf(path, sizeof(path), "/sys/block/%s/dm/name", e->d_name);
        if (read_text(path, name, sizeof(name))) continue;
        logmsg("mapper %s = %s", e->d_name, name);
        if (!strcmp(name, "system_gsi")) system_found = true;
        if (is_dsu_data(name)) {
            snprintf(path, sizeof(path), "/sys/block/%s/dev", e->d_name);
            if (read_text(path, dev, sizeof(dev))) continue;
            unsigned int maj, min;
            if (sscanf(dev, "%u:%u", &maj, &min) != 2) continue;
            int written = snprintf(data_node, data_len, "/dev/block/%.32s", e->d_name);
            if (written < 0 || (size_t)written >= data_len) { data_node[0] = 0; continue; }
            struct stat st;
            if (stat(data_node, &st) != 0) {
                if (mknod(data_node, S_IFBLK | 0600, makedev(maj, min))) data_node[0] = 0;
            } else if (!S_ISBLK(st.st_mode) || st.st_rdev != makedev(maj, min)) {
                data_node[0] = 0;
            }
        }
    }
    closedir(d);
    return system_found;
}

static void open_report(const char *data_node)
{
    if (!data_node[0]) { logmsg("No exact userdata_gsi mapping; data remains unmounted"); return; }
    mkdir("/data", 0771);
    /* Neither fsck nor mkfs: an uninitialised DSU data image is left alone. */
    if (mount(data_node, "/data", "ext4", MS_NOSUID | MS_NODEV, NULL) &&
        mount(data_node, "/data", "f2fs", MS_NOSUID | MS_NODEV, NULL)) {
        logmsg("DSU data mount unavailable: %s; using pmsg/kmsg", strerror(errno));
        return;
    }
    mkdir("/data/hmos-probe", 0700);
    reportfd = open("/data/hmos-probe/report.txt", O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0600);
    logmsg("Report opened on verified DSU mapping %s", data_node);
}

static void test_kernel(void)
{
    const char *gate = "/sys/module/access_tokenid/parameters/compat";
    int fd = open(gate, O_WRONLY | O_CLOEXEC);
    if (fd < 0 || write(fd, "1", 1) != 1) {
        logmsg("FAIL compatibility gate: %s (expected on unpatched stock kernel)", strerror(errno));
        failures++;
        if (fd >= 0) close(fd);
        return;
    }
    close(fd);
    int binder = open("/dev/binder", O_RDWR | O_CLOEXEC);
    if (binder < 0) binder = open("/dev/binderfs/binder", O_RDWR | O_CLOEXEC);
    if (binder < 0) {
        char major_minor[64];
        unsigned int maj, min;
        if (!read_text("/sys/class/misc/binder/dev", major_minor, sizeof(major_minor)) &&
            sscanf(major_minor, "%u:%u", &maj, &min) == 2) {
            mknod("/dev/hmos-probe-binder", S_IFCHR | 0600, makedev(maj, min));
            binder = open("/dev/hmos-probe-binder", O_RDWR | O_CLOEXEC);
        }
    }
    if (binder < 0) {
        /* Android's first stage has not created binderfs devices yet. */
        mkdir("/dev/hmos-binderfs", 0755);
        if (mount("binder", "/dev/hmos-binderfs", "binder", MS_NOSUID | MS_NOEXEC, NULL) == 0) {
            int ctl = open("/dev/hmos-binderfs/binder-control", O_RDWR | O_CLOEXEC);
            struct binderfs_device device = {.name = "probe"};
            if (ctl >= 0 && ioctl(ctl, BINDER_CTL_ADD, &device) == 0)
                binder = open("/dev/hmos-binderfs/probe", O_RDWR | O_CLOEXEC);
            if (ctl >= 0) close(ctl);
        }
    }
    struct binder_feature_set features = {0};
    if (binder < 0 || ioctl(binder, BINDER_FEATURE_SET, &features) || features.feature_set != 5) {
        logmsg("FAIL Binder feature query: mask=%llu error=%s", (unsigned long long)features.feature_set, strerror(errno));
        failures++;
    } else logmsg("PASS Binder feature query: token + sender-info mask=5");
    if (binder >= 0) close(binder);

    char mm[64];
    unsigned int maj, min;
    if (access("/dev/access_token_id", F_OK) &&
        !read_text("/sys/class/misc/access_token_id/dev", mm, sizeof(mm)) &&
        sscanf(mm, "%u:%u", &maj, &min) == 2)
        mknod("/dev/access_token_id", S_IFCHR | 0600, makedev(maj, min));
    fd = open("/dev/access_token_id", O_RDWR | O_CLOEXEC);
    unsigned long long old = 0, value = 0x0100000012345678ULL, readback = 0;
    bool saved = fd >= 0 && ioctl(fd, TOKEN_GET, &old) == 0;
    if (!saved || ioctl(fd, TOKEN_SET, &value) || ioctl(fd, TOKEN_GET, &readback) || readback != value) {
        logmsg("FAIL access-token round trip: %s", strerror(errno));
        failures++;
    } else logmsg("PASS access-token set/get round trip");
    if (saved) {
        pid_t child = fork();
        if (!child) {
            unsigned long long inherited = 0;
            _exit(ioctl(fd, TOKEN_GET, &inherited) || inherited != value);
        }
        int status = 0;
        if (child < 0 || waitpid(child, &status, 0) < 0 || !WIFEXITED(status) || WEXITSTATUS(status)) {
            failures++;
            logmsg("FAIL token inheritance");
        } else logmsg("PASS token inheritance");
        ioctl(fd, TOKEN_SET, &old);
    }
    if (fd >= 0) close(fd);
    fd = open(gate, O_WRONLY | O_CLOEXEC);
    if (fd >= 0) { write(fd, "0", 1); close(fd); }
}

static void mount_donor_images(void)
{
    static const char *parts[] = {"system", "vendor", "chip_prod", "sys_prod", "cust", "patch"};
    if (access("/hmos/images/system.img", R_OK)) {
        logmsg("Small probe image: donor payload not bundled");
        return;
    }
    mkdir("/mnt", 0755);
    if (mount("tmpfs", "/mnt", "tmpfs", MS_NOSUID | MS_NODEV, "mode=0755")) {
        logmsg("FAIL scratch tmpfs: %s", strerror(errno)); failures++; return;
    }
    int ctl = open("/dev/loop-control", O_RDWR | O_CLOEXEC);
    if (ctl < 0) {
        mknod("/dev/hmos-loop-control", S_IFCHR | 0600, makedev(10, 237));
        ctl = open("/dev/hmos-loop-control", O_RDWR | O_CLOEXEC);
    }
    for (size_t i = 0; i < sizeof(parts) / sizeof(parts[0]); i++) {
        char image[256], node[128], target[128];
        snprintf(image, sizeof(image), "/hmos/images/%s.img", parts[i]);
        snprintf(target, sizeof(target), "/mnt/%s", parts[i]);
        mkdir(target, 0755);
        int src = open(image, O_RDONLY | O_CLOEXEC);
        int num = ctl < 0 ? -1 : ioctl(ctl, LOOP_CTL_GET_FREE);
        snprintf(node, sizeof(node), "/dev/hmos-loop%d", num);
        if (num >= 0) mknod(node, S_IFBLK | 0600, makedev(7, num));
        int loop = num < 0 ? -1 : open(node, O_RDONLY | O_CLOEXEC);
        struct loop_info64 info = {.flags = LO_FLAGS_READ_ONLY};
        if (src < 0 || loop < 0 || ioctl(loop, LOOP_SET_FD, src) ||
            ioctl(loop, LOOP_SET_STATUS64, &info) ||
            mount(node, target, "erofs", MS_RDONLY | MS_NOSUID | MS_NODEV, NULL)) {
            logmsg("FAIL read-only %s mount: %s", parts[i], strerror(errno)); failures++;
        } else {
            logmsg("PASS read-only EROFS mount %s -> %s", image, target);
            if (i == 0) {
                logmsg("HarmonyOS system init present: %s", access("/mnt/system/system/bin/init", X_OK) ? "no" : "yes");
            }
        }
        if (loop >= 0) { umount(target); ioctl(loop, LOOP_CLR_FD, 0); close(loop); }
        if (src >= 0) close(src);
    }
    if (ctl >= 0) close(ctl);
}

static int selftest(void)
{
    if (!dm_basename_valid("dm-0") || !dm_basename_valid("dm-123") ||
        dm_basename_valid("dm-") || dm_basename_valid("../dm-0") || dm_basename_valid("dm-0/x") ||
        !is_dsu_data("userdata_gsi") || is_dsu_data("userdata") || is_dsu_data("userdata_a") ||
        is_dsu_data("foo_userdata_gsi") || sizeof(struct loop_info64) != 232) return 1;
    puts("PASS mapper identity checks and loop UAPI layout");
    return 0;
}

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--selftest")) return selftest();
    if (getpid() != 1) { fputs("DSU probe must run as PID 1; use --selftest for host checks\n", stderr); return 2; }
    klogfd = open("/dev/kmsg", O_WRONLY | O_CLOEXEC);
    pmsgfd = open("/dev/pmsg0", O_WRONLY | O_CLOEXEC);
    logmsg("BEGIN OP13 HarmonyOS DSU stage-1 probe; argc=%d arg1=%s", argc, argc > 1 ? argv[1] : "none");
    struct utsname uts;
    if (!uname(&uts)) logmsg("kernel %s %s", uts.release, uts.machine);
    char data_node[256] = {0};
    bool dsu_found = find_dsu(data_node, sizeof(data_node));
    if (!dsu_found) {
        logmsg("STOP: exact system_gsi mapping absent; no data mounts or kernel changes");
        failures++;
    } else {
        open_report(data_node);
        logmsg("PASS Android first-stage init reached DSU /system/bin/init as PID 1");
        dump_file("/proc/cmdline");
        dump_file("/proc/bootconfig");
        dump_file("/proc/mounts");
        dump_file("/proc/modules");
        dump_dir("/dev/dri"); dump_dir("/dev/dma_heap");
        dump_dir("/sys/class/drm"); dump_dir("/sys/class/backlight");
        dump_dir("/sys/class/input");
        logmsg("KGSL node present: %s", access("/dev/kgsl-3d0", F_OK) ? "no" : "yes");
        test_kernel();
        mount_donor_images();
    }
    logmsg("END failures=%d; donor init was not started; rebooting in 30 seconds", failures);
    if (reportfd >= 0) fsync(reportfd);
    sync();
    sleep(30);
    reboot(RB_AUTOBOOT);
    for (;;) { while (waitpid(-1, NULL, WNOHANG) > 0) {} sleep(1); }
}
