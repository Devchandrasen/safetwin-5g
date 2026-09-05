import copy
from pathlib import Path

import pytest

from tools.audit_reconnect_r3_build import preserve_services
from tools.audit_reconnect_r3_build_v2 import audit, canonical_services

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "evidence/engineering/20260905T111542Z-reconnect-r3-build"


def pair():
    from tests.test_reconnect_r3_build import services
    before = services()
    before[0]["Mounts"] = [{"Destination": "/a", "Source": "volume-a", "RW": False}, {"Destination": "/b", "Source": "volume-b", "RW": True}]
    after = copy.deepcopy(before); after[0]["Mounts"].reverse()
    return before, after


def test_order_regression_fails_v1_and_passes_v2_without_mutating_input():
    before, after = pair(); original = copy.deepcopy(after)
    with pytest.raises(ValueError, match="Mounts"): preserve_services(before, after)
    preserve_services(canonical_services(before), canonical_services(after))
    assert after == original


@pytest.mark.parametrize("key,value", [("Source", "another"), ("RW", True), ("Destination", "/changed")])
def test_real_mount_mutation_remains_rejected(key, value):
    before, after = pair(); after[0]["Mounts"][1][key] = value
    with pytest.raises(ValueError, match="Mounts"):
        preserve_services(canonical_services(before), canonical_services(after))


def test_duplicate_mount_destination_is_not_silently_deduplicated():
    before, after = pair(); after[0]["Mounts"][1]["Destination"] = "/b"
    with pytest.raises(ValueError, match="ambiguous"): canonical_services(after)


def test_raw_build_v2_integrity_not_network_recovery():
    # A source-only checkout uses the separately audited redacted release.
    if not RUN.exists(): pytest.skip("private raw Docker snapshot retained only on collection host")
    result = audit(RUN)
    assert result["build_verified"] and result["upstream_tracked_files"] == 4267
    assert not result["network_fix_validated"] and result["network_trials"] == 0
