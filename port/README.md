# HarmonyOS NEXT on OP13: DSU bring-up

This workspace now contains an experimental kernel adaptation and DSU probes.
**It is not yet a working HarmonyOS/SceneBoard port.** No phone partitions have
been flashed or formatted by these scripts.

The intended final result is the full Huawei HarmonyOS interface, including
SceneBoard and apps. The minimal init profile below is an internal startup
test, not a replacement for that interface. DSU is the primary route; UEFI
remains a fallback.

Current additional work:

- [Porter audit](docs/PORTER-AUDIT.md): all 436 selected upstream text files
  match the pinned commit; native Redmi flash/startup assumptions are mapped
  separately from the OP13 work. Full binary/functionality auditing is not claimed.
- `out/ui-config/`: OP13 native density/cutout and discrete 60/90/120 refresh
  overlays. Generated from original Huawei configs, conversion-tested and
  included in the raw core experiment. SceneBoard is not started by that profile.
- [OP13 hardware capture](docs/OP13-HARDWARE.md): 464 vendor modules audited,
  connected DSI panel confirmed, and the Redmi virtual-mode shortcut replaced
  with real mode IDs and refresh timing. Mode regression tests pass under
  ARM64 userspace emulation; actual display and module loading remain untested.
- `out/experiments/stage2/system.img`: separate RAM-only DSU-to-HarmonyOS-init
  experiment. See its adjacent README for restrictions and native test status.
- `work/logs/ohos-init-lab-result.json`: original Huawei init completes all
  three minimal startup jobs as PID 1 under isolated ARM64 userspace emulation.
  This does not emulate DSU or the OP13 hardware. External init modules are
  excluded, including the OHOS SELinux policy-loader module; no apps run.
- `port/display/0001-discover-internal-drm-and-active-mode.patch`: staged
  composer/allocator changes for internal DSI discovery and actual mode sizes.
  Both full HALs now build into `out/display/`. Selection logic passes seven
  host cases; resident loading and typed virtual calls pass in ARM64 userspace
  emulation. Hardware display behavior and native unloading remain unverified.
- `port/docs/BOOT-AND-ARB.md` and `port/docs/avb-arb-audit.json`: distinguish
  image signatures, DSU checks and unknown device rollback state. Removing a
  generated image's stale AVB footer is not ARB disablement or a safety proof.

## Outputs and what they do

| File | Purpose |
| --- | --- |
| `out/kernel/Image` | Linux 6.6.144 plus access-token/Binder extensions; user reports successful Android boot |
| `out/boot/op13-hmos-test.img` | Temporary boot candidate using `/home/palaziks/cos17/boot.img` as template |
| `out/boot/op13-hmos-test.json` | Source/kernel/output hashes and preserved boot components |
| `out/dsu/op13-dsu-probe.img.gz` | Small DSU PID-1/kernel/device probe; does not launch HarmonyOS |
| `out/dsu/op13-hmos-mount-probe.img` | Same probe plus six donor images, mounted read-only then unmounted |
| `out/dsu/payload-verification.json` | Byte-for-byte comparison of embedded images against the original donor |

The first build keeps ThinLTO. After it finishes, `disable_lto.sh` changes the
source defconfig and working config for subsequent builds. `out/kernel/config`
records the configuration actually used for the saved Image;
`out/kernel/next-build.config` records the configuration with LTO disabled.
Future builds use the locally downloaded ccache with a 2 GiB limit.

The user confirmed the generated kernel boots Android and works. Its saved
baseline is `out/baseline-android/`. ReSukiSU/SUSFS integration was cancelled;
neither has been added. The hardware capture script
`port/scripts/collect_op13_hardware.sh` needs USB debugging/ADB, not root.
Unreadable files are logged and skipped.

## Android kernel test first

Boot the packed candidate from your computer:

```sh
fastboot boot out/boot/op13-hmos-test.img
```

This requires the phone's temporary-boot support. The image has not been device
tested. The stale OEM AVB footer is removed because its hash describes the old
kernel; this is an unsigned temporary-boot image for the unlocked bootloader.
Neither this command nor an unlocked bootloader establishes compatibility
with the OP13's ARB implementation. See `port/docs/BOOT-AND-ARB.md`.
The template has kernel 6.6.118, while this kernel source is 6.6.144;
the user's original kernel from this source reportedly boots Android, but the
new additions still need testing against the installed vendor modules.

Confirm Android starts and storage, screen, touch, Wi-Fi and USB work. Collect
the running build/kernel/module information with:

```sh
bash port/scripts/collect_device_info.sh
```

The kernel's compatibility gate defaults to off:
`/sys/module/access_tokenid/parameters/compat`. The DSU probe enables it for its
tests and disables it afterward. Android Binder behavior is retained when off.
Neither binderfs nor SELinux enforcement was disabled in the kernel adaptation.

## DSU handoff test

The probe can also run with the original Android kernel: the compatibility
tests will then report failure, but reaching the probe proves the DSU handoff.
The phone needs a working DSU implementation and acceptance of custom images.
Images contain a signed development AVB footer and the `2026-07-01` security
patch property from the supplied Android files. Local signature verification
does not establish that the phone trusts this key. If the installed patch level
is newer or the installer rejects the key, collect that error before proceeding.

Use your DSU frontend to install the small gzip image, or the AOSP installer:

```sh
adb push out/dsu/op13-dsu-probe.img.gz /sdcard/Download/
adb shell am start-activity \
  -n com.android.dynsystem/com.android.dynsystem.VerificationActivity \
  -a android.os.image.action.START_INSTALL \
  -d file:///storage/emulated/0/Download/op13-dsu-probe.img.gz \
  --el KEY_SYSTEM_SIZE "$(stat -c %s out/dsu/op13-dsu-probe.img)" \
  --el KEY_USERDATA_SIZE 8589934592
```

Choose the one-boot/non-sticky DSU mode. The probe has no UI or adbd and is
expected to leave the screen blank. After reaching its PID 1, it logs evidence
and requests a reboot after 30 seconds. If the handoff never happens, that
timer cannot run. Return to normal Android with the phone's usual reboot path.

The probe only accepts the exact `system_gsi` mapping and only attempts to
mount the exact `userdata_gsi` mapping for a report. It never invokes a
formatter or falls back to the physical `userdata` partition. An unformatted
or encrypted DSU data image can fail to mount; that is recorded, not repaired.

Reports go to `/data/hmos-probe/report.txt` inside DSU data when mountable, and
to kernel/pmsg logs. After returning to Android, use an existing rooted setup
or recovery to read `/sys/fs/pstore` and look for `hmos-dsu:`. For example:

```sh
adb shell su -c 'cat /sys/fs/pstore/pmsg-ramoops-*' > work/dsu-pmsg.txt
```

Pstore capture depends on the phone's configuration. If no report survives,
the next step is a logging/USB transport change, not a claim that the probe ran.

After the small probe works, the larger mount probe can test all donor images
through read-only loop devices. It is about 6.3 GiB and needs additional DSU
space beyond its 8 GiB data allocation. Supply the raw image to a frontend that
accepts it. It still does **not** start donor init or SceneBoard.

## What the source review established

The supplied images are already the Redmi Note 10 Pro `hmos2sweet` iter43 port
of Pura 70 HarmonyOS 5.1, as recorded in `rom_full43/BUILD_INFO.txt`. They are
not unmodified Huawei images. The included boot image is header v2 with sweet
hardware arguments and a Linux 4.14 kernel. Its device trees must not be used
for OP13.

The reference utility extracts Huawei OTA images, substitutes a patched sweet
kernel and preinit, rewrites vendor HALs/configuration, and builds flashable
partitions. Its clean-install scripts wipe/repartition the target. They are
specific to sweet and are not used here.

DSU maps image-backed partitions; Android first-stage init then executes
`/system/bin/init selinux_setup`. A custom static executable there can take
over as PID 1. The probe implements this handoff. An actual HarmonyOS boot
would need to mount its partition layout, supply its musl runtime and startup
configuration, then enter HarmonyOS init. Sharing the `.img` extension alone
does not supply any of those steps.

## Remaining port work

1. Prove the modified kernel still boots Android and the DSU handoff works on
   this phone; obtain the resulting module/display/device logs.
2. Supply the **matching** OP13 vendor/vendor_dlkm/odm firmware and modules.
   `op13_stock` currently contains system/product/OPlus customization trees,
   not those hardware partitions. A separate older vendor_boot was inspected
   for evidence but is not substituted into the preferred COS17 boot image.
3. Replace sweet fstab and startup actions. The current donor directly mounts
   physical `userdata`, `cache`, `dsp`, modem and Bluetooth partitions and
   mounts `persist` writable. Preserve DSU data isolation and remove those
   assumptions before launching its init.
4. Adapt the sweet DRM/KMS buffer/composer and Mesa GPU layer to the OP13
   graphics drivers. The donor uses Adreno 618 firmware/configuration; OP13's
   hardware is different. Its Android bionic HALs cannot simply replace OHOS
   musl HDI libraries.
5. Add the remaining required kernel/filesystem interfaces and integrate
   power, USB, touch and other device services based on actual boot logs.
   The supplied 4.14 filesystem-emulation patches use `set_fs`, which is
   unavailable on 6.6. They were not blindly applied. Fake fs-verity success,
   broad DRM-auth bypasses and sweet Wi-Fi/haptics patches were not added.

The donor Mesa library contains an `FD830` identifier. This supports examining
reuse of the existing Mesa build rather than assuming it only contains Adreno
618 code. It does not prove the KGSL driver, firmware, buffer formats or
graphics services work on OP13. The existing sweet GPU firmware remains
inappropriate for this target until replaced with matching OP13 assets.

SceneBoard is already present in the donor. Copying it again will not resolve
the device-service, graphics or startup differences.

## Rebuilding and validation

```sh
python3 port/scripts/prepare_kernel.py
bash port/scripts/build_kernel.sh
python3 port/scripts/check_task_layout.py
python3 port/scripts/pack_test_boot.py --stock-boot /home/palaziks/cos17/boot.img
bash port/scripts/build_probe.sh --with-donor
python3 port/scripts/verify_payload.py
```

Additional offline experiments:

```sh
bash port/scripts/run_init_lab.sh
bash port/scripts/build_stage2.sh core
python3 port/scripts/verify_payload.py --image out/experiments/stage2/system.img \
  --report out/experiments/stage2/payload-verification.json --check-bootstrap --profile core --check-display
python3 port/scripts/prepare_display.py
bash port/scripts/check_display.sh
python3 port/scripts/audit_avb.py
```

Display compilation and userspace tests:

```sh
python3 port/scripts/fetch_display_headers.py
bash port/scripts/build_display.sh
HMOS_DISPLAY_TEST_PROGRAM="$PWD/out/display/display-abi-test" bash port/scripts/test_display_load.sh
HMOS_DISPLAY_TEST_PROGRAM="$PWD/out/display/display-mode-test" bash port/scripts/test_display_load.sh
HMOS_LAB_PROFILE=logging bash port/scripts/run_init_lab.sh
```

`pack_test_boot.py` refuses to overwrite its output. Use a new `--output` path
for a new candidate. It verifies the replacement kernel and checks hashes of
all unpacked non-kernel components and any genuine appended DTB data. The COS17
template has no genuine appended DTB chain: magiskboot's apparent DTB suffix
starts at the kernel's built-in empty DTB and contains more kernel data. The
packer handles that false split and checks the entire raw kernel field. Its
regression checks cover plain kernels, embedded-empty-DTB false positives and
genuine appended DTBs.

Build logs and untouched source backups are under `work/`. The adapted patch
is `port/kernel/0001-hmos-dsu-token-binder-6.6.patch`. It reuses the reference's
Huawei token driver, preserving its GPL copyright/license text. Two unused
task_struct KABI slots hold the tokens. The layout check compares size and
selected offsets; it is not a full vendor-module ABI certification.

The static probe is checked natively and under AArch64 QEMU. Both images have
locally verified AVB signatures/hashtrees. The small EROFS image passes the
bundled fsck. That old fsck makes an oversized read on the larger payload's
2.9 GiB nested system.img; `verify_payload.py` independently streams and hashes
every embedded donor image to check it against its input without that limit.

Source evidence:

- [hmos2sweet](https://github.com/tsryzenstech/hmos2sweet), pinned tree and
  downloaded-file hashes in `port/docs/reference-version.json` and
  `port/docs/reference-source.sha256`.
- [AOSP DSU documentation](https://source.android.com/docs/core/ota/dynamic-system-updates).
- [AOSP first-stage init](https://android.googlesource.com/platform/system/core/+/refs/heads/main/init/first_stage_init.cpp).
- [AOSP DSU fstab transformation](https://android.googlesource.com/platform/system/core/+/refs/heads/main/fs_mgr/libfstab/fstab.cpp).
- [OpenHarmony init stage selection](https://github.com/openharmony/startup_init/blob/OpenHarmony-5.0.0-Release/services/init/main.c).
