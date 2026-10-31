# Review of the OP13 changes

Reviewed the 14 OP13 commits from `3b96ed7` through `e155a95`, including
their build/startup paths. The six upstream commits remain intact.

## Problems requiring correction

1. **The original porter is still Redmi-specific.** `hmos2sweet.py`,
   `lib/builder.py` and `lib/flashgen.py` have no OP13 changes. The added
   scripts do not amount to a complete adaptation of its build pipeline.
   Its Redmi flash/wipe path is unsuitable for the requested DSU port.
2. **The native image is a diagnostic profile.** `fcd69df` connects only
   eight services, provides a 128 MiB RAM data filesystem and reboots after
   approximately two minutes. `build_stage2.sh` also defaults to minimal.
   This cannot satisfy a normal persistent launcher port.
3. **Graphics staging is disconnected from the image.** `6a9618b` prepares
   render/input/composer/allocator configuration and an HDF override, but
   `build_stage2.sh` does not consume the graphics component and the C entry
   rejects its profile. `03d8b12` stages modules without loading them.
   Adding service names and verifying CRCs does not enable graphics.
4. **The stock vendor change is partial.** `e155a95` mounts stock vendor/odm,
   but overlays all vendor bin/lib64 and masks vendor/etc. This supplies a
   native OHOS runtime and stock firmware, not an Android-to-OHOS HAL bridge
   or a complete OP13 hardware configuration. The directory-mount test
   establishes filesystem layout only.
5. **Service registration is not launcher startup.** Account manager and BMS
   publish in the guest, but the logs show no foreground user and repeated
   user-ID lookup failures. SceneBoard package inspection and an EGL softpipe
   test do not establish installation, native-window interoperability or launch.

The original large commit added 36,455 lines. A single generated module audit
accounted for 12,231; other generated inventories account for thousands more.
These are not equivalent to implementation progress. Future commits should
contain a focused functional change with concise, relevant validation.

## Disposition by commit

| Commit | Assessment |
| --- | --- |
| 3b96ed7 | Keep useful kernel/display adaptations; porter/build integration incomplete. |
| 4feed75 | Keep scoped DRM map permission; runtime compilation is not a strict policy pass. |
| 9f657d7 | Keep mount-order fix and donor identities; service graph incomplete. |
| 0e7b5d3 | Keep Kirin-device removal; it does not implement complete HDF startup. |
| 540bf83 | Guest regression evidence only; not DSU boot evidence. |
| c99a15d | Keep no-LTO preference and stock controller ABI correction. |
| 258959d | Guest appspawn/account result only; no active-user or launcher proof. |
| 1e7a8f5 | Useful Foundation/HUKS checks; installation/session still incomplete. |
| 22dbf4f | Keep rejection of incompatible older module providers. |
| 64bce14 | Keep general extraction tools outside published port code. |
| fcd69df | Replace phone RAM-data and timed-reboot behavior. |
| 03d8b12 | Keep audited module payload; add actual startup integration. |
| 6a9618b | Keep stock firmware and real shader test; connect graphics to normal startup. |
| e155a95 | Keep stock source selection; complete runtime/hardware integration. |

## First correction

The framework startup now requires the exact `userdata_gsi` mapper, rechecks
its sysfs identity and block-device numbers, and mounts it as persistent ext4
data. It never formats a device or falls back to physical Android userdata.
The builder no longer generates its old RAM seed and defaults to framework.
Ending log capture no longer reboots the framework. Legacy lab profiles keep
their separate diagnostic behavior.

Host and ARM64 compilation/selftests pass. Namespace tests retain the stock
firmware/ODM read-only checks and reject physical-userdata aliases and missing
DSU identities before mounting. Actual persistent DSU mounting and survival
across reboots require device verification. Graphics, account activation and
SceneBoard are still incomplete; no replacement full image was packed.
