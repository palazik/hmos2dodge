#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check donor identities and fresh-data directory prerequisites offline."""
import argparse
import json
from pathlib import PurePosixPath
from prepare_framework import ROOT, SOURCES, data_mkdir, prepare, source_path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--staged', action='store_true', help='Also check generated native and graphics profiles')
args = parser.parse_args()
config, report = prepare()
assert not config['import']
assert set(s['name'] for s in config['services']) == set(SOURCES)
etc = ROOT / 'work/ohos-runtime/system/system/etc'
users = {line.split(':')[0] for line in (etc / 'passwd').read_text().splitlines()}
groups = {line.split(':')[0] for line in (etc / 'group').read_text().splitlines()}
for service in config['services']:
    source = json.loads(source_path(SOURCES[service['name']]).read_bytes())
    donor = next(s for s in source['services'] if s['name'] == service['name'])
    for key in ('uid', 'gid', 'secon', 'permission', 'permission_acls', 'socket', 'caps', 'path'):
        assert service.get(key) == donor.get(key), (service['name'], key)
    assert service['disabled'] == 1 and service['start-mode'] == 'condition'
    assert not service.get('critical', [0])[0]
    assert not service.get('jobs') and not service.get('writepid')
    assert service['uid'] in users
    assert all(group in groups for group in service.get('gid', []))
    for socket in service.get('socket', []):
        assert socket['uid'] in users and socket['gid'] in groups
created = {'/data'}
for job in config['jobs']:
    if job['name'] == 'hmos-framework-token':
        assert job['cmds'] == ['load_access_token_id ']
        continue
    if job['name'] == 'hmos-framework-resources':
        assert job['cmds'] == ['setrlimit RLIMIT_NICE 40 40', 'setrlimit RLIMIT_NOFILE 32768 32768']
        continue
    assert job['name'] == 'hmos-framework-data'
    for command in job['cmds']:
        assert data_mkdir(command), command
        path = PurePosixPath(command.split()[1])
        assert str(path.parent) in created, str(path)
        created.add(str(path))
for command in ('mkdir /data/../metadata/foo 0700 root root',
                'mkdir /dev/block 0700 root root', 'mount_fstab /vendor/etc/fstab',
                'mkdir /data/${unexpected} 0700 root root',
                'mkdir /data/a 0700 root root; reboot'):
    assert not data_mkdir(command)
assert '/data/service/el1/public/access_token/lock' in created
assert '/data/samgr' in created
assert '/data/service/el1/public/access_token' in created
assert '/data/service/el1/public/database/bundle_manager_service' in created
print('PASS: ten donor service identities preserved; activation disabled; private-data parents ordered')
if args.staged:
    expected = {'hilogd', 'samgr', 'accesstoken_service', 'huks_service',
                'accountmgr', 'appspawn', 'foundation', 'installs'}
    extra = {'render_service', 'multimodalinput', 'composer_host', 'allocator_host'}
    for name in ('native', 'graphics'):
        directory = ROOT / 'out/framework' / name
        staged = json.loads((directory / 'etc/init.cfg').read_text())
        names = {s['name'] for s in staged['services']}
        assert names == expected | (extra if name == 'graphics' else set())
        assert len(names) == len(staged['services']) and not staged['import']
        for service in staged['services']:
            relative = SOURCES.get(service['name'], 'system/etc/init/' + service['name'] + '.cfg')
            source = json.loads(source_path(relative).read_text())
            donor = next(s for s in source['services'] if s['name'] == service['name'])
            for key in ('uid', 'gid', 'secon', 'permission', 'permission_acls', 'socket', 'caps', 'path'):
                assert donor.get(key) == service.get(key), (name, service['name'], key)
        for job in staged['jobs']:
            for command in job['cmds']:
                assert '/dev/block' not in command and '/dev/pids' not in command, command
                assert command.split()[0] not in ('mount', 'mount_fstab', 'format', 'reboot', 'reset'), command
                if command.startswith('start '):
                    assert command.split()[1] in names
        manifest = json.loads((directory / 'manifest.json').read_text())
        assert not manifest['observer_policy_included'] and not manifest['physical_userdata_mounted']
        assert not manifest['native_phone_tested'] and not manifest['sceneboard_started']
    print('PASS: native/graphics staged identities retained; exact service lists; no physical-storage startup commands')
