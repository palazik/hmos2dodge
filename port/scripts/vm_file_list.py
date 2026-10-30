#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""List a core guest payload and its ELF dependencies for cpio, NUL separated."""
import argparse
import json
from pathlib import Path
import re
import struct
import sys
from prepare_framework import ROOT


def needed(path):
    data = path.read_bytes()
    if data[:6] != b'\x7fELF\x02\x01':
        return []
    offset = struct.unpack_from('<Q', data, 40)[0]
    size, count = struct.unpack_from('<HH', data, 58)
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, offset + i * size) for i in range(count)]
    result = []
    for section in sections:
        if section[1] != 6:
            continue
        strings = sections[section[6]]
        table = data[strings[4]:strings[4] + strings[5]]
        for pos in range(section[4], section[4] + section[5], section[9]):
            tag, value = struct.unpack_from('<qQ', data, pos)
            if tag == 1:
                result.append(table[value:table.index(b'\0', value)].decode())
    return result


def select(stage):
    selected = {Path('.')}
    source = stage / 'system'
    namespace = (source / 'etc/ld-musl-namespace-aarch64.ini').read_text()
    # This core lab contains system executables using the system namespace.
    paths = re.findall(r'^\s*namespace.default.lib.paths\s*=\s*(.+)$', namespace, re.M)
    directories = [stage / name.lstrip('/') for name in paths[-1].split(':') if name.startswith('/system/')]
    directories += [source / 'lib64/ndk']

    def find_library(name):
        for directory in directories:
            path = directory / name
            if path.exists():
                return path
        raise ValueError('Core ELF dependency not found in system namespace: ' + name)

    queue = [source / 'bin' / name for name in
             ('init', 'samgr', 'hilogd', 'hilog', 'param', 'sa_main', 'restorecon', 'setfilecon', 'sa-query')]
    queue += [source / 'lib64/init/libselinuxadp.z.so',
              source / 'lib/ld-musl-aarch64.so.1',
              find_library('libparaperm_checker.z.so'),
              find_library('libfwmark_client.z.so'),
              find_library('libaccesstoken_manager_service.z.so'),
              find_library('libaccesstoken_config_policy.z.so'),
              find_library('libtokensync_sdk.z.so')]
    config = json.loads((source / 'etc/init.cfg').read_text())
    for service in config['services']:
        binary, *arguments = service['path']
        queue.append(stage / binary.lstrip('/'))
        for argument in arguments:
            if argument.startswith('/system/profile/') and argument.endswith('.json'):
                sa_profile = json.loads((stage / argument.lstrip('/')).read_text())
                queue += [find_library(sa['libpath']) for sa in sa_profile['systemability']]
    if any(service['name'] == 'appspawn' for service in config['services']):
        # Appspawn registers its own plugin tree through dlopen.
        queue += [source / 'bin/processdump']
        queue += list((source / 'lib64/appspawn').rglob('*.so'))
        queue += list((source / 'lib64/seccomp').rglob('*.so'))
        # Ark's generated code is opened as data, not an ELF DT_NEEDED entry.
        # Missing stub.an leaves interpreter entry slots empty during preload.
        queue += list((source / 'lib64/module/arkcompiler').iterdir())
        queue += [find_library(name) for name in
                  ('libace_compatible.z.so', 'libimageformatagent.z.so', 'libactivation_lock_sdk.z.so')]
    while queue:
        path = queue.pop()
        relative = path.relative_to(stage)
        if relative in selected:
            continue
        selected.add(relative)
        if path.is_symlink():
            target = Path(path.readlink())
            resolved = stage / str(target).lstrip('/') if target.is_absolute() else path.parent / target
            # Normalize without following absolute guest symlinks on the host.
            import os
            resolved = Path(os.path.normpath(resolved))
            resolved.relative_to(stage)
            queue.append(resolved)
        else:
            queue += [find_library(name) for name in needed(path)]
    for path in stage.rglob('*'):
        relative = path.relative_to(stage)
        if relative.parts[:2] in (('system', 'lib64'), ('system', 'lib'), ('system', 'bin')):
            continue
        selected.add(relative)
    for path in list(selected):
        selected.update(path.parents)
    return sorted(selected, key=str)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('core', 'framework'), default='core')
    args = parser.parse_args()
    stage = ROOT / ('work/system-vm/runtime-root-' + args.profile)
    files = select(stage)
    sys.stderr.write(f'Core VM payload: {len(files)} entries\n')
    for path in files:
        sys.stdout.buffer.write(str(path).encode() + b'\0')
