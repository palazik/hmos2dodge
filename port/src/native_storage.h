/* SPDX-License-Identifier: MIT */
#ifndef HMOS_NATIVE_STORAGE_H
#define HMOS_NATIVE_STORAGE_H
#include "ram_data.h"

static inline int hmos_provision_storage(const char *root, const char *manifest)
{
    FILE *directories = fopen(manifest, "r");
    if (!directories) return -1;
    char path[512], target[1024];
    unsigned int mode, uid, gid;
    while (fscanf(directories, "%511s %o %u %u", path, &mode, &uid, &gid) == 4) {
        int private_path = !strncmp(path, "/data/", 6) ||
                           !strcmp(path, "/mnt/sandbox") || !strncmp(path, "/mnt/sandbox/", 13) ||
                           !strcmp(path, "/mnt/startup") || !strncmp(path, "/mnt/startup/", 13);
        snprintf(target, sizeof(target), "%s%s", root, path);
        if (!private_path || strstr(path, "..") || mode > 07777 ||
            (mkdir(target, (mode_t)mode) && errno != EEXIST) ||
            chown(target, (uid_t)uid, (gid_t)gid) || chmod(target, (mode_t)mode)) {
            fclose(directories);
            return -1;
        }
    }
    if (!feof(directories)) { fclose(directories); return -1; }
    fclose(directories);
    /* Native token allocation happens before init jobs. This is the same
       donor account/group mapping used by the validated guest startup. */
    const char *parents[] = {"/data/service", "/data/service/el0"};
    for (size_t i = 0; i < sizeof(parents) / sizeof(parents[0]); i++) {
        snprintf(target, sizeof(target), "%s%s", root, parents[i]);
        if (mkdir(target, 0711) && errno != EEXIST) return -1;
    }
    snprintf(target, sizeof(target), "%s/data/service/el0/access_token", root);
    if ((mkdir(target, 0750) && errno != EEXIST) || chown(target, 0, 3020) || chmod(target, 0750)) return -1;
    snprintf(target, sizeof(target), "%s/data/service/el0/access_token/nativetoken.json", root);
    int token = open(target, O_CREAT | O_WRONLY | O_CLOEXEC | O_NOFOLLOW, 0660);
    if (token < 0) return -1;
    int result = fchmod(token, 0660);
    close(token);
    return result;
}
#endif
