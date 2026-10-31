/* SPDX-License-Identifier: MIT
 * Run only in the disposable chroot created by test_stage2_mounts.sh.
 */
#define STAGE2_ENTRY stage2_main
#include "dsu_stage2.c"

int main(void)
{
    const char *rejected_data[] = {"/dev/block/by-name/userdata", "/dev/block/sda",
                                    "/dev/block/dm-0/../userdata", "/tmp/userdata_gsi"};
    for (size_t i = 0; i < sizeof(rejected_data) / sizeof(rejected_data[0]); i++) {
        errno = 0;
        if (mount_dsu_data(rejected_data[i], "/unused") != -1 || errno != EINVAL) return 18;
    }
    if (mount_dsu_data("/dev/block/dm-999999", "/unused") != -1 || errno != ENODEV) return 19;
    puts("PASS: physical userdata aliases and unverified DSU devices rejected before mounting");
    newroot = "/donor";
    if (system_root_view("/source") ||
        readonly_bind("/stock/vendor", "/donor/vendor") ||
        readonly_bind("/stock/odm", "/donor/odm") ||
        ohos_vendor_runtime("/ohos-runtime")) {
        perror("OP13 vendor/ODM layout"); return 10;
    }
    const char *hardware_paths[] = {"/donor/vendor/firmware/op13.bin", "/donor/odm/op13.cfg"};
    for (size_t i = 0; i < sizeof(hardware_paths) / sizeof(hardware_paths[0]); i++) {
        char text[64];
        if (read_text(hardware_paths[i], text, sizeof(text)) || strcmp(text, "op13-stock")) return 11;
        int fd = open(hardware_paths[i], O_WRONLY);
        if (fd >= 0) { close(fd); return 12; }
        if (errno != EROFS) return 13;
    }
    char runtime[64];
    if (read_text("/donor/vendor/lib64/libhdi-test.so", runtime, sizeof(runtime)) ||
        strcmp(runtime, "ohos-runtime") ||
        access("/donor/vendor/lib64/libandroid-test.so", F_OK) == 0 ||
        access("/source/vendor/firmware/op13.bin", F_OK) == 0 ||
        access("/source/odm", F_OK) == 0) return 14;
    if (mask_dir("/vendor/etc") || access("/donor/vendor/etc/init/stock.rc", F_OK) == 0) return 15;
    int native_fd = open("/donor/vendor/lib64/libhdi-test.so", O_WRONLY);
    if (native_fd >= 0) { close(native_fd); return 16; }
    if (errno != EROFS) return 17;
    puts("PASS: OP13 firmware/ODM retained read-only; OHOS runtime isolated from Android libraries; source root unchanged");
    /* Reproduce the donor configuration mask, then exercise the actual helper. */
    if (mask_dir("/sys_prod/etc") || ui_overrides()) {
        perror("stage2 configuration mounts"); return 1;
    }
    if (access("/donor/sys_prod/etc/init/unsafe.cfg", F_OK) == 0) return 2;
    const char *paths[] = {
        "/donor/sys_prod/etc/window/resources/display_manager_config.xml",
        "/donor/sys_prod/etc/graphic/hgm_policy_config.xml"
    };
    for (size_t i = 0; i < sizeof(paths) / sizeof(paths[0]); i++) {
        int fd = open(paths[i], O_WRONLY);
        if (fd >= 0) { close(fd); return 3; }
        if (errno != EROFS) return 4;
        char text[64];
        if (read_text(paths[i], text, sizeof(text)) || strcmp(text, "op13-config")) return 5;
    }
    puts("PASS: actual stage2 mounts expose both OP13 configs read-only and hide donor init");
    return 0;
}
