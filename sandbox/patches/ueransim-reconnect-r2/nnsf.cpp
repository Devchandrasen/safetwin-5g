//
// This file is a part of UERANSIM project.
// Copyright (c) 2023 ALİ GÜNGÖR.
//
// https://github.com/aligungr/UERANSIM/
// See README, LICENSE, and CONTRIBUTING files for licensing details.
//
// SafeTwin engineering candidate R2, 2026-09-05. Not an official release.
// Only absent-slice, unambiguous, PLMN/slice-compatible fallback is added.

#include "task.hpp"

namespace nr::gnb
{

NgapAmfContext *NgapTask::selectAmf(int ueId, int32_t &requestedSliceType)
{
    if (requestedSliceType < -1 || requestedSliceType > 255)
        return nullptr;

    NgapAmfContext *selected = nullptr;
    for (auto &amf : m_amfCtx)
    {
        if (amf.second == nullptr || amf.second->state != EAmfState::CONNECTED)
            continue;
        bool eligible = false;
        for (const auto &plmnSupport : amf.second->plmnSupportList)
        {
            if (plmnSupport == nullptr || plmnSupport->plmn != m_base->config->plmn)
                continue;
            for (const auto &singleSlice : plmnSupport->sliceSupportList.slices)
            {
                if (requestedSliceType >= 0)
                {
                    // Preserve explicit SST matching; never fall back on a mismatch.
                    eligible = eligible || static_cast<int32_t>(singleSlice.sst) == requestedSliceType;
                }
                else
                {
                    // A Service Request need not carry an initial requested SST.
                    // The default candidate must overlap the configured gNB NSSAI.
                    for (const auto &configured : m_base->config->nssai.slices)
                        eligible = eligible || singleSlice == configured;
                }
            }
        }
        if (eligible)
        {
            // Never choose an arbitrary AMF from unordered-map iteration order.
            if (selected != nullptr && selected != amf.second)
                return nullptr;
            selected = amf.second;
        }
    }
    return selected;
}

NgapAmfContext *NgapTask::selectNewAmfForReAllocation(int ueId, int initiatedAmfId, int amfSetId)
{
    // TODO an arbitrary AMF is selected for now
    return findAmfContext(initiatedAmfId);
}

} // namespace nr::gnb
