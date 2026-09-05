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
