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
