# Offline framework integration

`python3 port/scripts/prepare_framework.py` stages a candidate in
`out/framework/framework.cfg`. It selects canonical system service definitions
explicitly, plus composer/allocator definitions from chip_prod. It does not
merge the Redmi vendor override with those definitions or infer directory
load order. Original inputs are unchanged; their hashes and every edited
service field are recorded in `out/framework/adaptation.json`.

The ten selected services are hilogd, samgr, accesstoken_service, accountmgr,
appspawn, foundation, render_service, multimodalinput, composer_host and
allocator_host. Donor uid/gid, capabilities, SELinux domains, permission/token
declarations, executable arguments and socket ownership are retained. Tests
also resolve service and socket owners against the donor account databases.

The candidate disables automatic service startup, critical reboot behavior,
donor cgroup writes and restart cascades. Its data job creates 46 private-data
directories with donor modes/owners and ordered parent prerequisites for a
fresh RAM filesystem. A second explicit job invokes the builtin token-table
loader after data setup; neither job is triggered automatically. It imports
no other configuration. Discarded donor
commands remain visible in the adaptation report, including Mali device
permissions, cgroup mounts and restart operations.
Discarding a required operation does not implement its replacement.

`python3 port/scripts/test_framework.py` verifies retained identities,
directory ordering, exact service selection and absence of automatic startup.
It does not start these services or prove framework readiness.

## Integration still required

This is a configuration component, **not a full framework boot profile**. The
current raw core image still starts only hilogd and samgr. The candidate is
not copied into it. In particular:

- The core image masks init plugins and has not loaded HarmonyOS SELinux
  policy. Native service transitions and the token initialization job must be wired
  before testing this configuration with its preserved security identities.
- The core's curated system/etc lacks broader framework configuration.
  Vendor HDF configuration also needs selective staging instead of exposing
  the entire donor hardware startup graph.
- Appspawn requires private writable sandbox mountpoints and adapted cgroups.
- Account/application storage needs an isolated implementation; the physical
  Android userdata and metadata partitions remain outside the startup path.
- Composer/allocator definitions alone do not load OP13 kernel modules or
  adapt HDF device configuration. Missing early module providers remain an
  unresolved hardware prerequisite.
- Service dependency readiness and actual SceneBoard application launch have
  not been established. No readiness parameter is fabricated by this tool.

These are integration tasks, with native behavior requiring later phone
verification. A successful candidate-generation test is not SceneBoard boot.

## Token initialization source check

The donor init binary contains the `load_access_token_id` command and native
token JSON paths. OpenHarmony 5.1 registers this command directly in
[init_cmds.c](https://github.com/openharmony/startup_init/blob/OpenHarmony-5.1.0-Release/services/init/standard/init_cmds.c).
It is not an external init plugin. Its
[service implementation](https://github.com/openharmony/startup_init/blob/OpenHarmony-5.1.0-Release/services/init/standard/init_service.c)
builds native tokens from service capabilities, permissions and ACLs, and sets
the child's token with `SetSelfTokenID`. This supports retaining those donor
fields instead of rewriting services as root. The proprietary binary's exact
implementation and native token-table behavior still require verification.

## Raw-image configuration visibility fix

The previous wrapper bound individual display XML overrides before masking
`/sys_prod/etc`, hiding them again. Startup now masks donor configuration
first and binds the curated OP13 etc tree read-only afterwards. This tree
contains the two generated display XML files and no donor init configs.

`bash port/scripts/test_stage2_mounts.sh` compiles the actual wrapper helpers
into a test and runs them in a disposable chroot and private user/mount/network
namespaces. It checks both override inodes are visible, writes fail with
EROFS, and a donor init file remains hidden. This is a local Linux mount test,
not device emulation or a native DSU test.

Raw-image builds now generate `out/experiments/stage2/build-manifest.json`
with image, wrapper, config and override hashes. Local AVB verification uses
the development key; it establishes neither OEM trust nor ARB compatibility.
