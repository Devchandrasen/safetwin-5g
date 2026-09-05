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
struct Logger { template<class... Args> void debug(Args...) {} };
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
    Logger *m_logger;
    std::array<PduSession *, 16> m_pduSessions{};
    void handleUplinkDataRequest(int psi, OctetString &&data);
    void handleUplinkStatusChange(int psi, bool isPending);
};

// UPSTREAM_METHODS

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
        std::cout << "FIXTURE_CASES=" << cases << " FAILURES=0\n"
                  << "IDLE_FIRST_PACKET_FORWARDED=0\nAFTER_CONNECT_INPUT_PACKET=2\n"
                  << "IDLE_BURST_REPLAYED=0\nNETWORK_PROOF=0\n";
        return cases == 60 ? 0 : 43;
    } catch (const std::exception &error) {
        std::cerr << "FIXTURE_FAILURE=" << error.what() << " COMPLETED_CASES=" << cases << '\n';
        return 42;
    }
}
