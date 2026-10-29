#!/usr/bin/env python3
"""Verify that the supplemental policy adds only the intended queried access."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def decisions(path):
    report = json.loads(path.read_text())
    return {(entry['source'], entry['target'], entry['class'], permission): allowed
            for entry in report['decisions'] for permission, allowed in entry['allowed'].items()}


baseline = decisions(ROOT / 'out/selinux/access-decisions.json')
patched = decisions(ROOT / 'out/selinux/op13-access-decisions.json')
changed = {key for key in baseline if baseline[key] != patched[key]}
expected = ('u:r:composer_host:s0', 'u:object_r:dev_dri_file:s0', 'chr_file', 'map')
assert baseline.keys() == patched.keys()
assert changed == {expected}, changed
assert not baseline[expected] and patched[expected]
assert patched[('u:r:samgr:s0', 'u:object_r:bootevent_param:s0', 'parameter_service', 'set')]
assert not patched[('u:r:samgr:s0', 'u:object_r:dev_dri_file:s0', 'chr_file', 'map')]
print('PASS queried access delta: composer DRM map added; samgr parameter access preserved; unrelated DRM map denied')

# The original donor does not pass strict compilation. Check that the new
# source introduces no additional neverallow failure locations, without
# relabeling either compilation as a strict policy pass.
reports = [json.loads((ROOT / f'out/selinux/{mode}/validation.json').read_text())
           for mode in ('strict', 'strict-op13')]
import hashlib
for report in reports:
    for name, value in report['input_sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == value, name
assert all(not report['compile_passed'] and report['neverallow_checks_enabled'] for report in reports)
locations = []
for report in reports:
    log = (ROOT / report['log']).read_text()
    locations.append(sorted(re.findall(r'neverallow check failed at ([^\n]+)', log)))
assert locations[0] and locations[0] == locations[1]
print(f'PASS no additional neverallow failure locations; strict donor and patched policies still FAIL ({len(locations[0])} reports each)')
