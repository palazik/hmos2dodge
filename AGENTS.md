# OP13 HarmonyOS port constraints

- The OnePlus 13 has anti-rollback (ARB). Treat its device-specific behavior
  and stored rollback state as unknown until actual device evidence exists.
- Work offline while the user has no device available. Do not run device
  flashing, erasing, partition creation, bootloader locking/unlocking, slot
  switching, or rollback-index-changing operations.
- Preserve original donor and stock images. COS17 boot template preference:
  `/home/palaziks/cos17/boot.img`.
- Removing an AVB footer from a generated image does not disable ARB. Neither
  an unlocked bootloader nor `fastboot boot` establishes ARB compatibility.
  Do not describe test candidates as ARB-safe without device-specific proof.
- Keep bootloader/firmware/vbmeta partitions outside the port's write path.
  Distinguish offline development signatures from OEM signatures and trust.
- Keep HarmonyOS writable storage isolated from physical Android userdata,
  metadata, persist, misc and firmware partitions in experimental startup.
- LTO was disabled at the user's request for subsequent kernel builds.
- The user cancelled ReSukiSU/SUSFS integration and resumed porting. Do not
  add root or SUSFS. Preserve the HarmonyOS changes and the Android-tested
  copies in `out/baseline-android/`.
- Report actual build/emulation results separately from untested OP13 boot,
  DSU, SceneBoard and hardware functionality.
- Use this project's supplied ROM inputs, OP13 capture and new vendor_boot.img.
  Do not substitute images from other porting projects.
- The user allows extraction of OP13 stock vendor/odm and needed ancillary
  images from /home/palaziks/claudefix/stock/payload.bin. They still exclude
  boot, vendor_boot, system, product, system_ext and every my_* partition.
  Preserve the supplied choices for those excluded inputs.
- Keep generic ROM extraction and one-off inspection utilities in ignored
  work/tools. Published code should implement, build or validate the HMOS5 port.
- Do not retain redundant full-ROM containers, temporary backups or stale VM
  archives. Keep the original ROM inputs and tested Android baseline, and
  build a full image only when actually needed. Remove staging image hardlinks
  after packing rather than leaving duplicate-looking trees behind.
