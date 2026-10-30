#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check donor identities and fresh-data directory prerequisites offline."""
import json
from pathlib import PurePosixPath
from prepare_framework import ROOT, SOURCES, data_mkdir, prepare, source_path

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
assert '/data/samgr' in created
assert '/data/service/el1/public/access_token' in created
assert '/data/service/el1/public/database/bundle_manager_service' in created
print('PASS: ten donor service identities preserved; activation disabled; private-data parents ordered')
