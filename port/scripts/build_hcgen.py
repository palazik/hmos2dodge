#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build pinned OpenHarmony hc-gen locally with lossless decompiler fixes."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
REVISION = '617c08a5b414c27fcc00baf78d9b3af8915e74ba'
REPO = 'openharmony/drivers_hdf_core'
PREFIX = 'framework/tools/hc-gen/'


def download(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'hmos2dodge-offline-tools'})
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read()


def main():
    source = ROOT / 'work/hc-gen-source'
    source.mkdir(parents=True, exist_ok=True)
    tree = json.loads(download(f'https://api.github.com/repos/{REPO}/git/trees/{REVISION}?recursive=1'))
    if tree.get('truncated'):
        raise RuntimeError('Truncated upstream source tree')
    entries = [e for e in tree['tree'] if e['type'] == 'blob' and e['path'].startswith(PREFIX)
               and (e['path'].endswith(('.cpp', '.h')) or e['path'] == PREFIX + 'CMakeLists.txt')
               and '/test/' not in e['path']]

    def fetch(entry):
        data = download(f'https://raw.githubusercontent.com/{REPO}/{REVISION}/{entry["path"]}')
        digest = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
        if digest != entry['sha']:
            raise RuntimeError('Upstream blob mismatch: ' + entry['path'])
        name = entry['path'][len(PREFIX):]
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return name, digest

    with ThreadPoolExecutor(max_workers=8) as pool:
        hashes = dict(pool.map(fetch, entries))
    path = source / 'src/decompile_gen.cpp'
    text = path.read_text()
    anchor = 'outStr << "\\\"" << astObj->StringValue() << "\\\"";'
    if text.count(anchor) != 1:
        raise RuntimeError('Unexpected upstream decompiler')
    path.write_text(text.replace('#include <sstream>', '#include <sstream>\n#include <iomanip>')
                   .replace(anchor, 'outStr << std::quoted(astObj->StringValue());'))
    path = source / 'src/lexer.cpp'
    text = path.read_text()
    if text.count('strtoll(') != 4:
        raise RuntimeError('Unexpected upstream integer lexer')
    path.write_text(text.replace('strtoll(', 'strtoull('))
    build = ROOT / 'work/hc-gen-build'
    subprocess.run(['cmake', '-S', str(source), '-B', str(build), '-DCMAKE_BUILD_TYPE=Release',
                    '-DCMAKE_CXX_FLAGS_RELEASE=-O2 -include cstdint'], check=True)
    subprocess.run(['cmake', '--build', str(build), '-j8'], check=True)
    output = ROOT / 'out/hdf'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'tool-source.json').write_text(json.dumps({
        'repository': REPO, 'revision': REVISION, 'original_git_blobs': hashes,
        'local_changes': ['quote embedded strings when decompiling',
                          'parse full uint64 range instead of signed overflow',
                          'force-include cstdint for current host compiler'],
        'binary_sha256': hashlib.sha256((build / 'hc-gen').read_bytes()).hexdigest(),
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
