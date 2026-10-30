// SPDX-License-Identifier: Apache-2.0
// Guest observer: query registration through the donor Binder client ABI.
#include <cstdio>
#include "iservice_registry.h"

int main()
{
    auto manager = OHOS::SystemAbilityManagerClient::GetInstance().GetSystemAbilityManager();
    if (manager == nullptr) {
        std::puts("VM-SA manager unavailable");
        return 2;
    }
    auto object = manager->CheckSystemAbility(3503); // Access-token manager SA.
    std::printf("VM-SA id=3503 registered=%s\n", object != nullptr ? "true" : "false");
    // A null reply can also be an access denial; do not infer service absence.
    return object != nullptr ? 0 : 3;
}
