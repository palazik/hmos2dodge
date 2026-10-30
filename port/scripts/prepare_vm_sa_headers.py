#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fetch pinned upstream samgr query headers, validating Git blob identities."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
manifest = json.loads((ROOT / 'port/docs/samgr-query-sources.json').read_text())
destination = ROOT / 'work/ohos-headers/systemabilitymgr_samgr'
for entry in manifest['headers']:
    relative = Path(entry['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Invalid header path')
    path = destination / relative
    def matches(data):
        return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == entry['git_blob_sha1']
    if path.is_file() and matches(path.read_bytes()):
        continue
    url = f"https://raw.githubusercontent.com/{manifest['repository']}/{manifest['commit']}/{relative.as_posix()}"
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read()
    if not matches(data):
        raise ValueError('Upstream header identity mismatch: ' + str(relative))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
print('Verified pinned samgr headers')
