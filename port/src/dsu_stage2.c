/* SPDX-License-Identifier: MIT
 * DSU -> HarmonyOS init handoff, using isolated persistent DSU data.
 * No donor service graph, physical userdata mount, formatter, or misc writer.
 */
#define main probe_main
#include "dsu_probe.c"
#undef main
#include <signal.h>

static const char *newroot = "/mnt/hmos-root";
static int capture_ticks = 20;
static bool diagnostic_reboot = true;

static int prepare_ipc(void)
{
    /* Android first-stage init does not necessarily create these misc nodes. */
    char numbers[64];
    unsigned int major, minor;
    if (access("/dev/access_token_id", F_OK)) {
        if (read_text("/sys/class/misc/access_token_id/dev", numbers, sizeof(numbers)) ||
            sscanf(numbers, "%u:%u", &major, &minor) != 2 ||
            mknod("/dev/access_token_id", S_IFCHR | 0600, makedev(major, minor))) return -1;
    }
    int token = open("/dev/access_token_id", O_RDWR | O_CLOEXEC);
    unsigned long long current_token;
    if (token < 0) return -1;
    int token_result = ioctl(token, TOKEN_GET, &current_token);
    close(token);
    if (token_result) return -1;
    int binder = open("/dev/binder", O_RDWR | O_CLOEXEC);
    if (binder < 0) {
        mkdir("/dev/hmos-binderfs", 0755);
        if (mount("binder", "/dev/hmos-binderfs", "binder", MS_NOSUID | MS_NOEXEC, NULL) && errno != EBUSY)
            return -1;
        int control = open("/dev/hmos-binderfs/binder-control", O_RDWR | O_CLOEXEC);
        if (control < 0) return -1;
        const char *names[] = {"binder", "hwbinder", "vndbinder"};
        for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); i++) {
            struct binderfs_device device = {0};
            snprintf(device.name, sizeof(device.name), "%s", names[i]);
            char path[128], alias[128];
            snprintf(path, sizeof(path), "/dev/hmos-binderfs/%s", names[i]);
            snprintf(alias, sizeof(alias), "/dev/%s", names[i]);
            if (access(path, F_OK) && ioctl(control, BINDER_CTL_ADD, &device)) { close(control); return -1; }
            if (access(alias, F_OK)) {
                /* Bind the actual binderfs inode. A symlink gains the donor's
                   chr-device label but requires a separate lnk_file read
                   permission, which its service domains do not have. */
                int placeholder = open(alias, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
                if (placeholder < 0) { close(control); return -1; }
                close(placeholder);
                if (mount(path, alias, NULL, MS_BIND, NULL)) { close(control); return -1; }
                /* Match donor ueventd.config before the HarmonyOS policy is
                   loaded. Its init domain may relabel, but cannot chmod,
                   an already labeled Binder character device. */
                if (chmod(alias, 0666)) { close(control); return -1; }
            }
        }
        close(control);
        binder = open("/dev/binder", O_RDWR | O_CLOEXEC);
    }
    if (binder < 0) return -1;
    struct binder_feature_set features = {0};
    int result = ioctl(binder, BINDER_FEATURE_SET, &features);
    close(binder);
    if (result || features.feature_set != 5) { errno = EOPNOTSUPP; return -1; }
    logmsg("PASS native token device and HarmonyOS Binder feature mask=5");
    return 0;
}

static int loop_mount(const char *part, const char *target)
{
    char image[256], node[128];
    snprintf(image, sizeof(image), "/hmos/images/%s.img", part);
    int ctl = open("/dev/loop-control", O_RDWR | O_CLOEXEC);
    if (ctl < 0) {
        mknod("/dev/hmos-loop-control", S_IFCHR | 0600, makedev(10, 237));
        ctl = open("/dev/hmos-loop-control", O_RDWR | O_CLOEXEC);
    }
    int number = ctl < 0 ? -1 : ioctl(ctl, LOOP_CTL_GET_FREE);
    if (ctl >= 0) close(ctl);
    if (number < 0) return -1;
    snprintf(node, sizeof(node), "/dev/hmos-stage2-loop%d", number);
    if (mknod(node, S_IFBLK | 0600, makedev(7, number)) && errno != EEXIST) return -1;
    int loop = open(node, O_RDONLY | O_CLOEXEC);
    int src = open(image, O_RDONLY | O_CLOEXEC);
    struct loop_info64 info = {.flags = LO_FLAGS_READ_ONLY};
    int result = -1;
    if (loop >= 0 && src >= 0 && ioctl(loop, LOOP_SET_FD, src) == 0 &&
        ioctl(loop, LOOP_SET_STATUS64, &info) == 0 &&
        mount(node, target, "erofs", MS_RDONLY | MS_NOSUID | MS_NODEV, NULL) == 0) result = 0;
    if (result && loop >= 0) ioctl(loop, LOOP_CLR_FD, 0);
    if (src >= 0) close(src);
    if (loop >= 0) close(loop);
    logmsg("stage2 mount %s -> %s: %s", part, target, result ? strerror(errno) : "read-only");
    return result;
}

static int root_mount(const char *source, const char *relative, const char *type,
                      unsigned long flags, const char *options)
{
    char target[512];
    snprintf(target, sizeof(target), "%s%s", newroot, relative);
    struct stat st;
    if (stat(target, &st) || !S_ISDIR(st.st_mode)) return -1;
    if (mount(source, target, type, flags, options)) {
        logmsg("FAIL root mount %s: %s", relative, strerror(errno)); return -1;
    }
    return 0;
}

static int mask_dir(const char *relative)
{
    char target[512];
    snprintf(target, sizeof(target), "%s%s", newroot, relative);
    struct stat st;
    if (stat(target, &st)) return errno == ENOENT ? 0 : -1;
    return root_mount("tmpfs", relative, "tmpfs", MS_NOSUID | MS_NODEV | MS_NOEXEC,
                      "mode=0555,size=1M");
}

static int display_overrides(void)
{
    const char *libraries[] = {"libdisplay_buffer_vdi_impl.z.so", "libdisplay_composer_vdi_impl.z.so"};
    for (size_t i = 0; i < sizeof(libraries) / sizeof(libraries[0]); i++) {
        char source[512], target[512];
        snprintf(source, sizeof(source), "/hmos/overrides/vendor/lib64/%s", libraries[i]);
        if (access(source, R_OK)) {
            if (errno == ENOENT) continue;
            return -1;
        }
        snprintf(target, sizeof(target), "%s/vendor/lib64/%s", newroot, libraries[i]);
        struct stat source_stat, target_stat;
        if (stat(source, &source_stat) || stat(target, &target_stat) ||
            !S_ISREG(source_stat.st_mode) || !S_ISREG(target_stat.st_mode)) { errno = EINVAL; return -1; }
        if (mount(source, target, NULL, MS_BIND, NULL)) return -1;
        logmsg("read-only display override: %s", libraries[i]);
    }
    return 0;
}

static int ui_overrides(void)
{
    /* Install the curated etc tree AFTER masking donor configuration. Binding
       individual files before the mask hid them again. This tree contains no
       init directory, imports, or donor hardware startup configuration. */
    if (root_mount("/hmos/overrides/sys_prod/etc", "/sys_prod/etc", NULL, MS_BIND, NULL) ||
        root_mount(NULL, "/sys_prod/etc", NULL,
                   MS_REMOUNT | MS_BIND | MS_RDONLY | MS_NOSUID | MS_NODEV, NULL)) return -1;
    const char *paths[] = {
        "/sys_prod/etc/window/resources/display_manager_config.xml",
        "/sys_prod/etc/graphic/hgm_policy_config.xml"
    };
    for (size_t i = 0; i < sizeof(paths) / sizeof(paths[0]); i++) {
        char source[512], target[512];
        snprintf(source, sizeof(source), "/hmos/overrides%s", paths[i]);
        snprintf(target, sizeof(target), "%s%s", newroot, paths[i]);
        struct stat source_stat, target_stat;
        if (stat(source, &source_stat) || stat(target, &target_stat) ||
            !S_ISREG(source_stat.st_mode) || !S_ISREG(target_stat.st_mode)) return -1;
        if (source_stat.st_dev != target_stat.st_dev || source_stat.st_ino != target_stat.st_ino)
            { errno = EINVAL; return -1; }
        logmsg("read-only OP13 UI override: %s", paths[i]);
    }
    return 0;
}

#include "native_framework.h"
#include "vendor_layout.h"

static _Noreturn void stop_boot(const char *reason)
{
    logmsg("STOP stage2: %s (%s); requesting reboot in 30 seconds", reason, strerror(errno));
    sleep(30);
    reboot(RB_AUTOBOOT);
    for (;;) sleep(1);
}

static void start_capture(void)
{
    pid_t child = fork();
    if (child < 0) stop_boot("capture worker fork");
    if (child) return;
    int reader = open("/dev/kmsg", O_RDONLY | O_NONBLOCK | O_CLOEXEC);
    if (reader >= 0) lseek(reader, 0, SEEK_END);
    size_t captured = 0;
    pid_t hilog_child = -1;
    int hilog_tick = -1;
    char marker[256], path[512];
    snprintf(path, sizeof(path), "%s/dev/hmos-init-stage2", newroot);
    for (int tick = 0; tick < capture_ticks; tick++) {
        sleep(2);
        if (hilog_child > 0) {
            pid_t reaped = waitpid(hilog_child, NULL, WNOHANG);
            if (reaped != 0) hilog_child = -1;
            else if (tick - hilog_tick >= 2) {
                kill(hilog_child, SIGKILL);
                waitpid(hilog_child, NULL, 0);
                hilog_child = -1;
            }
        }
        if ((tick == 3 || tick == 13) && hilog_child < 0 && pmsgfd >= 0) {
            hilog_child = fork();
            if (hilog_child == 0) {
                dup2(pmsgfd, STDOUT_FILENO);
                dup2(pmsgfd, STDERR_FILENO);
                if (chroot(newroot) || chdir("/")) _exit(125);
                char *const args[] = {"/system/bin/hilog", "-x", NULL};
                execv(args[0], args);
                _exit(126);
            }
            hilog_tick = tick;
        }
        if (!read_text(path, marker, sizeof(marker)) && marker[0])
            logmsg("HarmonyOS init marker: %s", marker);
        if (reader >= 0 && pmsgfd >= 0 && captured < 65536) {
            char record[4096];
            ssize_t length;
            while (captured < 65536 && (length = read(reader, record, sizeof(record) - 1)) > 0) {
                record[length] = 0;
                if (strstr(record, "[Init]") || strstr(record, "[PARAM]") ||
                    strstr(record, "[SELINUX]") || strstr(record, "Error loading")) {
                    /* Do not write forwarded records back to kmsg: that loops. */
                    dprintf(pmsgfd, "hmos-stage2-kmsg: %s\n", record);
                    captured += (size_t)length;
                }
            }
        }
    }
    if (!diagnostic_reboot) {
        logmsg("startup log capture ended; HarmonyOS continues running");
        _exit(0);
    }
    logmsg("diagnostic smoke-test interval ended; requesting ordinary reboot");
    sync();
    reboot(RB_AUTOBOOT);
    _exit(1);
}

#ifndef STAGE2_ENTRY
#define STAGE2_ENTRY main
#endif
int STAGE2_ENTRY(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--selftest")) return selftest();
    if (getpid() != 1) { fputs("stage2 requires PID 1\n", stderr); return 2; }
    klogfd = open("/dev/kmsg", O_WRONLY | O_CLOEXEC);
    pmsgfd = open("/dev/pmsg0", O_WRONLY | O_CLOEXEC);
    char profile[64];
    if (read_text("/hmos/bootstrap/profile", profile, sizeof(profile))) stop_boot("bootstrap profile missing");
    bool framework = !strcmp(profile, "framework");
    if (!framework && strcmp(profile, "minimal") && strcmp(profile, "logging") && strcmp(profile, "core")) stop_boot("unsupported bootstrap profile");
    if (framework) { capture_ticks = 60; diagnostic_reboot = false; }
    logmsg("BEGIN HarmonyOS DSU stage2: profile=%s; data=%s", profile,
           framework ? "persistent userdata_gsi" : "diagnostic RAM");
    char dsu_data[256] = {0};
    if (!find_dsu(dsu_data, sizeof(dsu_data))) stop_boot("exact system_gsi mapping missing");
    if (framework && !dsu_data[0]) stop_boot("exact userdata_gsi mapping missing");
    if (framework && !access("/sys/fs/selinux/class/process/index", F_OK)) stop_boot("an existing policy is already loaded");
    /* No data mount, filesystem check/repair, or formatting here. */
    int gate = open("/sys/module/access_tokenid/parameters/compat", O_WRONLY | O_CLOEXEC);
    if (gate < 0 || write(gate, "1", 1) != 1) stop_boot("HarmonyOS kernel extensions missing");
    close(gate);
    if (mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL)) stop_boot("private mount propagation");
    if (prepare_ipc()) stop_boot("token/Binder device setup");
    mkdir("/mnt", 0755);
    if (mount("tmpfs", "/mnt", "tmpfs", MS_NOSUID | MS_NODEV, "mode=0755,size=16M")) stop_boot("scratch mount");
    mkdir(newroot, 0755);
    if (framework) {
        if (mkdir("/mnt/hmos-system", 0755) || loop_mount("system", "/mnt/hmos-system") ||
            system_root_view("/mnt/hmos-system")) stop_boot("HarmonyOS system root view");
    } else if (loop_mount("system", newroot)) stop_boot("system image mount");
    static const struct { const char *part, *target; } parts[] = {
        {"vendor", "/vendor"}, {"chip_prod", "/chip_prod"},
        {"sys_prod", "/sys_prod"}, {"cust", "/cust"}, {"patch", "/patch_hw"},
    };
    for (size_t i = 0; i < sizeof(parts) / sizeof(parts[0]); i++) {
        char target[512];
        snprintf(target, sizeof(target), "%s%s", newroot, parts[i].target);
        const char *part = framework && !strcmp(parts[i].part, "vendor") ? "op13_vendor" : parts[i].part;
        if (loop_mount(part, target)) stop_boot("read-only partition mount");
    }
    if (framework) {
        char odm[512];
        snprintf(odm, sizeof(odm), "%s/odm", newroot);
        if (loop_mount("op13_odm", odm) || mkdir("/mnt/hmos-vendor-runtime", 0755) ||
            loop_mount("vendor", "/mnt/hmos-vendor-runtime") ||
            ohos_vendor_runtime("/mnt/hmos-vendor-runtime")) stop_boot("OP13 vendor/odm and OHOS runtime layout");
        logmsg("OP13 vendor/odm base; separate OHOS bin/lib64 runtime; no Android HAL startup");
    }
    if (display_overrides()) stop_boot("display library overrides");
    if (root_mount("/hmos/bootstrap/etc", "/system/etc", NULL, MS_BIND, NULL)) stop_boot("minimal init config");
    /* Minimal init profile: no external init modules, policy-loader module,
       hardware autorun/reboot plugins, or non-system config layers. */
    const char *masks[] = {"/system/lib64/init",
                          "/vendor/etc", "/chip_prod/etc", "/sys_prod/etc", "/cust/etc", "/patch_hw/etc"};
    for (size_t i = 0; i < sizeof(masks) / sizeof(masks[0]); i++)
        if (mask_dir(masks[i])) stop_boot("config/plugin mask");
    if (framework) {
        const char *sources[] = {"/hmos/bootstrap/init_modules", "/hmos/bootstrap/vendor_etc"};
        const char *targets[] = {"/system/lib64/init", "/vendor/etc"};
        for (size_t i = 0; i < sizeof(sources) / sizeof(sources[0]); i++)
            if (root_mount(sources[i], targets[i], NULL, MS_BIND, NULL) ||
                root_mount(NULL, targets[i], NULL, MS_REMOUNT | MS_BIND | MS_RDONLY | MS_NOSUID | MS_NODEV, NULL))
                stop_boot("native framework configuration bind");
    }
    if (ui_overrides()) stop_boot("OP13 UI configuration overrides");
    if (framework) {
        if (native_devices()) stop_boot("private framework devices");
    } else {
        if (root_mount("/dev", "/dev", NULL, MS_BIND | MS_REC, NULL)) stop_boot("device bind");
        if (mask_dir("/dev/block")) stop_boot("physical block-device mask");
    }
    if (root_mount("proc", "/proc", "proc", MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL)) stop_boot("proc");
    if (root_mount("/sys", "/sys", NULL, MS_BIND, NULL) ||
        root_mount(NULL, "/sys", NULL, MS_REMOUNT | MS_BIND | MS_RDONLY, NULL)) stop_boot("read-only sysfs");
    if (framework) {
        char data_target[512];
        snprintf(data_target, sizeof(data_target), "%s/data", newroot);
        if (root_mount("tmpfs", "/storage", "tmpfs", MS_NOSUID | MS_NODEV, "mode=0755,size=16M") ||
            root_mount("tmpfs", "/mnt", "tmpfs", MS_NOSUID | MS_NODEV, "mode=0755,size=16M") ||
            mount_dsu_data(dsu_data, data_target)) stop_boot("persistent DSU data mount (ext4 required; never formatted here)");
        native_persistent_data = true;
    } else if (root_mount("tmpfs", "/data", "tmpfs", MS_NOSUID | MS_NODEV,
                          "mode=0771,size=256M")) stop_boot("RAM-only data");
    /* The system EROFS /metadata path is deliberately never connected to
       Android metadata. The donor graph contains no storage or misc service. */
    char marker_path[512];
    snprintf(marker_path, sizeof(marker_path), "%s/dev/hmos-init-stage2", newroot);
    int marker = open(marker_path, O_CREAT | O_TRUNC | O_WRONLY | O_CLOEXEC, 0600);
    if (marker < 0) stop_boot("marker file");
    close(marker);
    if (framework && native_policy_and_storage()) stop_boot("native policy/storage preparation");
    start_capture();
    if (framework && native_context("u:r:kernel:s0")) stop_boot("initial native init context");
    if (chroot(newroot) || chdir("/")) stop_boot("chroot");
    clearenv();
    setenv("PATH", "/system/bin:/vendor/bin", 1);
    logmsg("exec real HarmonyOS init --second-stage; data=%s",
           framework ? "persistent DSU filesystem" : "temporary diagnostic RAM");
    char *const init_args[] = {"/system/bin/init", "--second-stage", "0", NULL};
    execv(init_args[0], init_args);
    stop_boot("exec HarmonyOS init");
}
