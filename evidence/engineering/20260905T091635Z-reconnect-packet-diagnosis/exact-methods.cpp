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