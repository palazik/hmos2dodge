/* SPDX-License-Identifier: Apache-2.0 */
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>

static int load_factory(const char *path, const char *create_name, const char *destroy_name)
{
    fprintf(stderr, "LOAD %s\n", path);
    void *library = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "FAIL dlopen %s: %s\n", path, dlerror()); return 1; }
    void *(*create)(void) = (void *(*)(void))dlsym(library, create_name);
    void (*destroy)(void *) = (void (*)(void *))dlsym(library, destroy_name);
    if (!create || !destroy) { fprintf(stderr, "FAIL factory exports: %s\n", path); return 1; }
    fprintf(stderr, "CREATE %s\n", path);
    void *instance = create();
    if (!instance) { fprintf(stderr, "FAIL factory returned null: %s\n", path); return 1; }
    fprintf(stderr, "DESTROY %s\n", path);
    destroy(instance);
    printf("PASS OHOS dynamic load and factory lifecycle: %s\n", path);
    fflush(stdout);
    /* This test keeps the HALs resident; unloading is a separate test case. */
    if (getenv("HMOS_DISPLAY_TEST_UNLOAD")) {
        fprintf(stderr, "UNLOAD %s\n", path);
        dlclose(library);
    }
    return 0;
}

int main(void)
{
    int result = load_factory("/vendor/lib64/libdisplay_buffer_vdi_impl.z.so", "CreateDisplayBufferVdi", "DestroyDisplayBufferVdi");
    result |= load_factory("/vendor/lib64/libdisplay_composer_vdi_impl.z.so", "CreateComposerVdiV1_1", "DestroyComposerVdiV1_1");
    return result;
}
