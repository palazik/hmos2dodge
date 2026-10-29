# OP13 SELinux integration work

The source in `op13-drm.cil` is a supplemental policy fragment, separate from
the original generated donor CIL. It adds only
`composer_host -> dev_dri_file:chr_file map`.

`HdiDrmComposition` maps dumb buffers through its DRM fd for blank-frame and
diagnostic shadow-buffer paths. Offline libsepol decisions on the donor policy
allow that domain to open/read/write/ioctl DRM devices but deny mapping them.
The allocator's exported dma-buf mappings are a different path; this fragment
does not add blanket access for allocator, renderer, applications or other
device types. Driver-specific extended ioctl access is not evaluated here.

## Offline checks

`build_selinux.py` reads the original system/vendor CIL and compatibility map,
builds policy version 31, and records input/output hashes. It does not load a
policy into either the host or a device. It rejects inputs changed while the
compiler is running. The extracted files are expected under the existing
development workspace, as described in the project guide.

The helper defaults to the strict mode, with neverallow checks enabled.
**The original, unchanged donor fails strict validation.** OpenHarmony 5.1's
runtime loader invokes secilc with `-N`; the helper's explicitly selected
`donor-runtime` mode matches that behavior. A successful build in this mode
is not a strict policy pass and does not certify kernel enforcement or boot.

Example commands, with a local secilc/libsepol installation or the isolated
tools in `work/policy-tools`:

```sh
python3 port/scripts/build_selinux.py --mode strict
python3 port/scripts/build_selinux.py --mode strict --with-op13
python3 port/scripts/build_selinux.py --mode donor-runtime
python3 port/scripts/build_selinux.py --mode donor-runtime --with-op13
python3 port/scripts/check_selinux_access.py
python3 port/scripts/check_selinux_access.py \
  --policy out/selinux/donor-runtime-op13/policy.31 \
  --output out/selinux/op13-access-decisions.json
python3 port/scripts/test_selinux_access.py
```

The two strict commands return nonzero for the known donor failures. The
regression compares their neverallow failure locations, explicitly retaining
the failed status, and checks that only the intended queried permission
changes. It is a selected access regression, not an exhaustive policy audit.
`samgr` can set `bootevent_param` in the binary policy; its host-lab failure
also reports unavailable peer security contexts, so a blanket permission
bypass would not establish native correctness.

Current policy candidates are under `out/selinux/`, excluded from Git. They
are not installed into the raw core image or loaded by its bootstrap. Native
policy loading, transitions, OP13 node labels, KGSL ioctl access, dma-buf
labels and framework service readiness still need integration and testing.
Neither Android SELinux enforcement nor the Android-tested kernel is changed.

Runtime compiler reference:
[OpenHarmony 5.1 load_policy.cpp](https://github.com/openharmony/security_selinux_adapter/blob/OpenHarmony-5.1.0-Release/framework/policycoreutils/src/load_policy.cpp).

The isolated host tools used for the recorded run were Debian secilc and
libsepol 3.8.1-1, extracted into the workspace without system installation.
No tools, donor CIL files or compiled policies are distributed in Git.
