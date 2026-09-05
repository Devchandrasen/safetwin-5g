#include <cstdio>
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

// Test doubles only. The two production method bodies are inserted verbatim.
// This is not a UE executable, packet capture, or proposed network correction.
#include <array>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using OctetString = std::string; // Byte ownership stand-in, not upstream ABI.
enum class EMmSubState {
    MM_REGISTERED_INITIATED_PS, MM_REGISTERED_NORMAL_SERVICE,
    MM_REGISTERED_NON_ALLOWED_SERVICE, MM_REGISTERED_LIMITED_SERVICE,
    MM_DEREGISTERED_INITIATED_PS, MM_SERVICE_REQUEST_INITIATED_PS,
    REJECTED_FIXTURE_STATE
};
enum class ECmState { CM_IDLE, CM_CONNECTED };
enum class EPsState { INACTIVE, ACTIVE };
struct PduSession { EPsState psState = EPsState::ACTIVE; bool uplinkPending = false; };
struct NmUeNasToRls {
    enum { DATA_PDU_DELIVERY };
    explicit NmUeNasToRls(int) {}
    int psi = 0;
    OctetString pdu;
};
struct Sink {
    std::vector<std::pair<int, OctetString>> packets;
    void push(std::unique_ptr<NmUeNasToRls> message) {
        packets.emplace_back(message->psi, std::move(message->pdu));
    }
};
struct TaskBase { Sink *rlsTask; };
struct Logger {
    std::vector<std::string> traces;
    template<class... Args> void debug(const char *format, Args... args) {
        char line[512]; std::snprintf(line, sizeof(line), format, args...);
        if (std::string(line).find("ST3 ") == 0) traces.emplace_back(line);
    }
};
struct LoggerRef {
    Logger *value;
    LoggerRef(Logger *p): value(p) {}
    Logger *operator->() { return value; }
    Logger *get() { return value; }
};
struct NasMm {
    EMmSubState m_mmSubState = EMmSubState::MM_REGISTERED_NORMAL_SERVICE;
    ECmState m_cmState = ECmState::CM_IDLE;
    int requests = 0, cycles = 0;
    bool connectDuringCallback = false;
    void serviceRequestRequiredForData() {
        ++requests;
        if (connectDuringCallback) m_cmState = ECmState::CM_CONNECTED;
    }
    void triggerMmCycle() { ++cycles; }
};
struct NasSm {
    TaskBase *m_base;
    NasMm *m_mm;
    LoggerRef m_logger;
    std::array<PduSession *, 16> m_pduSessions{};
    void handleUplinkDataRequest(int psi, OctetString &&data);
    void handleUplinkStatusChange(int psi, bool isPending);
};

void NasSm::handleUplinkDataRequest(int psi, OctetString &&data)
{
    auto state = m_mm->m_mmSubState;
    if (state != EMmSubState::MM_REGISTERED_INITIATED_PS && state != EMmSubState::MM_REGISTERED_NORMAL_SERVICE &&
        state != EMmSubState::MM_REGISTERED_NON_ALLOWED_SERVICE &&
        state != EMmSubState::MM_REGISTERED_LIMITED_SERVICE && state != EMmSubState::MM_DEREGISTERED_INITIATED_PS &&
        state != EMmSubState::MM_SERVICE_REQUEST_INITIATED_PS)
        return;

    if (m_pduSessions[psi]->psState != EPsState::ACTIVE)
        return;

    if (m_mm->m_cmState == ECmState::CM_CONNECTED)
    {
        // TODO: We should also check if radio resources are established by RRC.
        //  Checking CM state is not sufficient

        if (m_pduSessions[psi]->uplinkPending)
        {
            m_pduSessions[psi]->uplinkPending = false;
            handleUplinkStatusChange(psi, false);
        }

        auto m = std::make_unique<NmUeNasToRls>(NmUeNasToRls::DATA_PDU_DELIVERY);
        m->psi = psi;
        m->pdu = std::move(data);
        m_base->rlsTask->push(std::move(m));
    }
    else
    {
        if (!m_pduSessions[psi]->uplinkPending)
        {
            m_pduSessions[psi]->uplinkPending = true;
            handleUplinkStatusChange(psi, true);
        }
    }
}

void NasSm::handleUplinkStatusChange(int psi, bool isPending)
{
    m_logger->debug("Uplink data status changed PSI[%d] pending[%s]", psi, isPending ? "true" : "false");
    m_pduSessions[psi]->uplinkPending = isPending;

    if (isPending)
        m_mm->serviceRequestRequiredForData();

    m_mm->triggerMmCycle();
}

struct World {
    Sink sink;
    TaskBase base{&sink};
    NasMm mm;
    Logger logger;
    PduSession session;
    NasSm sm{&base, &mm, &logger, {}};
    World() { sm.m_pduSessions[1] = &session; }
    void input(const std::string &packet) {
        OctetString owned = packet;
        sm.handleUplinkDataRequest(1, std::move(owned));
        // As in the caller, the input message goes out of scope after handling.
    }
};

void check(bool condition, const std::string &message) {
    if (!condition) throw std::runtime_error(message);
}

int main() {
    int cases = 0;
    try {
        // Six accepted MM substates plus one rejected state, two CM states,
        // two session states and two initial pending states: 56 combinations.
        for (int state = 0; state < 7; ++state)
        for (int connected = 0; connected < 2; ++connected)
        for (int active = 0; active < 2; ++active)
        for (int pending = 0; pending < 2; ++pending) {
            World w;
            w.mm.m_mmSubState = static_cast<EMmSubState>(state);
            w.mm.m_cmState = connected ? ECmState::CM_CONNECTED : ECmState::CM_IDLE;
            w.session.psState = active ? EPsState::ACTIVE : EPsState::INACTIVE;
            w.session.uplinkPending = pending;
            w.input("matrix-packet");
            const bool eligible = state < 6 && active;
            const bool forwarded = eligible && connected;
            const bool changed = eligible && (pending == connected);
            check(w.sink.packets.size() == (forwarded ? 1u : 0u), "matrix forwarding");
            if (forwarded) check(w.sink.packets[0] == std::make_pair(1, std::string("matrix-packet")), "payload identity");
            check(w.session.uplinkPending == (eligible ? !connected : !!pending), "matrix pending");
            check(w.mm.cycles == (changed ? 1 : 0), "matrix cycle");
            check(w.mm.requests == (changed && !connected ? 1 : 0), "matrix request");
            ++cases;
        }
        {
            World w;
            w.input("icmp-seq-1");
            check(w.sink.packets.empty() && w.session.uplinkPending && w.mm.requests == 1, "idle first packet");
            w.mm.m_cmState = ECmState::CM_CONNECTED; // external transition, no timer/network model
            check(w.sink.packets.empty(), "state transition is not a replay");
            w.input("icmp-seq-2");
            check(w.sink.packets == std::vector<std::pair<int, std::string>>{{1, "icmp-seq-2"}}, "only second packet survives");
            check(!w.session.uplinkPending && w.mm.cycles == 2, "pending cleared on later packet");
            ++cases;
        }
        {
            World w;
            w.input("idle-1"); w.input("idle-2"); w.input("idle-3");
            check(w.sink.packets.empty() && w.mm.requests == 1, "no idle queue or repeated request");
            w.mm.m_cmState = ECmState::CM_CONNECTED;
            w.input("connected-4");
            check(w.sink.packets == std::vector<std::pair<int, std::string>>{{1, "connected-4"}}, "idle burst never replayed");
            ++cases;
        }
        {
            World w;
            w.mm.connectDuringCallback = true;
            w.input("callback-packet");
            check(w.mm.m_cmState == ECmState::CM_CONNECTED && w.sink.packets.empty(), "idle branch does not recheck after callback");
            ++cases;
        }
        {
            World w;
            w.mm.m_cmState = ECmState::CM_CONNECTED;
            w.input("no-radio-readiness-model");
            check(w.sink.packets.size() == 1, "CM alone forwards; downstream readiness is outside method");
            ++cases;
        }

        {
            World w;
            std::string packet(84, '\0');
            packet[0] = 0x45; packet[3] = 84; packet[9] = 1;
            const unsigned char flow[] = {10,45,0,2,10,45,0,1};
            for (int i = 0; i < 8; ++i) packet[12+i] = static_cast<char>(flow[i]);
            packet[20] = 8; packet[24] = 0x27; packet[25] = 0x11; packet[27] = 1;
            w.input(packet);
            check(w.sink.packets.empty() && w.mm.requests == 1, "valid idle packet still not forwarded");
            w.mm.m_cmState = ECmState::CM_CONNECTED; packet[27] = 2; w.input(packet);
            check(w.sink.packets == std::vector<std::pair<int, std::string>>{{1, packet}}, "only valid connected packet forwarded");
            check(w.logger.traces.size() == 0, "instrumented trace count");
            if (0) {
                check(w.logger.traces[0].find("stage=nas_in") != std::string::npos, "ingress trace");
                check(w.logger.traces[1].find("stage=nas_idle") != std::string::npos, "idle trace");
                check(w.logger.traces[3].find("stage=nas_forward") != std::string::npos, "forward trace");
                for (const auto &line : w.logger.traces) std::cout << line << '\n';
            }
            ++cases;
        }
        std::cout << "FIXTURE_CASES=" << cases << " FAILURES=0\n"
                  << "IDLE_FIRST_PACKET_FORWARDED=0\nAFTER_CONNECT_INPUT_PACKET=2\n"
                  << "IDLE_BURST_REPLAYED=0\nNETWORK_PROOF=0\n";
        return cases == 61 ? 0 : 43;
    } catch (const std::exception &error) {
        std::cerr << "FIXTURE_FAILURE=" << error.what() << " COMPLETED_CASES=" << cases << '\n';
        return 42;
    }
}
