# HDF display configuration candidate

The donor `chip_prod` HDF bytecode configures both
`libdisplay_composer_driver_1.0.z.so` and Huawei's
`libdisplayengine_driver.z.so` inside composer_host. Replacing the composer
VDI alone leaves that additional Kirin display-engine device configured.

`port/scripts/prepare_hdf.py` removes exactly
`root.device_info.display_composer.displayengine_device` and compiles the
result into `out/hdf/op13.hcb`. The compositor and allocator driver entries,
host list, host order and other device definitions remain unchanged.
composer_host and allocator_host retain their positions 7 and 8, matching
the staged donor devhost command arguments. This does not start other hosts.

Before adapting anything, the script decompiles and recompiles the original
HCB and requires **byte-for-byte equality**. It then checks the adapted
binary decompiles to the expected token stream, preserving quoted strings,
and verifies the host list/order. It also checks the input remained unchanged.
Missing, duplicate or malformed target nodes are rejected.

The current result and hashes are in `hdf-display-result.json`. Local donor,
decompiled configurations, compiler and output bytecode stay outside Git.

## Reproduction

The existing extraction tool prefixes output with the image basename:

```sh
./bin/Linux/x86_64/extract.erofs -i hmos5/chip_prod.img \
  -X /etc/hdfconfig/hdf_default.hcb -o work/donor-configs/chip_prod
python3 port/scripts/build_hcgen.py
python3 port/scripts/prepare_hdf.py
python3 port/scripts/test_hdf.py
```

The compiler builder fetches only hc-gen source/build files from pinned
[OpenHarmony drivers_hdf_core](https://github.com/openharmony/drivers_hdf_core/tree/617c08a5b414c27fcc00baf78d9b3af8915e74ba/framework/tools/hc-gen),
verifies Git blob hashes and builds locally. It records source hashes and
local changes in `out/hdf/tool-source.json`. The local fixes escape embedded
quotes in decompiled strings, parse the full uint64 range, and supply a
missing cstdint include for the host compiler. Without the first two fixes,
the donor's embedded JSON strings and negative priority encoded as uint64
fail to recompile. The exact original binary round-trip guards the changes
for this input; it is not a general compiler validation suite.

## Integration status

This HCB is a candidate for the later framework profile. It has **not** been
installed in the raw core image, whose hardware services remain disabled.
All other HDF hosts remain defined in this candidate; enabling an unrestricted
hdf_devmgr would therefore require further adaptation. The tool does not make
that change. Native HDF loading, driver-to-VDI calls, OP13 kernel module loading,
DRM access and actual display output still need integration and verification.
