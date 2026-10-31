#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage an opt-in native framework bootstrap, without guest observer policy."""
import hashlib
import json
from pathlib import Path
import shutil
from framework_profile import ROOT, build_profile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_fresh(source, target):
    target = Path(target)
    if target.exists() or target.is_symlink():
        target.unlink()
    return shutil.copy2(source, target)


def main():
    output = ROOT / 'out/framework/native'
    system = ROOT / 'work/ohos-runtime/system/system'
    vendor = ROOT / 'work/donor-configs/vendor/etc/selinux'
    config, provision, names, adaptations = build_profile('foundation')
    config['services'] = [s for s in config['services'] if s['name'] != 'faultloggerd']
    omitted = []
    for job in config['jobs']:
        kept = []
        for command in job['cmds']:
            # Fault tracing/log collection are lab-only. Pids is absent from
            # the ABI-compatible kernel; never fabricate its task files.
            if command == 'start faultloggerd' or '/data/log/faultlog' in command or '/dev/pids' in command:
                omitted.append(command)
            else:
                kept.append(command.replace('setparam ohos.boot.hardware op13_vm',
                                            'setparam ohos.boot.hardware op13'))
        job['cmds'] = kept
    provision = [line for line in provision if not line.startswith('/data/log/faultlog')]
    output.mkdir(parents=True, exist_ok=True)
    # These are independent generated copies. Make only staging directories
    # writable before replacing previously copied read-only configuration.
    for path in output.rglob('*'):
        if path.is_dir() and not path.is_symlink():
            path.chmod(path.stat().st_mode | 0o200)
    # Copy, not hardlink: later image staging must never chmod donor inodes.
    def ignore(path, names):
        return [name for name in names if Path(path) == system / 'etc' and
                (name == 'init' or name.startswith('init.'))]
    shutil.copytree(system / 'etc', output / 'etc', dirs_exist_ok=True, ignore=ignore,
                    symlinks=True, copy_function=copy_fresh)
    (output / 'etc/init').mkdir(exist_ok=True)
    (output / 'etc/init.cfg').write_text(json.dumps(config, indent=2) + '\n')
    shutil.copytree(vendor, output / 'vendor_etc/selinux', dirs_exist_ok=True,
                    symlinks=True, copy_function=copy_fresh)
    policy = ROOT / 'out/selinux/donor-runtime-op13/policy.31'
    validation = json.loads((policy.parent / 'validation.json').read_text())
    if validation['vm_diagnostics_only'] or not validation['compile_passed']:
        raise SystemExit('Native bootstrap requires a successfully compiled regular OP13 policy')
    if validation['policy_sha256'] != digest(policy):
        raise SystemExit('Native policy bytes differ from compiler validation record')
    for name, value in validation['input_sha256'].items():
        if digest(ROOT / name) != value:
            raise SystemExit('Native policy inputs changed; rebuild policy: ' + name)
    copy_fresh(policy, output / 'vendor_etc/selinux/prebuild_sepolicy/policy.31')
    copy_fresh(system / 'etc/selinux/system.cil.sha256',
                 output / 'vendor_etc/selinux/prebuild_sepolicy.system.cil.sha256')
    data_contexts = output / 'vendor_etc/selinux/targeted/contexts/file_contexts'
    original_contexts = data_contexts.read_text()
    data_contexts.chmod(data_contexts.stat().st_mode | 0o200)
    data_contexts.write_text(original_contexts + '\n/mnt/hmos-data\\.ext4 u:object_r:hmos_ram_data_file:s0\n')
    plugins = output / 'init_modules'
    plugins.mkdir(exist_ok=True)
    copy_fresh(system / 'lib64/init/libselinuxadp.z.so', plugins / 'libselinuxadp.z.so')
    for name in ('autorun', 'reboot'):
        (plugins / name).mkdir(exist_ok=True)
    (output / 'data-directories').write_text('\n'.join(provision) + '\n')
    (output / 'profile').write_text('framework\n')
    contexts = ['/.* u:object_r:rootfs:s0',
                '/system/bin/init u:object_r:init_exec:s0',
                '/hmos/bootstrap/etc(/.*)? u:object_r:system_etc_file:s0',
                '/hmos/bootstrap/vendor_etc(/.*)? u:object_r:vendor_etc_file:s0',
                '/hmos/bootstrap/init_modules(/.*)? u:object_r:system_lib_file:s0',
                '/hmos/overrides/vendor/lib64/.* u:object_r:vendor_lib_file:s0',
                '/hmos/overrides/sys_prod/.* u:object_r:sys_prod_file:s0']
    for original in (system / 'etc/selinux/targeted/contexts/file_contexts',
                     vendor / 'targeted/contexts/file_contexts'):
        for line in original.read_text().splitlines():
            for source, target in (('/system/etc', '/hmos/bootstrap/etc'),
                                   ('/vendor/etc', '/hmos/bootstrap/vendor_etc')):
                if line.startswith(source):
                    contexts.append(target + line[len(source):])
    (output / 'file-contexts').write_text('\n'.join(dict.fromkeys(contexts)) + '\n')
    report = {
        'scope': 'Native framework bootstrap component; raw stage2 integration pending',
        'services': sorted(s['name'] for s in config['services']),
        'donor_credentials_and_permissions_retained': True,
        'observer_policy_included': False, 'policy_sha256': digest(policy),
        'config_sha256': digest(output / 'etc/init.cfg'),
        'directory_manifest_sha256': digest(output / 'data-directories'),
        'adapted_data_directories': adaptations, 'omitted_lab_or_unsupported_commands': omitted,
        'external_init_modules': ['libselinuxadp.z.so'],
        'physical_userdata_mounted': False, 'native_phone_tested': False,
        'sceneboard_started': False,
    }
    (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(output)


if __name__ == '__main__':
    main()
