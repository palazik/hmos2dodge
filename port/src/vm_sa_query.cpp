// SPDX-License-Identifier: Apache-2.0
// Guest observer: query registration through the donor Binder client ABI.
#include <cstdio>
#include <cstdlib>
#include "iservice_registry.h"

int main(int argc, char **argv)
{
    int id = 3503;
    if (argc == 2) {
        char *end = nullptr;
        long parsed = std::strtol(argv[1], &end, 10);
        if (!end || *end || parsed < 1 || parsed > 0x7fffffffL) return 4;
        id = static_cast<int>(parsed);
    } else if (argc != 1) return 4;
    auto manager = OHOS::SystemAbilityManagerClient::GetInstance().GetSystemAbilityManager();
    if (manager == nullptr) {
        std::puts("VM-SA manager unavailable");
        return 2;
    }
    auto object = manager->CheckSystemAbility(id);
    std::printf("VM-SA id=%d registered=%s\n", id, object != nullptr ? "true" : "false");
    // A null reply can also be an access denial; do not infer service absence.
    return object != nullptr ? 0 : 3;
}
