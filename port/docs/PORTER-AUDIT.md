# hmos2sweet review and OP13 applicability

Reference commit: `1be080c325fee50622d4fdbd996e1dc96717feba`.
All 436 selected text source/build/config files were retrieved and checked
against their Git blob hashes. `porter-source-coverage.json` records the
coverage. Compiled payloads are not thereby audited, and this is not a claim
that every source path has been exhaustively reviewed or tested.

The reviewed architecture, CLI, builder, patch loader, boot packer, flash
generator, preinit, kernel adaptations, display code and patch manifests show
that the tool targets native Redmi Note 10 Pro installation. The builder
extracts Huawei OTA images, applies selected vendor replacements and init
fragments/hooks, builds an sm6150 boot image and produces native flash scripts.
It does not implement an OP13 DSU port. The supplied donor is already an
iter43 build of that Redmi port.

## Disposition for OP13

| Upstream component | OP13 treatment |
| --- | --- |
| Native flash generator / lpwrite | Excluded. Deletes/resizes logical partitions, formats userdata/cache, flashes boot/dtbo and can write super from recovery. |
| Preinit / fstab.sweet | Replaced by DSU bootstrap. Original paths refer to physical super, userdata, cache, misc and DSP. |
| Kernel token/Binder patches | Adapted to Linux 6.6 with runtime opt-in and task KABI padding; Android baseline tested by owner. |
| Kernel hmdfs/sharefs emulation | Not directly applied: 4.14 implementation uses removed `set_fs`/`do_mount` interfaces. Isolated storage integration remains work. |
| Kernel fs-verity success stubs | Not adopted as a blanket substitute for code-signing verification. |
| Kernel WLAN/NFC/vibrator/SSR patches | Redmi-specific; not applied wholesale to SM8750. |
| Display composer / allocator | Both adapted and built. DRM discovery and real mode handling tested offline; native KMS untested. |
| Mesa/GLES | Donor runtime identified; presence of GPU identifiers is not a rendering compatibility test. |
| Display geometry / fixed 120 Hz | Replaced by OP13 capture-based geometry and discrete 60/90/120 Hz policies. |
| CPU/GPU performance scripts | Redmi CPU topology/governor paths are not carried into the core bootstrap. |
| Crash/reboot suppression | Current core services have critical restart actions disabled; unrestricted donor reboot jobs are excluded. |
| Userauth/HUKS/PIN replacements | Existing donor replacements are present in read-only inputs; not certified as production credential storage on OP13. |
| Remoteproc/Wi-Fi/Bluetooth/sensors | Require SM8750-specific adaptation; donor starts/mounts are excluded from core startup. |
| Audio/camera/RIL/GNSS/IR/NFC | Redmi hardware assumptions are not reused as OP13 implementations. |
| USB gadget | Redmi controller/serial configuration is not reused as an OP13 configuration. |
| Thermal | Redmi sensor thresholds and Kirin policies require OP13 review before enabling corresponding services. |
| Setup wizard / SceneBoard | No automatic setup-complete values are fabricated. Full framework/app startup remains unfinished. |

## Framework findings

`audit_framework.py` maps donor init services and system-ability profiles
without executing them. The full startup contains physical partition mounts,
fstab handling, restorecon operations, reboot jobs, Redmi coprocessor launchers
and duplicate service overrides. These must be adapted deliberately; copying
all init files is not a full OP13 port.

Foundation's declared external dependency includes SA 3503, hosted by
`accesstoken_service`; another dependency, SA 3299, is hosted in foundation.
Appspawn, access-token policy, accounts, isolated storage, render service and
HDF hosts are needed before full SceneBoard bring-up. The host lab currently
cannot establish native Binder/SELinux readiness; `samgr` exits there.

No upstream native installer has been executed. The local experiment mounts
donor images read-only and uses RAM for HarmonyOS writable state. Full OP13
boot, DSU acceptance, SceneBoard and hardware functionality are still untested.
