# Attribution and component licenses

This project adapts portions of
https://github.com/tsryzenstech/hmos2sweet at commit
`1be080c325fee50622d4fdbd996e1dc96717feba`. The upstream project and its
contributors retain their copyrights. Its display implementation derives
from OpenHarmony drivers_peripheral and generated HDI interfaces.

- `port/display/src/`: upstream hmos2sweet/OpenHarmony display sources, with
  OP13 adaptations. Apache-2.0; retain per-file copyright and license notices.
- `port/display/*.patch`: modifications to that Apache-2.0 display code.
- `port/kernel/`: modifications to Linux/Android kernel code and the Huawei
  access-token driver, adapted through hmos2sweet. GPL-2.0; upstream notices
  are preserved in the patch. The complete kernel is not distributed here.
- `port/src/`: MIT where stated in the source.
- Original project scripts, documentation and tests: Apache-2.0 unless a
  per-file notice states otherwise.

Apache-2.0 is reproduced in `LICENSE`; the Linux kernel's GPL-2.0 text is in
`LICENSES/GPL-2.0.txt`. Upstream component provenance and header-source metadata
are recorded in `port/docs/`. Proprietary donor and stock images, libraries,
firmware and the local SDK/sysroot are excluded from this source repository.
