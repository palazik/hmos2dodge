# Boot paths and anti-rollback

The user's OP13 has ARB. The project does not know its stored rollback state
or the exact OEM enforcement policy. Do not infer compatibility from kernel
version numbers, an unlocked bootloader, or temporary-boot support.

`audit_avb.py` checks the actual source and generated images without changing
them. The COS17 source boot image is unchanged and matches its recorded hash.
Its embedded vbmeta header reports rollback index 0 at location 0. That is an
image field, **not a reading of the phone's stored counters or firmware ARB**.

The generated kernel candidate has no AVB footer. The old footer authenticated
the old kernel, so the packer removed that stale footer from the generated
file. It did not remove or modify anything on the phone, change the original
COS17 image, flash vbmeta, or disable ARB. The candidate is unsigned; its lack
of a footer is not evidence that the phone accepts it or that it is ARB-safe.
The earlier temporary-boot command was not an ARB compatibility assessment.
The user subsequently reported that the candidate boots Android and works.
This is device evidence for that kernel boot, not a blanket ARB guarantee.

The kernel used by DSU also needs to be accounted for. `fastboot boot` loads
from RAM; it does not install the image for subsequent boots. An ordinary
DSU reboot therefore cannot be assumed to retain the tested custom kernel.
A temporary boot of the custom kernel while DSU is armed is a route to
investigate without flashing, but that exact sequence has not been validated
on this OP13. The bootstrap stops if its required kernel interfaces are absent.
No persistent kernel installation has been performed by this project.

Three separate mechanisms matter here:

| Mechanism | What is known here |
| --- | --- |
| AVB signature/hash verification | Source boot has OEM metadata; generated kernel candidate is unsigned; DSU experiments use a local development key |
| Device rollback protection | Device-stored values and OEM firmware enforcement remain unknown; no firmware or bootloader images are installed by this project |
| DSU compatibility checks | DSU uses image metadata, signing/trust and security patch comparisons; a locally verified development signature does not establish device acceptance |

The DSU development wrapper uses a `2026-07-01` compatibility property from
the supplied extracted Android files. This is not a claim that HarmonyOS has
received Android security fixes or that the installed device patch level
matches it. A DSU rejection must be investigated rather than treating a
metadata edit as proof of ARB compatibility.

DSU remains the primary port route. AOSP first-stage init maps DSU images and
executes `/system/bin/init selinux_setup` from the selected root. This offers
a handoff point for a custom bootstrap. The current bootstrap mounts the six
donor filesystems read-only and enters HarmonyOS init with a curated config.
Whether the entire OS, HDI services and SceneBoard run through this path on
the OP13 is still unproven. UEFI remains a fallback; it has not been developed
or tested in this phase.

No bootloader, firmware, vbmeta, physical userdata, persist, or misc partition
has been flashed or formatted by this project.

Primary references:

- [AOSP AVB and rollback protection](https://android.googlesource.com/platform/external/avb/+/refs/heads/main/README.md).
- [AOSP verified boot flow](https://source.android.com/docs/security/features/verifiedboot/boot-flow).
- [AOSP DSU documentation](https://source.android.com/docs/core/ota/dynamic-system-updates).
- [AOSP first-stage init](https://android.googlesource.com/platform/system/core/+/refs/heads/main/init/first_stage_init.cpp).
