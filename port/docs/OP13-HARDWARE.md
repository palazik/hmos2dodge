# OP13 hardware capture, 2026-10-29

Source: `20261029-163450.zip`, extracted under
`work/device-hardware/20261029-163450/`. Archive hash and selected observations
are in `op13-hardware-capture.json`; per-module hashes and comparisons are in
`op13-module-audit.json`. The archive and original kernel/images are preserved.

The capture identifies CPH2649, SM8750, COS build
`CPH2649_17.0.0.102(EX01)`, and security patch `2026-10-05`.
The reported verified-boot property is `green`; this alone does not establish
the current bootloader lock state or any stored rollback counter.

## Display changes supported by the capture

The internal connector is `card0-DSI-1`, connected. Sysfs exposes
1440×3168 command modes at 60, 90 and 120 Hz (120 appears twice).
Android additionally advertises 1080×2376 modes and reports that resolution
at 90 Hz during capture. These Android mode IDs are not DRM mode IDs.
The backlight is `panel0-backlight`, maximum 4094.

Both primary `card0` and `renderD128` exist, as does `/dev/kgsl-3d0`.
DMA heaps include `system`, `qcom,system` and `qcom,display`; `/dev/ion`
is absent. Dumb-buffer capability, atomic KMS and native OHOS rendering were
not measured by this capture.

The staged composer now enumerates real connector modes, validates mode IDs,
allows nonzero CRTC mode IDs, and derives software fallback vsync timing from
the selected refresh rate. The Redmi-specific virtual mode 1 and half-rate
hardware-vblank filter are removed. The existing backlight discovery already
includes the captured path and reads its maximum dynamically.

## Module audit and remaining inputs

There are 464 distinct `.ko` files; the two pulled vendor paths contain
identical module bytes. Across them, 24,564 imported CRC records match entries
in the Android-tested kernel's saved symbol table, with no mismatches among
comparable entries. For `msm_drm`, 674 imports match and 140 are absent from
that table; for `msm_kgsl`, 459 match and 66 are absent. Absent entries require
other module providers and are not counted as matching.

The captured graphics modules have vermagic
`6.6.118-android15-8-o-4k SMP preempt mod_unload modversions aarch64`.
The local Linux 6.6 loader ignores the release portion of vermagic when CRCs
are present (`kernel/module/version.c: same_magic`), but still checks the
remaining flags and symbol CRCs. This audit does not certify complete ABI,
signatures, loadability or actual device behavior.

The offline dependency traversal for display and GPU finds 35 uncaptured
providers, including clocks, SCM, pinctrl, DMA heaps and vendor boot modules.
They may already load during Android first-stage startup; that is not yet
established for the DSU handoff. The dependency order in the JSON is incomplete
and must not be executed as a load script. No modules have been loaded or
added to the experimental startup by this audit.

Only firmware filenames were captured, including `gen80000_*` GPU files.
Do not substitute the Redmi firmware or treat the filename list as firmware
contents. The collector now also attempts read-only pulls of
`/system_dlkm/lib/modules` and `/lib/modules`, and records `uname -a` for a
future capture; access failures remain nonfatal and root is not required.

## DSU status

The captured Android system is not running DSU. Its October security patch is
newer than the July date in the existing experiment's development AVB metadata.
Acceptance of that metadata must be investigated before a native DSU test.
No dates or rollback indices were changed to conceal the discrepancy.
Neither these properties nor the module audit establish ARB compatibility.

Reproduce the module audit without a device:

```sh
python3 port/scripts/audit_op13_modules.py \
  --capture work/device-hardware/20261029-163450 \
  --output port/docs/op13-module-audit.json
```
