#!/usr/bin/env python3
"""Prepare OP13 window/refresh overlays without modifying donor images."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def geometry(xml, width=1440, dpi=640):
    root = ET.fromstring(xml)
    # Android capture: centered native cutout polygon, x=-38..38, y=0..160.
    left, right = width // 2 - 38, width // 2 + 38
    values = {'dpi': str(dpi), 'cutoutArea': f'{left} 0 {right-left} 160',
              'defaultDisplayCutoutPath': f'M{left} 0 L{right} 0 L{right} 160 L{left} 160 Z',
              'curvedScreenBoundary': '0 0 0 0'}
    for name, value in values.items():
        element = root.find(name)
        if element is None:
            element = ET.SubElement(root, name)
        element.text = value
    # OP13-specific waterfall geometry is not established by this capture.
    waterfall = root.find('isWaterfallDisplay')
    if waterfall is not None:
        waterfall.set('enable', 'false')
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def refresh_policy(xml):
    root = ET.fromstring(xml)
    strategies = root.findall(".//Params[@name='refreshRate_strategy_config']/Strategy")
    if not strategies:
        raise ValueError('Missing refresh strategy section')
    rates = (60, 90, 120)

    def supported(value):
        return min(rates, key=lambda rate: (abs(rate - value), rate))

    for strategy in strategies:
        for key in ('min', 'max'):
            strategy.set(key, str(supported(int(strategy.attrib[key]))))
        # Begin with discrete KMS modes; LTPO/adaptive synchronization needs
        # native driver validation, independent of Android advertising it.
        strategy.set('dynamicMode', '0')
        for key in ('Other_SF', 'AceAnimato', 'down', 'supportAS'):
            strategy.attrib.pop(key, None)
    for element in root.iter():
        if element.tag == 'Ltpo' and element.get('name') in ('switch', 'adaptiveSync'):
            element.set('value', '0')
        if 'preferred_fps' in element.attrib and int(element.get('preferred_fps')) > 0:
            element.set('preferred_fps', str(supported(int(element.get('preferred_fps')))))
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def main():
    source = ROOT / 'work/donor-configs/sys_prod'
    output = ROOT / 'out/ui-config/overrides/sys_prod'
    transforms = {'etc/window/resources/display_manager_config.xml': geometry,
                  'etc/graphic/hgm_policy_config.xml': refresh_policy}
    report = {'native_tested': False, 'source': 'original Huawei config from provided sys_prod image',
              'geometry_evidence': '20261029-163450/display.txt: physical 1440x3168, native density 640, centered -38..38 x 0..160 cutout',
              'refresh_policy': 'discrete 60/90/120 strategies; LTPO/adaptive disabled pending native validation',
              'files': {}}
    for name, transform in transforms.items():
        original = (source / name).read_bytes()
        data = transform(original)
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        report['files']['/sys_prod/' + name] = {
            'source_sha256': hashlib.sha256(original).hexdigest(),
            'output_sha256': hashlib.sha256(data).hexdigest()}
    (ROOT / 'out/ui-config/manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
