import hashlib
import json
from pathlib import Path
import shutil

import pytest

from tools.audit_reconnect_r3_build_v2 import audit as build_audit
from tools.audit_reconnect_r3_release import RELEASE, audit
from tools.publish_reconnect_r3_build import commitment, sanitize_services


def rehash(run):
    data = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in run.iterdir() if p.is_file() and p.name != "manifest.json"}
    (run / "manifest.json").write_text(json.dumps({"captured_file_sha256": data}))


def mutate_json(run, name, change):
    value = json.loads((run / name).read_bytes()); change(value)
    (run / name).write_text(json.dumps(value))
    rehash(run)


def test_publishable_release_is_verified_fixture_only():
    result = audit()
    assert result["release_audit_passed"] and not result["raw_configurations_published"]
    assert not result["private_transform_verified"] and result["build"]["build_verified"]
    assert result["build"]["network_trials"] == 0 and not result["build"]["network_fix_validated"]


def test_new_image_lock_matches_measured_image_binaries_and_patch():
    from tools.audit_reconnect_r3_build import sums
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / "config/experiments/reconnect-r3-images.json").read_bytes())
    summary = json.loads((RELEASE / "summary.json").read_bytes())
    binaries = sums((RELEASE / "bin-after.sha256").read_bytes())
    assert lock["derived_image_id"] == summary["derived_image_id"]
    assert lock["derived_tag"] == summary["derived_image_tag"]
    assert lock["derived_gnb_sha256"] == binaries["/opt/ueransim/bin/nr-gnb"]
    assert lock["derived_ue_sha256"] == binaries["/opt/ueransim/bin/nr-ue"]
    assert lock["instrumentation_patch_sha256"] == hashlib.sha256((RELEASE / "instrumentation.diff").read_bytes()).hexdigest()
    assert not lock["sandbox_image_applied"] and not lock["network_fix_validated"]


def test_hmac_commitments_preserve_equality_not_plain_secrets():
    value = {"Env": ["PASSWORD=private-example-value"]}
    key = b"x" * 32
    assert commitment(value, key) == commitment(value, key)
    assert commitment(value, key) != commitment(value, b"y" * 32)
    assert "private-example-value" not in json.dumps(commitment(value, key))


def test_sanitizer_omits_health_logs_and_environment_values():
    from tests.test_reconnect_r3_build import services
    rows = services(); rows[0]["Config"] = {"Env": ["TOKEN=private-example-value"]}
    rows[0]["State"]["Health"] = {"Log": "private-example-value"}
    result = sanitize_services(rows, b"x" * 32)
    assert "private-example-value" not in json.dumps(result)
    assert "Health" not in result[0]["State"]


@pytest.mark.parametrize("key,value", [("network_fix_validated", True), ("sandbox_image_applied", True), ("TNSM_ready", True), ("network_trials", 4)])
def test_hash_consistent_claim_promotion_rejected(tmp_path, key, value):
    run = tmp_path / "release"; shutil.copytree(RELEASE, run)
    mutate_json(run, "summary.json", lambda row: row.update({key: value}))
    with pytest.raises(ValueError): build_audit(run)


def test_extra_build_privilege_rejected_even_with_manifest_updated(tmp_path):
    run = tmp_path / "release"; shutil.copytree(RELEASE, run)
    mutate_json(run, "commands.json", lambda rows: next(row for row in rows if row["name"] == "docker-build")["argv"].insert(2, "--allow=security.insecure"))
    with pytest.raises(ValueError, match="command scope"): build_audit(run)


def test_compiler_input_replacement_rejected_even_with_manifest_updated(tmp_path):
    run = tmp_path / "release"; shutil.copytree(RELEASE, run)
    mutate_json(run, "commands.json", lambda rows: next(row for row in rows if row["name"] == "docker-build").update(stdin_sha256="0" * 64))
    with pytest.raises(ValueError, match="input linkage"): build_audit(run)


def test_unredacted_private_fields_rejected_by_release_schema(tmp_path):
    run = tmp_path / "release"; shutil.copytree(RELEASE, run)
    data = json.loads((run / "redaction.json").read_bytes())
    data["raw_evidence_kept_local"] = False
    (run / "redaction.json").write_text(json.dumps(data)); rehash(run)
    with pytest.raises(ValueError, match="private evidence disclosure"): audit(run)
