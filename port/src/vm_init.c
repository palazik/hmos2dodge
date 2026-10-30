/* SPDX-License-Identifier: MIT
 * PID 1 for a diskless QEMU virt lab. This is never a phone boot entrypoint.
 */
#define STAGE2_ENTRY vm_unused_stage2_entry
#include "dsu_stage2.c"
#include <signal.h>
#include <sys/xattr.h>
#include <dirent.h>
#include <sys/ptrace.h>
#include <sys/uio.h>
#define LO_FLAGS_AUTOCLEAR 4 /* Linux loop UAPI */
static void vm_mount(const char *source, const char *target, const char *type);

static pid_t vm_traced[64];
static size_t vm_trace_count;

static void vm_trace_faults(void)
{
    DIR *proc = opendir("/proc");
    if (proc) {
        struct dirent *entry;
        while ((entry = readdir(proc)) && vm_trace_count < 64) {
            if (entry->d_name[0] < '0' || entry->d_name[0] > '9') continue;
            pid_t pid = (pid_t)strtol(entry->d_name, NULL, 10);
            bool known = false;
            for (size_t i = 0; i < vm_trace_count; i++) if (vm_traced[i] == pid) known = true;
            if (known) continue;
            char path[512], name[128];
            snprintf(path, sizeof(path), "/proc/%s/comm", entry->d_name);
            if (read_text(path, name, sizeof(name)) || strcmp(name, "appspawn")) continue;
            if (ptrace(PTRACE_SEIZE, pid, NULL, NULL) == 0) {
                vm_traced[vm_trace_count++] = pid;
                printf("VM-TRACE attached appspawn pid=%d\n", pid);
            }
        }
        closedir(proc);
    }
    for (size_t i = 0; i < vm_trace_count; i++) {
        pid_t pid = vm_traced[i];
        int status;
        if (pid <= 0 || waitpid(pid, &status, WNOHANG | 0x40000000) <= 0) continue;
        if (!WIFSTOPPED(status)) { vm_traced[i] = -1; continue; }
        int signal = WSTOPSIG(status);
        if (signal == SIGSEGV || signal == SIGABRT || signal == SIGSYS) {
            struct { uint64_t x[31], sp, pc, pstate; } registers = {0};
            struct iovec vector = {&registers, sizeof(registers)};
            if (!ptrace(PTRACE_GETREGSET, pid, (void *)1, &vector)) {
                printf("VM-TRACE fault pid=%d signal=%d pc=0x%llx sp=0x%llx lr=0x%llx x0=0x%llx x1=0x%llx\n",
                       pid, signal, (unsigned long long)registers.pc,
                       (unsigned long long)registers.sp, (unsigned long long)registers.x[30],
                       (unsigned long long)registers.x[0], (unsigned long long)registers.x[1]);
            }
            char path[128], line[1024];
            snprintf(path, sizeof(path), "/proc/%d/maps", pid);
            FILE *maps = fopen(path, "r");
            if (maps) {
                while (fgets(line, sizeof(line), maps)) {
                    unsigned long long start, end;
                    if (sscanf(line, "%llx-%llx", &start, &end) == 2 &&
                        ((registers.pc >= start && registers.pc < end) ||
                         (registers.x[30] >= start && registers.x[30] < end)))
                        printf("VM-TRACE map pid=%d %s", pid, line);
                }
                fclose(maps);
            }
            ptrace(PTRACE_DETACH, pid, NULL, (void *)(long)signal);
            vm_traced[i] = -1;
        } else {
            ptrace(PTRACE_CONT, pid, NULL, (void *)(long)signal);
        }
    }
}

static void vm_processes(void)
{
    DIR *proc = opendir("/proc");
    if (!proc) return;
    struct dirent *entry;
    while ((entry = readdir(proc))) {
        if (entry->d_name[0] < '0' || entry->d_name[0] > '9') continue;
        char path[512], name[128], content[2048];
        snprintf(path, sizeof(path), "/proc/%s/comm", entry->d_name);
        if (read_text(path, name, sizeof(name))) continue;
        snprintf(path, sizeof(path), "/proc/%s/cmdline", entry->d_name);
        if (read_text(path, content, sizeof(content))) continue;
        if (!strstr(content, "samgr") && !strstr(content, "sa_main") && !strstr(content, "accesstoken_service") && !strstr(content, "hilogd") && !strstr(content, "appspawn") && !strstr(content, "accountmgr")) continue;
        const char *files[] = {"status", "attr/current", "wchan"};
        for (size_t i = 0; i < sizeof(files) / sizeof(files[0]); i++) {
            snprintf(path, sizeof(path), "/proc/%s/%s", entry->d_name, files[i]);
            if (!read_text(path, content, sizeof(content)))
                printf("VM-PROCESS %s pid=%s %s: %s\n", name, entry->d_name, files[i], content);
        }
    }
    closedir(proc);
}

static void vm_fault_files(void)
{
    const char *folder = "/data/log/faultlog/temp";
    DIR *directory = opendir(folder);
    if (!directory) { perror("VM fault directory"); return; }
    struct dirent *entry;
    while ((entry = readdir(directory))) {
        if (entry->d_name[0] == '.') continue;
        char path[512], buffer[32768];
        snprintf(path, sizeof(path), "%s/%s", folder, entry->d_name);
        if (!read_text(path, buffer, sizeof(buffer)))
            printf("VM-FAULT %s\n%s\n", entry->d_name, buffer);
    }
    closedir(directory);
}

static void vm_capture(void)
{
    pid_t child = fork();
    if (child < 0) { perror("VM capture fork"); return; }
    if (child) return;
    int reader = open("/dev/kmsg", O_RDONLY | O_NONBLOCK | O_CLOEXEC);
    if (reader >= 0) lseek(reader, 0, SEEK_END);
    char profile[64];
    bool framework = !read_text("/vm/profile", profile, sizeof(profile)) && !strcmp(profile, "framework");
    int output[2];
    if (pipe2(output, O_NONBLOCK | O_CLOEXEC)) _exit(125);
    size_t total = 0;
    for (int tick = 0; tick < (framework ? 240 : 120); tick++) {
        usleep(500000);
        if (framework) vm_trace_faults();
        char diagnostic[4096];
        ssize_t bytes;
        while ((bytes = read(output[0], diagnostic, sizeof(diagnostic) - 1)) > 0) {
            diagnostic[bytes] = 0;
            fwrite(diagnostic, 1, (size_t)bytes, stdout);
        }
        if (reader >= 0 && total < 512 * 1024) {
            char buffer[4096];
            ssize_t count;
            while (total < 512 * 1024 && (count = read(reader, buffer, sizeof(buffer) - 1)) > 0) {
                buffer[count] = 0;
                if (strstr(buffer, "[Init]") || strstr(buffer, "[PARAM]") ||
                    strstr(buffer, "[SELINUX]") || strstr(buffer, "avc:") ||
                    strstr(buffer, "Error loading") || strstr(buffer, "selinux")) {
                    printf("VM-KMSG %s", buffer);
                    total += (size_t)count;
                }
            }
        }
        if (tick == 30 || tick == 90) {
            vm_processes();
            const char *commands[][5] = {
                {"/system/bin/param", "get", "bootevent.samgr.ready", NULL},
                {"/system/bin/param", "get", "accesstoken.permission.init", NULL},
                {"/system/bin/sa-query", NULL, NULL, NULL},
                {"/system/lib/ld-musl-aarch64.so.1", "/system/bin/hilog", "-x", NULL, NULL},
                {"/system/bin/param", "get", "bootevent.appspawn.started", NULL},
                {"/system/bin/sa-query", "200", NULL, NULL},
            };
            for (size_t i = 0; i < sizeof(commands) / sizeof(commands[0]); i++) {
                if (i >= 4 && !framework) continue;
                pid_t client = fork();
                if (!client) {
                    int flags = fcntl(output[1], F_GETFL);
                    fcntl(output[1], F_SETFL, flags & ~O_NONBLOCK);
                    dup2(output[1], STDOUT_FILENO); dup2(output[1], STDERR_FILENO);
                    int input = open("/dev/null", O_RDONLY);
                    if (input >= 0) dup2(input, STDIN_FILENO);
                    execv(commands[i][0], (char *const *)commands[i]); _exit(126);
                }
                if (client > 0) {
                    /* Reap asynchronously: a blocked client cannot stall the watchdog. */
                    waitpid(client, NULL, WNOHANG);
                }
            }
        }
    }
    if (framework) vm_fault_files();
    char enforce[16];
    if (!read_text("/sys/fs/selinux/enforce", enforce, sizeof(enforce)))
        printf("VM final SELinux enforce=%s\n", enforce);
    printf("VM runtime observation ended\n");
    sync();
    reboot(RB_POWER_OFF);
    _exit(0);
}

static int vm_private_devices(void)
{
    const char *names[] = {"null", "zero", "random", "urandom", "console", "kmsg", "access_token_id"};
    struct stat nodes[sizeof(names) / sizeof(names[0])];
    for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); i++) {
        char path[128];
        snprintf(path, sizeof(path), "/dev/%s", names[i]);
        if (stat(path, &nodes[i]) || !S_ISCHR(nodes[i].st_mode)) return -1;
    }
    /* HarmonyOS uses a tmpfs /dev. Its policy labels this filesystem as tmpfs;
       devtmpfs instead uses the different 'device' filesystem security type. */
    vm_mount("tmpfs", "/dev", "tmpfs");
    for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); i++) {
        char path[128];
        snprintf(path, sizeof(path), "/dev/%s", names[i]);
        mode_t mode = nodes[i].st_mode;
        if (i < 4) mode = S_IFCHR | 0666; /* donor ueventd: public basic devices */
        if (mknod(path, mode, nodes[i].st_rdev)) return -1;
    }
    mkdir("/dev/socket", 0755);
    mkdir("/dev/unix", 0755);
    mkdir("/dev/unix/socket", 0755);
    mkdir("/dev/__parameters__", 0771);
    mkdir("/dev/shm", 01777);
    int console = open("/dev/console", O_RDWR | O_CLOEXEC);
    if (console < 0) return -1;
    dup2(console, 0); dup2(console, 1); dup2(console, 2);
    if (console > 2) close(console);
    if (klogfd >= 0) close(klogfd);
    klogfd = open("/dev/kmsg", O_WRONLY | O_CLOEXEC);
    return 0;
}

static int vm_token_storage(void)
{
    FILE *directories = fopen("/vm/data-directories", "r");
    if (!directories) return -1;
    char path[512];
    unsigned int mode, uid, gid;
    while (fscanf(directories, "%511s %o %u %u", path, &mode, &uid, &gid) == 4) {
        bool private_path = !strncmp(path, "/data/", 6) ||
                            !strcmp(path, "/mnt/sandbox") || !strncmp(path, "/mnt/sandbox/", 13) ||
                            !strcmp(path, "/mnt/startup") || !strncmp(path, "/mnt/startup/", 13);
        if (!private_path || strstr(path, "..") || mode > 07777 ||
            (mkdir(path, (mode_t)mode) && errno != EEXIST) ||
            chown(path, (uid_t)uid, (gid_t)gid) || chmod(path, (mode_t)mode)) {
            fclose(directories);
            return -1;
        }
    }
    if (!feof(directories)) { fclose(directories); return -1; }
    fclose(directories);
    /* Native token allocation occurs while init reads services, before jobs.
       Provide its private RAM path before that allocation can persist JSON. */
    mkdir("/data/service", 0711);
    mkdir("/data/service/el0", 0711);
    mkdir("/data/service/el0/access_token", 0750);
    if (chown("/data/service/el0/access_token", 0, 3020)) return -1;
    int token_config = open("/data/service/el0/access_token/nativetoken.json",
                            O_CREAT | O_WRONLY | O_CLOEXEC, 0660);
    if (token_config < 0) return -1;
    close(token_config);
    return 0;
}

static int vm_restore_labels(void)
{
    /* newc initramfs strips EROFS SELinux xattrs. Restore the donor's labels
       before enabling enforcement, rather than grant rootfs access. The
       policy must be loaded first for tmpfs in-memory labels to work.
       This preparation is specific to the cpio lab, not the phone image. */
    char enforce[16];
    if (read_text("/sys/fs/selinux/enforce", enforce, sizeof(enforce)) || strcmp(enforce, "0") ||
        !access("/sys/fs/selinux/class/process/index", F_OK)) {
        puts("VM FAIL expected a fresh guest with no loaded policy");
        return -1;
    }
    int policy = open("/vendor/etc/selinux/prebuild_sepolicy/policy.31", O_RDONLY | O_CLOEXEC);
    struct stat st;
    if (policy < 0 || fstat(policy, &st) || st.st_size < 1 || st.st_size > 16 * 1024 * 1024)
        return -1;
    char *data = malloc((size_t)st.st_size);
    if (!data) { close(policy); return -1; }
    size_t consumed = 0;
    while (consumed < (size_t)st.st_size) {
        ssize_t count = read(policy, data + consumed, (size_t)st.st_size - consumed);
        if (count <= 0) { free(data); close(policy); return -1; }
        consumed += (size_t)count;
    }
    close(policy);
    int loader = open("/sys/fs/selinux/load", O_WRONLY | O_CLOEXEC);
    ssize_t loaded = loader < 0 ? -1 : write(loader, data, consumed);
    if (loader >= 0) close(loader);
    free(data);
    if (loaded != (ssize_t)consumed) { perror("VM initial policy load"); return -1; }
    const char backing_label[] = "u:object_r:vm_data_backing_file:s0";
    if (setxattr("/vm/data.ext4", "security.selinux", backing_label, sizeof(backing_label), 0) ||
        vm_token_storage()) return -1;
    int attr = open("/proc/self/attr/current", O_WRONLY | O_CLOEXEC);
    const char context[] = "u:r:init:s0";
    if (attr < 0 || write(attr, context, sizeof(context) - 1) != sizeof(context) - 1) return -1;
    close(attr);
    const char *paths[] = {"/system", "/vendor", "/dev", "/data", "/mnt", "/storage"};
    for (size_t i = 0; i < sizeof(paths) / sizeof(paths[0]); i++) {
        pid_t child = fork();
        if (!child) {
            char *const args[] = {"/system/bin/restorecon", (char *)paths[i], NULL};
            execv(args[0], args);
            _exit(126);
        }
        int status = 0;
        if (child < 0 || waitpid(child, &status, 0) < 0 || !WIFEXITED(status) || WEXITSTATUS(status)) {
            printf("VM FAIL pre-policy restorecon %s status=%d\n", paths[i], status);
            return -1;
        }
    }
    char label[256];
    ssize_t count = getxattr("/dev/kmsg", "security.selinux", label, sizeof(label) - 1);
    if (count <= 0) { perror("VM kmsg label readback"); return -1; }
    label[count] = 0;
    if (strcmp(label, "u:object_r:dev_kmsg_file:s0")) return -1;
    /* The original init enables enforcement in its early policy loader,
       before reading services. Its second-stage self-exec is an early-boot
       operation; the donor policy does not grant init a later self-exec. */
    printf("VM donor labels restored; original init will enable enforcement before service startup\n");
    return 0;
}

static void vm_mount(const char *source, const char *target, const char *type)
{
    mkdir(target, 0755);
    if (mount(source, target, type, MS_NOSUID, NULL)) {
        printf("VM FAIL mount %s: %s\n", target, strerror(errno));
        reboot(RB_POWER_OFF);
        for (;;) sleep(1);
    }
}

static int vm_data_mount(void)
{
    /* The backing file came from cpio and lives only in guest RAM. No QEMU
       drive, host directory or physical partition supplies this filesystem. */
    if (mknod("/dev/vm-loop-control", S_IFCHR | 0600, makedev(10, 237))) return -1;
    int control = open("/dev/vm-loop-control", O_RDWR | O_CLOEXEC);
    int number = control < 0 ? -1 : ioctl(control, LOOP_CTL_GET_FREE);
    if (control >= 0) close(control);
    if (number < 0) return -1;
    char node[128];
    snprintf(node, sizeof(node), "/dev/vm-data-loop%d", number);
    if (mknod(node, S_IFBLK | 0600, makedev(7, number))) return -1;
    int loop = open(node, O_RDWR | O_CLOEXEC);
    int image = open("/vm/data.ext4", O_RDWR | O_CLOEXEC);
    struct loop_info64 info = {.flags = LO_FLAGS_AUTOCLEAR};
    int result = -1;
    if (loop >= 0 && image >= 0 && ioctl(loop, LOOP_SET_FD, image) == 0 &&
        ioctl(loop, LOOP_SET_STATUS64, &info) == 0 &&
        mount(node, "/data", "ext4", MS_NOSUID | MS_NODEV, NULL) == 0) result = 0;
    if (result && loop >= 0) ioctl(loop, LOOP_CLR_FD, 0);
    if (image >= 0) close(image);
    if (loop >= 0) close(loop);
    return result;
}

int main(void)
{
    if (getpid() != 1) return 2;
    /* Stock Android GKI need not include devtmpfs. Use first-stage-style
       tmpfs nodes so the kernel probe does not depend on that option. */
    vm_mount("tmpfs", "/dev", "tmpfs");
    static const struct { const char *name; unsigned int major, minor; } initial_nodes[] = {
        {"console", 5, 1}, {"null", 1, 3}, {"zero", 1, 5},
        {"random", 1, 8}, {"urandom", 1, 9}, {"kmsg", 1, 11}
    };
    for (size_t i = 0; i < sizeof(initial_nodes) / sizeof(initial_nodes[0]); i++) {
        char path[128];
        snprintf(path, sizeof(path), "/dev/%s", initial_nodes[i].name);
        if (mknod(path, S_IFCHR | 0600, makedev(initial_nodes[i].major, initial_nodes[i].minor))) return 5;
    }
    int console = open("/dev/console", O_RDWR);
    if (console >= 0) {
        dup2(console, 0); dup2(console, 1); dup2(console, 2);
        if (console > 2) close(console);
    }
    setvbuf(stdout, NULL, _IONBF, 0);
    vm_mount("proc", "/proc", "proc");
    vm_mount("sysfs", "/sys", "sysfs");
    int rate = open("/proc/sys/kernel/printk_ratelimit", O_WRONLY | O_CLOEXEC);
    if (rate >= 0) { (void)write(rate, "0", 1); close(rate); }
    struct utsname version;
    if (uname(&version)) return 3;
    printf("VM native ARM64 kernel: %s %s\n", version.release, version.machine);
    klogfd = open("/dev/kmsg", O_WRONLY | O_CLOEXEC);
    test_kernel();
    printf("VM KERNEL CHECK %s failures=%d\n", failures ? "FAIL" : "PASS", failures);
    char profile[64] = {0};
    if (!failures && !read_text("/vm/profile", profile, sizeof(profile)) && (!strcmp(profile, "core") || !strcmp(profile, "framework"))) {
        int gate = open("/sys/module/access_tokenid/parameters/compat", O_WRONLY | O_CLOEXEC);
        if (gate < 0 || write(gate, "1", 1) != 1) return 4;
        close(gate);
        vm_mount("selinuxfs", "/sys/fs/selinux", "selinuxfs");
        if (vm_data_mount()) { perror("VM RAM-backed ext4"); reboot(RB_POWER_OFF); return 6; }
        vm_mount("tmpfs", "/mnt", "tmpfs");
        vm_mount("tmpfs", "/storage", "tmpfs");
        if (vm_private_devices()) {
            perror("VM private devices");
            reboot(RB_POWER_OFF);
            for (;;) sleep(1);
        }
        if (prepare_ipc()) {
            perror("VM private Binder setup");
            reboot(RB_POWER_OFF);
            for (;;) sleep(1);
        }
        int marker = open("/dev/hmos-init-stage2", O_CREAT | O_WRONLY | O_CLOEXEC, 0600);
        if (marker >= 0) close(marker);
        if (vm_restore_labels()) {
            reboot(RB_POWER_OFF);
            for (;;) sleep(1);
        }
        printf("VM exec original HarmonyOS init with donor service identities\n");
        vm_capture();
        /* Native init creates its parameter-server socket while still in the
           initial kernel domain. The policy grants clients connectto kernel,
           then init's policy adapter transitions PID 1 to init. Preserve that
           ordering rather than grant clients a different socket permission. */
        int attr = open("/proc/self/attr/current", O_WRONLY | O_CLOEXEC);
        const char initial[] = "u:r:kernel:s0";
        if (attr < 0 || write(attr, initial, sizeof(initial) - 1) != sizeof(initial) - 1) {
            perror("VM initial init domain");
            reboot(RB_POWER_OFF);
            for (;;) sleep(1);
        }
        close(attr);
        clearenv();
        setenv("PATH", "/system/bin:/vendor/bin", 1);
        char *const args[] = {"/system/bin/init", "--second-stage", "0", NULL};
        execv(args[0], args);
        perror("VM donor init exec");
    }
    sync();
    reboot(RB_POWER_OFF);
    for (;;) sleep(1);
}
