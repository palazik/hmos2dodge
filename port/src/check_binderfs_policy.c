/* SPDX-License-Identifier: Apache-2.0
 * libsepol userspace policy query; does not touch the kernel policy.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sepol/sepol.h>
#include <sepol/policydb/services.h>

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    FILE *policy = fopen(argv[1], "rb");
    if (!policy) return 3;
    int status = sepol_set_policydb_from_file(policy);
    fclose(policy);
    if (status) return 4;
    const char *paths[] = {"/", "/binder", "/hwbinder", "/vndbinder"};
    const char *types[] = {"dev_file", "dev_binder_file", "dev_hwbinder_file", "dev_vndbinder_file"};
    puts("{");
    for (size_t i = 0; i < 4; i++) {
        sepol_security_class_t cls;
        sepol_security_id_t sid;
        char *context = NULL;
        size_t length = 0;
        if (sepol_string_to_security_class(i ? "chr_file" : "dir", &cls) ||
            sepol_genfs_sid("binder", paths[i], cls, &sid) ||
            sepol_sid_to_context(sid, &context, &length)) return 5;
        char expected[128];
        snprintf(expected, sizeof(expected), "u:object_r:%s:s0", types[i]);
        if (strcmp(context, expected)) {
            fprintf(stderr, "%s: expected %s, got %s\n", paths[i], expected, context);
            free(context);
            return 6;
        }
        printf("  \"%s\": \"%s\"%s\n", paths[i], context, i == 3 ? "" : ",");
        free(context);
    }
    puts("}");
    return 0;
}
