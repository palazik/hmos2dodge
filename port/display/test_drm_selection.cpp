/* SPDX-License-Identifier: Apache-2.0 */
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <unistd.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <vector>

struct Card {
    bool dumb = true;
    bool resources = true;
    uint32_t type = DRM_MODE_CONNECTOR_DSI;
    drmModeConnection state = DRM_MODE_CONNECTED;
    int modes = 1;
};
static std::vector<Card> cards;
static std::vector<int> closed;
static int resource_count, connector_count;

static int FakeOpen(const char *path, int flags, ...)
{
    unsigned card = 999;
    int end = 0;
    assert(sscanf(path, "/dev/dri/card%u%n", &card, &end) == 1);
    assert(path[end] == '\0');
    assert(flags == (O_RDWR | O_CLOEXEC));
    if (card >= cards.size()) { errno = ENOENT; return -1; }
    return static_cast<int>(card) + 100;
}
static int FakeClose(int fd) { closed.push_back(fd); return 0; }
static int FakeGetCap(int fd, uint64_t cap, uint64_t *value)
{
    assert(cap == DRM_CAP_DUMB_BUFFER);
    *value = cards.at(fd - 100).dumb;
    return 0;
}
static drmModeRes *FakeGetResources(int fd)
{
    if (!cards.at(fd - 100).resources) return nullptr;
    auto *r = new drmModeRes{};
    r->count_connectors = 1;
    r->connectors = new uint32_t[1]{static_cast<uint32_t>(fd)};
    resource_count++;
    return r;
}
static void FakeFreeResources(drmModeRes *r)
{
    delete[] r->connectors; delete r; resource_count--;
}
static drmModeConnector *FakeGetConnector(int fd, uint32_t id)
{
    assert(id == static_cast<uint32_t>(fd));
    const auto &card = cards.at(fd - 100);
    auto *c = new drmModeConnector{};
    c->connector_type = card.type;
    c->connection = card.state;
    c->count_modes = card.modes;
    connector_count++;
    return c;
}
static void FakeFreeConnector(drmModeConnector *c) { delete c; connector_count--; }

#define open FakeOpen
#define close FakeClose
#define drmGetCap FakeGetCap
#define drmModeGetResources FakeGetResources
#define drmModeFreeResources FakeFreeResources
#define drmModeGetConnector FakeGetConnector
#define drmModeFreeConnector FakeFreeConnector
#include "ohos_drm_device.h"
#undef open
#undef close

static void test(const char *name, std::vector<Card> devices, int expected, std::vector<int> rejected)
{
    cards = devices; closed.clear();
    char path[64] = {};
    int fd = OhosOpenInternalDrm(path, sizeof(path));
    assert(fd == expected);
    assert(closed == rejected);
    assert(resource_count == 0 && connector_count == 0);
    if (fd >= 0) {
        char wanted[64]; snprintf(wanted, sizeof(wanted), "/dev/dri/card%d", fd - 100);
        assert(!strcmp(wanted, path));
    } else assert(errno == ENODEV);
    printf("PASS DRM selection: %s\n", name);
}

int main()
{
    Card external; external.type = DRM_MODE_CONNECTOR_VIRTUAL;
    Card disconnected; disconnected.state = DRM_MODE_DISCONNECTED;
    Card no_mode; no_mode.modes = 0;
    Card no_dumb; no_dumb.dumb = false;
    Card no_resources; no_resources.resources = false;
    test("internal panel on card1", {external, Card{}}, 101, {100});
    test("disconnected connector rejected", {disconnected, Card{}}, 101, {100});
    test("connector without modes rejected", {no_mode, Card{}}, 101, {100});
    test("non-dumb allocator device rejected", {no_dumb, Card{}}, 101, {100});
    test("resource query failure closes fd", {no_resources, Card{}}, 101, {100});
    test("virtual display never selected", {external}, -1, {100});
    test("missing DRM device", {}, -1, {});
}
