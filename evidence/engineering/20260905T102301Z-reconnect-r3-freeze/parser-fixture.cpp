#include <cstdio>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
// SafeTwin R3 instrumentation only. No queue, timer, packet mutation or retry.
#pragma once
#include <cstddef>
#include <cstdint>

namespace safetwin_r3 {
struct Identity {
    unsigned ipid{}, id{}, sequence{}, bytes{};
    unsigned long long fingerprint{};
};

inline unsigned be16(const unsigned char *data) {
    return (static_cast<unsigned>(data[0]) << 8) | data[1];
}

inline bool identify(const unsigned char *data, std::size_t size, Identity &identity) {
    if (!data || size < 28 || size > 65535 || (data[0] >> 4) != 4) return false;
    const std::size_t ihl = (data[0] & 15u) * 4u;
    if (ihl < 20 || ihl + 8 > size || be16(data + 2) != size) return false;
    // Reserved/MF/offset reject; DF is permitted. Only the fixed sandbox flow.
    if ((be16(data + 6) & 0xbfffu) || data[9] != 1) return false;
    const unsigned char flow[] = {10, 45, 0, 2, 10, 45, 0, 1};
    for (unsigned i = 0; i < 8; ++i) if (data[12 + i] != flow[i]) return false;
    if (data[ihl] != 8 || data[ihl + 1] != 0) return false;
    const unsigned id = be16(data + ihl + 4), sequence = be16(data + ihl + 6);
    if (id < 10001 || id > 10099 || sequence < 1 || sequence > 5) return false;
    unsigned long long fingerprint = 14695981039346656037ull;
    for (std::size_t i = 0; i < size; ++i) {
        fingerprint ^= data[i];
        fingerprint *= 1099511628211ull;
    }
    identity = {be16(data + 4), id, sequence, static_cast<unsigned>(size), fingerprint};
    return true;
}

template<class Logger, class Packet>
inline void emit(Logger *logger, const Packet &packet, const char *stage,
                 int psi, int actor, int connected, int mm, int active, int pending) {
    if (!logger || psi != 1) return;
    Identity identity;
    if (!identify(reinterpret_cast<const unsigned char *>(packet.data()), packet.length(), identity)) return;
    logger->debug("ST3 stage=%s psi=%d actor=%d cm=%d mm=%d ps=%d pending=%d ipid=%u id=%u seq=%u bytes=%u fp=%llu",
                  stage, psi, actor, connected, mm, active, pending, identity.ipid,
                  identity.id, identity.sequence, identity.bytes, identity.fingerprint);
}
} // namespace safetwin_r3


std::string packet(unsigned id = 10001, unsigned sequence = 1, unsigned ihl = 20) {
    std::string value(84, '\0');
    value[0] = static_cast<char>(0x40u | (ihl / 4)); value[3] = 84;
    value[4] = 0x12; value[5] = 0x34; value[8] = 64; value[9] = 1;
    const unsigned char flow[] = {10,45,0,2,10,45,0,1};
    for (int i = 0; i < 8; ++i) value[12 + i] = static_cast<char>(flow[i]);
    value[ihl] = 8; value[ihl + 4] = static_cast<char>(id >> 8);
    value[ihl + 5] = static_cast<char>(id); value[ihl + 6] = static_cast<char>(sequence >> 8);
    value[ihl + 7] = static_cast<char>(sequence);
    return value;
}
struct Logger {
    std::vector<std::string> lines;
    template<class... Args> void debug(const char *format, Args... args) {
        char text[512]; std::snprintf(text, sizeof(text), format, args...); lines.emplace_back(text);
    }
};
int main() {
    int cases = 0;
    auto require = [&](bool condition) { if (!condition) throw std::runtime_error("parser case " + std::to_string(cases)); ++cases; };
    try {
        safetwin_r3::Identity identity;
        auto accepts = [&](const std::string &value) {
            return safetwin_r3::identify(reinterpret_cast<const unsigned char *>(value.data()), value.size(), identity);
        };
        auto value = packet(); auto original = value;
        require(accepts(value)); require(identity.id == 10001 && identity.sequence == 1 && identity.ipid == 4660 && identity.bytes == 84);
        require(value == original);
        require(!safetwin_r3::identify(nullptr, 84, identity));
        for (unsigned length = 0; length < 28; ++length) require(!accepts(value.substr(0, length)));
        for (unsigned ihl = 0; ihl < 5; ++ihl) { auto bad = value; bad[0] = static_cast<char>(0x40 + ihl); require(!accepts(bad)); }
        auto bad = value; bad[0] = 0x65; require(!accepts(bad));
        bad = value; bad[3] = 83; require(!accepts(bad));
        bad = value; bad[3] = 85; require(!accepts(bad));
        bad = value; bad[9] = 17; require(!accepts(bad));
        for (int offset = 12; offset < 20; ++offset) { bad = value; bad[offset] ^= 1; require(!accepts(bad)); }
        bad = value; bad[6] = 0x20; require(!accepts(bad));
        bad = value; bad[7] = 1; require(!accepts(bad));
        bad = value; bad[6] = static_cast<char>(0x80); require(!accepts(bad));
        bad = value; bad[6] = 0x40; require(accepts(bad));
        bad = value; bad[20] = 0; require(!accepts(bad));
        bad = value; bad[21] = 1; require(!accepts(bad));
        require(!accepts(packet(10000))); require(!accepts(packet(10100)));
        require(!accepts(packet(10001, 0))); require(!accepts(packet(10001, 6)));
        require(accepts(packet(10099, 5))); require(accepts(packet(10001, 1, 24)));
        require(!accepts(std::string(65536, '\0')));
        Logger logger;
        safetwin_r3::emit(&logger, value, "nas_in", 1, 0, 0, 7, -1, -1);
        require(logger.lines.size() == 1 && value == original);
        safetwin_r3::emit(&logger, value, "nas_in", 2, 0, 0, 7, -1, -1);
        require(logger.lines.size() == 1);
        safetwin_r3::emit(static_cast<Logger *>(nullptr), value, "nas_in", 1, 0, 0, 7, -1, -1);
        require(logger.lines.size() == 1);
        std::cout << "PARSER_CASES=" << cases << " FAILURES=0\n" << logger.lines[0] << '\n';
        return 0;
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 42; }
}
