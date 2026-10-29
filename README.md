# hmos2dodge

Experimental HarmonyOS NEXT 5 port work for the OnePlus 13, derived from
[hmos2sweet](https://github.com/tsryzenstech/hmos2sweet). The goal is the full
Huawei interface, including SceneBoard and apps, with DSU as the primary
experimental boot route.

**This is not a finished ROM or a verified HarmonyOS boot on OP13.**

Current results:

- A Linux 6.6 kernel with gated HarmonyOS token/Binder extensions built
  successfully; the project owner reports that it boots Android on OP13.
- Original HarmonyOS init and logging have been exercised in an isolated
  ARM64 userspace lab. This does not emulate DSU or OP13 hardware.
- Adapted OHOS display HALs build and pass loader, virtual-call, DRM-selection
  and real-mode regression checks in the lab. Native graphics remain untested.
- OP13 window geometry and discrete refresh policy overlays are generated
  from the owner's hardware capture without modifying the donor images.
- A RAM-only DSU startup image can be built. Its core profile starts hilogd
  and samgr, does not start SceneBoard, and is not a full ROM.

The full framework, SELinux integration, isolated persistent storage, driver
startup and native DSU handoff remain under development. Samgr readiness has
not been established. The existing development AVB metadata predates the
captured host's security patch and Android version; device acceptance is
unresolved.

## Source layout

- [Project guide](port/README.md): scripts, prerequisites, outputs and results.
- [Boot and ARB notes](port/docs/BOOT-AND-ARB.md).
- [Hardware observations](port/docs/OP13-HARDWARE.md).
- [Porter review](port/docs/PORTER-AUDIT.md): upstream coverage and adaptations.
- `port/kernel/`: Linux 6.6 patch, preserving the upstream GPL notices.
- `port/display/`: adapted display sources and regression tests.
- `port/src/`: experimental DSU PID-1 bootstrap sources.
- `port/scripts/`: build, inspection and offline verification helpers.

These scripts currently expect the original development workspace layout,
including user-supplied images, a matching kernel checkout, and local build
tools. A clean checkout alone is not a complete build environment. The
reconstruction steps are being documented; this is not a one-command porter.

No ROM images, firmware blobs, device captures, private signing keys, kernel
binaries or build outputs are published here. Obtain inputs independently.
Published source hashes and reduced audit reports document the development
inputs and checks.

## Device constraints

OP13 anti-rollback state and OEM enforcement are not established by an
Android boot test, unlocked bootloader, or temporary-boot support. Development
AVB signatures are not OEM signatures. Removing a stale footer from a generated
image does not disable ARB.

Keep bootloader, firmware and vbmeta outside this port's write path. The
experimental HarmonyOS startup keeps writable state in RAM and excludes
physical Android userdata, metadata, persist and misc. Do not run the
upstream Redmi clean-install scripts on OP13. No flashing commands are provided
as an installation procedure for this unfinished port.

No root manager or SUSFS is integrated. LTO is disabled for subsequent kernel
builds; the Android-tested baseline was built earlier with ThinLTO.

## Attribution and licenses

See [NOTICE.md](NOTICE.md). The repository's original tooling uses Apache-2.0
unless a file states otherwise; existing MIT, Apache and GPL notices remain in
effect. The kernel patches are GPL-2.0. No Huawei or OnePlus proprietary image
or library is licensed or distributed by this repository.

