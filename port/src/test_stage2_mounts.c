/* SPDX-License-Identifier: MIT
 * Run only in the disposable chroot created by test_stage2_mounts.sh.
 */
#define STAGE2_ENTRY stage2_main
#include "dsu_stage2.c"

int main(void)
{
    newroot = "/donor";
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
