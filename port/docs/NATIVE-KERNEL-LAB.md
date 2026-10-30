# Diskless ARM64 kernel lab

This lab defaults to the Android-tested OP13 kernel on QEMU's generic ARM64
`virt` machine. `HMOS_VM_KERNEL` selects another experimental kernel; its
hash is recorded when staging the archive. It exercises real kernel Binder,
access-token ioctls, process IDs,
service credentials and SELinux. It does not emulate DSU, the OP13, Qualcomm
hardware, an Android bootloader, AVB acceptance or ARB state.

The runner supplies no disks, shared directories, network or device
passthrough. Guest writable storage is RAM. `/data` is a generated 128 MiB
ext4 file included in cpio and loop-mounted inside the guest; it has no
persistent host backing. Original images and the
Android-tested kernel copies remain unchanged. A watchdog powers down the
guest after its observation interval. QEMU exiting successfully is not a
service-readiness test.

Use an installed `qemu-system-aarch64` or set `HMOS_QEMU` to one. The local
workspace also has Debian QEMU 7.2.22 extracted under `work/system-vm/tools`,
without installation into the host. A static ARM64 musl toolchain and the
existing extracted donor/runtime and policy tools are required.

```sh
bash port/scripts/build_vm_probe.sh
bash port/scripts/run_vm.sh probe
python3 port/scripts/build_selinux.py --mode donor-runtime --with-op13 --vm-diagnostics
bash port/scripts/build_vm_runtime.sh
bash port/scripts/run_vm.sh core
```

Logs are local `work/logs/vm-{probe,core}.log`; generated input records are
`out/vm/runtime-inputs-core.json` (also mirrored to `runtime-inputs.json`).
The compact archive explicitly adds dynamic
plugins as well as recursively resolving ELF `DT_NEEDED` dependencies.
It selects hilogd, samgr and accesstoken_service with the donor definitions,
including UID/GID, SELinux context, token permissions and sockets. Donor
critical reboots and unrestricted configuration imports are disabled.
The donor resource limits precede service startup: a missing RLIMIT_NICE
prevents init applying access-token service importance after dropping UID.

The cpio format discards the original EROFS security xattrs. The lab therefore
loads a compiled policy into the guest, restores labels before services,
and lets original init enable enforcing mode. This preparation has a
permissive interval. Original init attempts to load policy again and currently
logs a reload failure; do not report this as an error-free policy-loader test.
No host policy is loaded. Runtime compilation with `-N` follows the upstream
loader's compilation behavior; strict compilation still fails on the donor's
390 existing neverallow locations.

`vm-diagnostics.cil` is a separate observer-only supplement. It lets the
init-domain observer execute the loader, map the donor hilog client, and
connect to the log reader socket and query access-token SA 3503. A dedicated
`vm_data_backing_file` type also permits kernel loop writeback to the RAM
file; generic rootfs writes are not granted. This avoids granting the disabled donor
production debug domain access to the VM console. It is compiled into an
`-op13-vm` output, never the regular `-op13` policy or the raw phone image.
The observed services retain their donor domains; the observer privileges
must not be mistaken for an unchanged whole-policy test.

The lab preserves native init's ordering: parameter sockets are created in
the initial kernel domain before init transitions into its own domain.
Changing this order creates a socket `connectto` denial for native clients.
Basic public character devices need donor modes; root-only random/null nodes
produce misleading service failures.

# BinderFS adaptation

The donor predates BinderFS. The OP13 supplement labels its root and three
Binder nodes using existing donor device types. `check_binderfs_policy.py`
queries the compiled labels in libsepol memory, without loading kernel policy.
The shared startup helper bind-mounts actual BinderFS inodes onto `/dev/binder`,
`/dev/hwbinder` and `/dev/vndbinder`. Symlinks add a separate link permission
which native service policy does not grant. Modes are set to donor 0666 before
policy loading; root-only feature-query success does not test non-root access.

These changes do not establish SceneBoard, framework, display, Android DSU
handoff or native OP13 boot readiness. The raw core image still uses the
separate restricted two-service profile described in FRAMEWORK-BRINGUP.md.

# Storage and registration checks

Plain tmpfs does not supply the donor's expected labeled-data filesystem
behavior or the database stack's persistent xattrs on this kernel. The lab
uses RAM-backed ext4 so errors from missing filesystem semantics can be
distinguished from missing framework/security services. This does not mount
Android userdata, provide persistence, or resolve Huawei storage services.

The small `vm_sa_query.cpp` observer uses the original donor Binder libraries
and pinned OpenHarmony 5.1 samgr headers. It calls `CheckSystemAbility(3503)`.
A non-null response establishes that the observer obtained a registered
remote object; a null response may also indicate an access denial. Neither
result establishes complete access-token functionality. The real
`accesstoken.permission.init` parameter is observed separately; no invented
service-ready parameter is set or treated as evidence.

The original COS17 kernel also boots the minimal `virt` guest. Its probe
cannot open this port's custom access-token compatibility gate. That only
establishes absence of this interface. It does not prove that every HarmonyOS
version or another DSU adaptation requires these kernel patches, and does
not establish anything about the reported private HMOS7 port.

The fresh-data candidate also provisions access_token/lock before the service
starts. RDB lock-file creation otherwise fails because the service domain
can create files there but cannot create the directory itself.

# Recorded core result

The completed run in `native-kernel-result.json` passes the kernel feature and
token checks, observes samgr in its donor domain, sees samgr set its real ready
parameter, and obtains access-token SA 3503 through Binder. Final SELinux
mode is enforcing and the RAM ext4 filesystem has no I/O errors. Fresh-data
directories are provisioned before enforcement and restored to donor labels;
placing their creation only in later init jobs is insufficient because some
parent directory permissions intentionally restrict runtime init.

These are core-startup observations. Original init's policy-reload error and
missing dependent service/configuration errors remain. No SceneBoard launch
or native DSU test is implied.

# Expanded service lab

`bash port/scripts/build_vm_runtime.sh framework` stages an independent
archive with accountmgr, appspawn and faultloggerd in addition to the three
core services. `bash port/scripts/run_vm.sh framework` observes it for
120 guest seconds. Its input record is `out/vm/runtime-inputs-framework.json`.
Both profiles have independent staging directories; a runner lock prevents
two guests from overwriting a log concurrently. `HMOS_VM_TIMEOUT` controls
the host timeout, and `HMOS_VM_INITRD` can select a decompressed cpio in
host RAM to avoid TCG gzip overhead. No guest disk is added.

The expanded observer can query account-manager SA 200 and trace appspawn's
fault registers with ptrace. Those permissions exist only in the separate
VM policy. Appspawn retains its own domain and seccomp filters. Faultloggerd
alone has not produced usable crash reports in this setup; the register
observer is a separate diagnostic path. It does not suppress the original
fatal signal or establish service readiness.

The dependency list must include files opened dynamically: appspawn plugins,
seccomp filters and Ark's `module/arkcompiler/stub.an` and metadata. ELF
`DT_NEEDED` resolution alone misses them. An earlier compact archive omitted
`stub.an`; the runtime logged its absence and appspawn faulted at a null
indirect call in `libark_jsruntime.so` (ELF VA 0x3a6c10). This was a lab
payload omission, not absence from the original donor image.
OpenHarmony's [runtime build configuration](https://github.com/openharmony/arkcompiler_ets_runtime/blob/master/js_runtime_config.gni)
also defines the standard-system `STUB_AN_FILE` path. The donor's own missing
file log and fault registers are the evidence for this particular failure.

The donor's pids cgroup mount cannot succeed with the stock controller set.
Enabling CONFIG_CGROUP_PIDS changed imported module CRCs in an experimental
build, so it is excluded from the phone kernel configuration. See
`kernel-pids-experiment.json`. Do not bypass module CRC checks to work around
this. The remaining appspawn sandbox/cgroup behavior requires adaptation.

The recorded expanded runs (`framework-kernel-result.json` and
`framework-nolto-result.json`) observe account-manager SA 200 and access-token
SA 3503 through Binder, appspawn setting its real startup event, no observed
appspawn SIGSEGV, and final enforcement. The second run also provisions
private `/mnt/sandbox` and `/mnt/startup` directories before label restoration,
eliminating their init mkdir errors. It uses the rebuilt no-LTO kernel, which
has not been tested on Android. These checks establish selected service
initialization, not the ability to launch applications or enforce a complete
application sandbox. Missing pids control, dependent services and device
security components remain unresolved.

The runner checks the selected kernel against its staged input record and
checks that a custom initrd contains the staged archive. It records actual
launch hashes separately. `record_vm_results.py` verifies these records and
the source hashes before writing a result. Rebuild with the same
`HMOS_VM_KERNEL` value passed to the runner when selecting another kernel.

# Foundation lab

The `foundation` build/runner profile adds the original Foundation service
and HUKS service to the expanded guest. The archive includes the two donor
SystemResources packages and the donor's three HUKS HDI libraries. The donor
already contains hmos2sweet's software HUKS CA implementation; this lab does
not provide Huawei TEE behavior or hardware-backed key trust. Its files and
keys live only in the private RAM ext4 filesystem.
It also registers the original `installs` service with its on-demand flag,
credentials, capabilities and permissions retained. BMS requests SA 511
through SAMGR; init supplies the original on-demand launch arguments. The
guest does not run an installer against Android or expose any physical disk.

Foundation's original profile references `libwms.z.so` for SA 4606, but that
library is absent from the checked donor system/vendor/chip_prod/sys_prod
inventories. The archive builder records this specific unresolved entry and
leaves the profile unchanged. Other missing dependencies still fail the
build. Native sa_main logs the failed load and continues; SA 3299 (common
events) and SA 401 (bundle manager) have been obtained through Binder.
This does not demonstrate a working window manager or installed applications.

The guest adds the kernel's ashmem misc device using its sysfs-reported device
number, checks a size ioctl and shared mapping, and applies exact donor
0666 modes with chmod. Relying only on mknod's mode lets the process umask
reduce this to 0644: a root-only smoke test then hides non-root access errors.
No extra service-domain SELinux permission is needed for that DAC fix.

The installed donor library also uses `/data/service/el1/public/bms`, while
its foundation.cfg creates an older database tree. The lab provisions a
private BMS directory and lock subdirectory owned by Foundation before
restoring labels. These experimental directories are recorded separately
from exact donor mkdir commands. No Android data is imported.

For the current candidate:

```sh
python3 port/scripts/build_selinux.py --mode donor-runtime --with-op13 --vm-diagnostics
HMOS_VM_KERNEL="$PWD/out/kernel/Image" bash port/scripts/build_vm_runtime.sh foundation
HMOS_VM_KERNEL="$PWD/out/kernel/Image" bash port/scripts/run_vm.sh foundation
python3 port/scripts/record_vm_results.py --profile foundation
```

`audit_framework_apps.py` separately checks ZIP CRCs and records manifests
and hashes of the original SceneBoard and SystemResources HAP/HSP packages.
To extract its inputs without changing the images:

```sh
mkdir -p work/framework-assets
bin/Linux/x86_64/extract.erofs -i hmos5/system.img -X /system/app/SceneBoard -s -o work/framework-assets
bin/Linux/x86_64/extract.erofs -i hmos5/system.img -X /system/app/SystemResources -s -o work/framework-assets
python3 port/scripts/audit_framework_apps.py
```

The package report is metadata/CRC inspection, not signature-trust
verification, installation or successful SceneBoard execution.

One-time publish log lines may be lost in a busy hilog buffer. The result
recorder tests registration through the native Binder query, and records
publish-log presence separately. A returned object establishes registration;
it does not establish every method of that service works. Database schema
DDL reported by the native BMS/RDB stack is another narrower observation.
The global account/storage startup graph and application installation still
need integration; obtaining the account SA alone does not create or activate
an application user.
