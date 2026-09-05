// Executes the actual copied nnsf.cpp function against interface fixtures.
#include "task.hpp"
#include <iostream>
#include <string>

using namespace nr::gnb;

int main(int argc, char **argv)
{
    GnbConfig config{{999, 70, false}, {{{1, std::nullopt}}}};
    TaskBase base{&config};
    PlmnSupport support{config.plmn, config.nssai};
    NgapAmfContext amf{EAmfState::CONNECTED, {&support}};
    NgapTask task{&base, {{1, &amf}}};
    auto select = [&](int32_t request) { return task.selectAmf(17, request); };
    if (argc == 2 && std::string(argv[1]) == "--official-counterexample")
    {
        if (select(1) != &amf || select(2) != nullptr || select(-1) != nullptr)
            return 3;
        std::cout << "OFFICIAL_COUNTEREXAMPLE: explicit SST 1 selects; unsupported SST 2 rejects; absent SST -1 rejects despite one connected compatible AMF\n";
        return 0;
    }
    int failures = 0, cases = 0;
    auto check = [&](bool ok, const char *label) {
        ++cases;
        std::cout << (ok ? "PASS " : "FAIL ") << label << '\n';
        failures += !ok;
    };
    check(select(1) == &amf, "explicit-supported-sst");
    check(select(-1) == &amf, "absent-sst-unique-compatible-default");
    check(select(2) == nullptr, "explicit-mismatch-no-fallback");
    check(select(-2) == nullptr && select(256) == nullptr, "invalid-sst-range");
    support.sliceSupportList.slices.push_back({1, std::nullopt});
    check(select(-1) == &amf && select(1) == &amf, "duplicate-slice-is-one-amf");
    support.sliceSupportList = config.nssai;
    for (auto state : {EAmfState::NOT_CONNECTED, EAmfState::WAITING_NG_SETUP})
    {
        amf.state = state;
        check(select(-1) == nullptr && select(1) == nullptr, "disconnected-or-unready-amf");
    }
    amf.state = EAmfState::CONNECTED;
    support.plmn.mcc = 998;
    check(select(-1) == nullptr && select(1) == nullptr, "wrong-plmn");
    support.plmn = config.plmn;
    support.plmn.isLongMnc = true;
    check(select(-1) == nullptr && select(1) == nullptr, "mnc-length-mismatch");
    support.plmn = config.plmn;
    support.sliceSupportList.slices[0].sd = 7;
    check(select(-1) == nullptr, "default-sd-mismatch");
    support.sliceSupportList = config.nssai;
    config.nssai.slices.clear();
    check(select(-1) == nullptr, "no-configured-default");
    config.nssai = support.sliceSupportList;
    NgapAmfContext second{EAmfState::CONNECTED, {&support}};
    task.m_amfCtx[2] = &second;
    check(select(-1) == nullptr && select(1) == nullptr, "ambiguous-two-compatible-amfs");
    second.state = EAmfState::NOT_CONNECTED;
    check(select(-1) == &amf && select(1) == &amf, "one-connected-candidate");
    task.m_amfCtx.clear();
    check(select(-1) == nullptr && select(1) == nullptr, "no-amf");
    task.m_amfCtx[1] = nullptr;
    check(select(-1) == nullptr && select(1) == nullptr, "null-amf");
    task.m_amfCtx[1] = &amf;
    amf.plmnSupportList = {nullptr};
    check(select(-1) == nullptr && select(1) == nullptr, "null-plmn-support");
    std::cout << "FIXTURE_CASES=" << cases << " FAILURES=" << failures << '\n';
    return failures ? 1 : 0;
}
