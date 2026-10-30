#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage explicit framework services and RAM-data directories; do not start them."""
import copy
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    'hilogd': 'system/etc/init/hilogd.cfg',
    'samgr': 'system/etc/init/samgr_standard.cfg',
    'accesstoken_service': 'system/etc/init/access_token.cfg',
    'accountmgr': 'system/etc/init/accountmgr.cfg',
    'appspawn': 'system/etc/init/appspawn.cfg',
    'foundation': 'system/etc/init/foundation.cfg',
    'render_service': 'system/etc/init/graphic.cfg',
    'multimodalinput': 'system/etc/init/multimodalinput.cfg',
    'composer_host': 'chip_prod/etc/init/hdf_devhost.cfg',
    'allocator_host': 'chip_prod/etc/init/hdf_devhost.cfg',
}


def source_path(relative):
    if relative.startswith('system/'):
        return ROOT / 'work/ohos-runtime/system' / relative
    return ROOT / 'work/donor-configs' / relative


def data_mkdir(command):
    """Only literal directory creation inside private /data is transferable."""
    words = command.split()
    if len(words) != 5 or words[0] != 'mkdir':
        return False
    path = PurePosixPath(words[1])
    if not path.is_absolute() or '..' in path.parts or not words[1].startswith('/data/'):
        return False
    return (bool(re.fullmatch(r'/data/[A-Za-z0-9_./-]+', words[1])) and
            all(c in '01234567' for c in words[2]) and len(words[2]) in (3, 4, 5) and
            all(re.fullmatch(r'[A-Za-z0-9_-]+', w) for w in words[3:]))


def prepare():
    services, directories, omitted, hashes, edits = [], {}, [], {}, {}
    for name, relative in SOURCES.items():
        path = source_path(relative)
        raw = path.read_bytes()
        hashes[relative] = hashlib.sha256(raw).hexdigest()
        cfg = json.loads(raw)
        matches = [s for s in cfg['services'] if s['name'] == name]
        if len(matches) != 1:
            raise ValueError(f'{relative}: expected exactly one {name}')
        service = copy.deepcopy(matches[0])
        before = copy.deepcopy(service)
        # No cgroup writes, restart cascades, implicit startup, or critical reboot.
        # Retain uid/gid, SELinux domain, capabilities, tokens and socket owners.
        service.pop('jobs', None)
        service.pop('writepid', None)
        if 'critical' in service:
            service['critical'][0] = 0
        service.update(disabled=1, **{'start-mode': 'condition'})
        services.append(service)
        edits[name] = {k: {'donor': before.get(k), 'candidate': service.get(k)}
                       for k in sorted(set(before) | set(service))
                       if before.get(k) != service.get(k)}
        for job in cfg.get('jobs', []):
            for command in job.get('cmds', []):
                if data_mkdir(command):
                    dest = command.split()[1]
                    if dest in directories and directories[dest] != command:
                        raise ValueError('Conflicting directory owners/mode: ' + dest)
                    directories[dest] = command
                elif command.strip() != 'load_access_token_id':
                    entry = {'source': relative, 'job': job['name'], 'command': command}
                    if entry not in omitted:
                        omitted.append(entry)
    # RDB creates key lock files here but the donor service domain cannot
    # create this subdirectory. A fresh private filesystem needs init to
    # provision it rather than granting that domain new directory rights.
    directories['/data/service/el1/public/access_token/lock'] = (
        'mkdir /data/service/el1/public/access_token/lock 0700 access_token access_token')
    # Parent directories are needed on a fresh tmpfs, unlike an installed phone.
    parents = {'/data/service': '0711 root root', '/data/service/el0': '0711 root root',
               '/data/service/el1': '0711 root root', '/data/service/el1/public': '0711 root root',
               '/data/storage': '0711 root root'}
    for dest in list(directories):
        for parent in PurePosixPath(dest).parents:
            if str(parent) in ('/', '/data'):
                break
            parents.setdefault(str(parent), '0711 root root')
    for dest, mode_owner in parents.items():
        directories.setdefault(dest, f'mkdir {dest} {mode_owner}')
    # These two prerequisites are present in the donor root init job. Without
    # RLIMIT_NICE, native init cannot apply accesstoken_service importance -20
    # after dropping its UID. Preserve the donor values, not a guessed cap.
    root_init = source_path('system/etc/init.cfg')
    root_raw = root_init.read_bytes()
    hashes['system/etc/init.cfg'] = hashlib.sha256(root_raw).hexdigest()
    donor_commands = {command for job in json.loads(root_raw).get('jobs', [])
                      for command in job.get('cmds', [])}
    limits = ['setrlimit RLIMIT_NICE 40 40', 'setrlimit RLIMIT_NOFILE 32768 32768']
    if not set(limits) <= donor_commands:
        raise ValueError('Expected donor resource limits are missing')
    config = {'import': [], 'services': services, 'jobs': [
        {'name': 'hmos-framework-data', 'cmds': [directories[p] for p in
         sorted(directories, key=lambda p: (len(PurePosixPath(p).parts), p))]},
        {'name': 'hmos-framework-token', 'cmds': ['load_access_token_id ']},
        {'name': 'hmos-framework-resources', 'cmds': limits}]}
    report = {
        'scope': 'Offline candidate only; not imported by the current core image',
        'source_sha256': hashes, 'service_changes': edits,
        'omitted_donor_commands': omitted,
        'additional_data_prerequisites': ['access_token/lock: provision RDB lock directory before service startup'],
        'activation': 'No automatic start job; all services require explicit activation',
        'unresolved': [
            'Native SELinux policy loading and process transitions',
            'Execute builtin access-token initialization after private-data setup; native token permissions untested',
            'Private writable appspawn sandbox mounts and cgroups',
            'Account/storage initialization without physical Android userdata',
            'HDF configuration and matching OP13 display/GPU driver loading',
            'Service readiness order and SceneBoard application installation/launch',
        ],
    }
    return config, report


def main():
    config, report = prepare()
    output = ROOT / 'out/framework'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'framework.cfg').write_text(json.dumps(config, indent=2) + '\n')
    (output / 'adaptation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'Staged {len(config["services"])} services, {len(config["jobs"][0]["cmds"])} private-data directories; no activation')


if __name__ == '__main__':
    main()
