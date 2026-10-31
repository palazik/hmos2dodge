#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Image source contract for the isolated HMOS bootstrap and OP13 hardware base."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def payload_sources(profile):
    sources = {name + '.img': ROOT / 'hmos5' / (name + '.img')
               for name in ('system', 'vendor', 'chip_prod', 'sys_prod', 'cust', 'patch')}
    if profile == 'framework':
        sources.update({'op13_' + name + '.img': ROOT / 'op13_stock' / (name + '.img')
                        for name in ('vendor', 'odm')})
    return sources


def expected_hashes(profile):
    expected = {Path(name).name: digest for line in (ROOT / 'port/docs/input-images.sha256').read_text().splitlines()
                for digest, name in [line.split(maxsplit=1)]}
    if profile == 'framework':
        for name in ('vendor', 'odm'):
            record = json.loads((ROOT / 'op13_stock' / (name + '.json')).read_text())
            if record['partition'] != name or not record['partition_hash_verified']:
                raise ValueError('Stock partition lacks verified payload extraction: ' + name)
            expected['op13_' + name + '.img'] = record['sha256']
    return {name: expected[name] for name in payload_sources(profile)}


def verify_sources(profile):
    expected = expected_hashes(profile)
    for name, path in payload_sources(profile).items():
        if path.is_symlink() or not path.is_file():
            raise ValueError('Expected a regular source image: ' + str(path))
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected[name]:
            raise ValueError('Source image changed: ' + str(path))
    return expected
