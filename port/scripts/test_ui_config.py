#!/usr/bin/env python3
"""Check the OP13 conversion preserves unrelated Huawei UI policy."""
import xml.etree.ElementTree as ET
from prepare_ui_config import geometry, refresh_policy, ROOT

source = ROOT / 'work/donor-configs/sys_prod'
original = ET.parse(source / 'etc/window/resources/display_manager_config.xml').getroot()
adapted = ET.fromstring(geometry(ET.tostring(original)))
assert adapted.findtext('dpi') == '640'
assert adapted.findtext('cutoutArea') == '682 0 76 160'
for key in ('castBundleName', 'castAbilityName', 'rotationPolicy', 'externalScreenDefaultMode'):
    assert adapted.findtext(key) == original.findtext(key), key
original = ET.parse(source / 'etc/graphic/hgm_policy_config.xml').getroot()
adapted = ET.fromstring(refresh_policy(ET.tostring(original)))
path = ".//Params[@name='refreshRate_strategy_config']/Strategy"
before, after = original.findall(path), adapted.findall(path)
assert [s.get('name') for s in before] == [s.get('name') for s in after]
assert any(s.get('min') == '60' and s.get('max') == '120' for s in after)
assert any(s.get('min') == s.get('max') == '90' for s in after)
for strategy in after:
    assert int(strategy.get('min')) in (60, 90, 120)
    assert int(strategy.get('max')) in (60, 90, 120)
    assert int(strategy.get('min')) <= int(strategy.get('max'))
assert ET.tostring(original.find("Params[@name='refresh_rate_4settings']")) == ET.tostring(adapted.find("Params[@name='refresh_rate_4settings']"))
try:
    refresh_policy(b'<HgmConfig/>')
except ValueError:
    pass
else:
    raise AssertionError('Missing strategies must fail')
print('PASS OP13 cutout/density; Huawei config and strategy IDs preserved; discrete 60/90/120 policy; missing-section rejection')
