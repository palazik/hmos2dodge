# Diskless ARM64 kernel lab

This lab runs the Android-tested OP13 kernel on QEMU's generic ARM64 `virt`
machine. It exercises real kernel Binder, access-token ioctls, process IDs,
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
`out/vm/runtime-inputs.json`. The compact archive explicitly adds dynamic
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
