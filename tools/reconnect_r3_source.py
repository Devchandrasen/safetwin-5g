"""Deterministic, additions-only instrumentation overlay on the retained R2 tree."""
import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RETAINED = ROOT / "evidence/engineering/20260905T091635Z-reconnect-packet-diagnosis"
HEADER = ROOT / "sandbox/patches/ueransim-reconnect-r3-trace/safetwin_trace_r3.hpp"
SOURCES = ("src/ue/nas/sm/sap.cpp", "src/ue/rls/ctl_task.cpp", "src/gnb/gtp/task.cpp")


def additions():
    cm = "static_cast<int>(m_mm->m_cmState == ECmState::CM_CONNECTED)"
    mm = "static_cast<int>(state)"
    state = "static_cast<int>(m_pduSessions[psi]->psState == EPsState::ACTIVE), static_cast<int>(m_pduSessions[psi]->uplinkPending)"
    def log(stage, packet, actor="0", context="-1, -1, -1, -1"):
        return f'    safetwin_r3::emit(m_logger.get(), {packet}, "{stage}", psi, {actor}, {context});\n'
    return {
        SOURCES[0]: [
            ("include", '#include "sm.hpp"\n', '#include <utils/safetwin_trace_r3.hpp>\n'),
            ("nas-in", "void NasSm::handleUplinkDataRequest(int psi, OctetString &&data)\n{\n    auto state = m_mm->m_mmSubState;\n", log("nas_in", "data", context=f"{cm}, {mm}, -1, -1")),
            ("nas-forward", "    if (m_mm->m_cmState == ECmState::CM_CONNECTED)\n    {\n", log("nas_forward", "data", context=f"{cm}, {mm}, {state}")),
            ("nas-idle", "    else\n    {\n", log("nas_idle", "data", context=f"{cm}, {mm}, {state}")),
        ],
        SOURCES[1]: [
            ("include", '#include "ctl_task.hpp"\n', '#include <utils/safetwin_trace_r3.hpp>\n'),
            ("ue-rls", "void RlsControlTask::handleUplinkDataDelivery(int psi, OctetString &&data)\n{\n", log("ue_rls", "data", "m_servingCell")),
        ],
        SOURCES[2]: [
            ("include", '#include "task.hpp"\n', '#include <utils/safetwin_trace_r3.hpp>\n'),
            ("gnb-in", "void GtpTask::handleUplinkData(int ueId, int psi, OctetString &&pdu)\n{\n", log("gnb_in", "pdu", "ueId")),
            ("gnb-missing", '        m_logger->err("Uplink data failure, PDU session not found. UE[%d] PSI[%d]", ueId, psi);\n', log("gnb_missing", "pdu", "ueId")),
            ("gnb-resource", "    auto &pduSession = m_pduSessions[sessionInd];\n", log("gnb_resource", "pdu", "ueId")),
        ],
    }


def render(path, source):
    if "SAFETWIN_R3_" in source:
        raise ValueError("source already instrumented")
    for name, anchor, addition in additions()[path]:
        if source.count(anchor) != 1:
            raise ValueError("non-unique source anchor: " + path + ":" + name)
        block = f"// SAFETWIN_R3_BEGIN {name}\n{addition}// SAFETWIN_R3_END {name}\n"
        source = source.replace(anchor, anchor + block)
    return source


def strip(source):
    """Reject malformed/nested markers; remove complete instrumentation blocks."""
    pattern = r"(?m)^// SAFETWIN_R3_BEGIN ([a-z-]+)\n(?:(?!SAFETWIN_R3_).)*?^// SAFETWIN_R3_END \1\n"
    clean = re.sub(pattern, "", source, flags=re.DOTALL)
    if "SAFETWIN_R3_" in clean:
        raise ValueError("malformed instrumentation markers")
    return clean


def source_tree():
    result = {}
    for path in SOURCES:
        original = (RETAINED / ("upstream-" + path.replace("/", "-"))).read_text(encoding="utf-8")
        instrumented = render(path, original)
        if strip(instrumented) != original:
            raise ValueError("behavioral source changed")
        result[path] = instrumented.encode()
    result["src/utils/safetwin_trace_r3.hpp"] = HEADER.read_bytes()
    return result


def hashes():
    return {path: hashlib.sha256(data).hexdigest() for path, data in source_tree().items()}
