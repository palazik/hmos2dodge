#!/usr/bin/env python3
"""Fetch only display build headers from OpenHarmony mirrors and the donor port."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'work/ohos-headers'
REPOSITORIES = {'hdf_core': 'drivers_hdf_core'}
PREFIXES = {
    'drivers_interface': ['display/'],
    'drivers_peripheral': ['display/buffer/hdi_service/include/', 'display/composer/hdi_service/include/', 'display/utils/include/'],
    'hdf_core': ['interfaces/inner_api/utils/', 'interfaces/inner_api/osal/shared/', 'interfaces/inner_api/osal/uhdf/',
                 'interfaces/inner_api/hdi/', 'interfaces/inner_api/ipc/', 'interfaces/inner_api/core/'],
    'graphic_graphic_surface': ['interfaces/inner_api/utils/'],
    'commonlibrary_c_utils': ['base/include/'],
    'communication_ipc': ['interfaces/innerkits/ipc_core/include/'],
    'hiviewdfx_hilog': ['interfaces/native/innerkits/include/'],
    'hiviewdfx_hitrace': ['interfaces/native/innerkits/include/hitrace_meter/'],
    'third_party_libdrm': ['include/drm/', 'libsync.h', 'xf86drm.h', 'xf86drmMode.h'],
    'third_party_bounds_checking_function': ['include/'],
}


def read_url(url):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'op13-hmos-display-build'})
            with urllib.request.urlopen(request, timeout=35) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404 or attempt == 2: raise
        except Exception:
            if attempt == 2: raise
        time.sleep(attempt + 1)


def index_repo(repo):
    remote = REPOSITORIES.get(repo, repo)
    directory = DEST / repo
    directory.mkdir(parents=True, exist_ok=True)
    index = directory / '.tree.json'
    ref_file = directory / '.ref'
    if index.exists() and ref_file.exists():
        return repo, ref_file.read_text().strip(), json.loads(index.read_text())
    for ref in ('OpenHarmony-5.1.0-Release', 'OpenHarmony-v5.1.0-Release'):
        try:
            data = read_url(f'https://api.github.com/repos/openharmony/{remote}/git/trees/{ref}?recursive=1')
            tree = json.loads(data)
            if tree.get('truncated'): raise RuntimeError('truncated source tree')
            index.write_bytes(data)
            ref_file.write_text(ref + '\n')
            return repo, ref, tree
        except urllib.error.HTTPError as exc:
            if exc.code != 404: raise
    raise RuntimeError('release not found: ' + repo)


jobs = []
with ThreadPoolExecutor(max_workers=3) as executor:
    for repo, ref, tree in executor.map(index_repo, PREFIXES):
        count = 0
        for item in tree['tree']:
            name = item['path']
            if item['type'] != 'blob' or not name.endswith(('.h', '.hpp', '.inc')): continue
            if not any(name.startswith(p) for p in PREFIXES[repo]): continue
            if '..' in Path(name).parts: raise RuntimeError('unexpected source path')
            remote = REPOSITORIES.get(repo, repo)
            jobs.append((DEST / repo / name, f'https://raw.githubusercontent.com/openharmony/{remote}/{ref}/{name}'))
            count += 1
        print(f'{repo}: {count} headers ({ref})', flush=True)

tree = json.loads((ROOT / 'work/reference-tree.json').read_text())
for repo, name in [
    ('drivers_peripheral', 'display/composer/hdi_service/include/idisplay_composer_vdi_v1_1.h'),
    ('drivers_interface', 'display/composer/v1_2/include/idisplay_composer_interface.h'),
]:
    jobs.append((ROOT / 'work/abi-headers/OpenHarmony-v5.0.3-Release' / repo / name,
                 f'https://raw.githubusercontent.com/openharmony/{repo}/OpenHarmony-v5.0.3-Release/{name}'))
for item in tree['tree']:
    name = item['path']
    if item['type'] == 'blob' and name.startswith('src/display/hdi-gen/') and name.endswith('.h'):
        jobs.append((ROOT / 'work/reference-source' / name,
                     'https://raw.githubusercontent.com/tsryzenstech/hmos2sweet/main/' + name))


def fetch(job):
    path, url = job
    if not path.exists():
        data = read_url(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return {'path': str(path.relative_to(ROOT)), 'url': url, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


with ThreadPoolExecutor(max_workers=8) as executor:
    manifest = list(executor.map(fetch, jobs))
(ROOT / 'port/docs/display-header-sources.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(f'Fetched/verified {len(manifest)} display headers', flush=True)
