// Minimal interface fixture, not the UERANSIM production types or a network.
#pragma once
#include <cstdint>
#include <optional>
#include <unordered_map>
#include <vector>

namespace nr::gnb
{
struct Plmn { int mcc{}, mnc{}; bool isLongMnc{}; };
inline bool operator!=(const Plmn &a, const Plmn &b)
{ return a.mcc != b.mcc || a.mnc != b.mnc || a.isLongMnc != b.isLongMnc; }
struct SingleSlice { uint8_t sst{}; std::optional<int> sd{}; };
inline bool operator==(const SingleSlice &a, const SingleSlice &b)
{ return a.sst == b.sst && a.sd == b.sd; }
struct NetworkSlice { std::vector<SingleSlice> slices{}; };
struct PlmnSupport { Plmn plmn{}; NetworkSlice sliceSupportList{}; };
enum class EAmfState { NOT_CONNECTED, WAITING_NG_SETUP, CONNECTED };
struct NgapAmfContext { EAmfState state{}; std::vector<PlmnSupport *> plmnSupportList{}; };
struct GnbConfig { Plmn plmn{}; NetworkSlice nssai{}; };
struct TaskBase { GnbConfig *config{}; };
class NgapTask
{
public:
    TaskBase *m_base{};
    std::unordered_map<int, NgapAmfContext *> m_amfCtx{};
    NgapAmfContext *selectAmf(int, int32_t &);
    NgapAmfContext *selectNewAmfForReAllocation(int, int, int);
    NgapAmfContext *findAmfContext(int id) { return m_amfCtx.at(id); }
};
}
