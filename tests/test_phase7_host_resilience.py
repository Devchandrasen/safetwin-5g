from pathlib import Path

from tools.audit_phase7_host_sleep_abort import audit


ROOT = Path(__file__).resolve().parents[1]


def test_sleep_inhibition_is_narrow_and_always_cleared() -> None:
    script = (ROOT / "tools" / "run_with_sleep_inhibition.ps1").read_text(
        encoding="utf-8"
    )
    assert "$esContinuous = [uint32]2147483648" in script
    assert "$esSystemRequired = [uint32]1" in script
    assert "ES_CONTINUOUS|ES_SYSTEM_REQUIRED" in script
    assert "ES_AWAYMODE_REQUIRED" not in script
    assert "ES_DISPLAY_REQUIRED" not in script
    assert "finally {" in script
    assert "SetThreadExecutionState($esContinuous)" in script


def test_sleep_inhibition_propagates_child_exit_code() -> None:
    script = (ROOT / "tools" / "run_with_sleep_inhibition.ps1").read_text(
        encoding="utf-8"
    )
    assert "$childExitCode = $child.ExitCode" in script
    assert "exit $childExitCode" in script


def test_host_resilience_source_hashes_are_cross_clone_portable() -> None:
    script = (ROOT / "tools" / "verify_phase7_host_resilience.ps1").read_text(
        encoding="utf-8"
    )
    assert "function Get-PortableTextSha256" in script
    assert '.Replace("`r`n", "`n").Replace("`r", "`n")' in script
    assert 'files_sha256_mode = "utf8-lf-normalized"' in script


def test_abort_capture_forbids_partial_resume_and_analysis() -> None:
    script = (
        ROOT / "tools" / "capture_phase7_host_sleep_abort.ps1"
    ).read_text(encoding="utf-8")
    assert 'campaign_complete = $false' in script
    assert 'dataset_release_eligible = $false' in script
    assert 'outcome_analysis_eligible = $false' in script
    assert 'resume_permitted = $false' in script
    assert "source-index.json" in script
    assert "Application API" in script


def test_abort_auditor_rejects_positive_admissibility(tmp_path: Path) -> None:
    source = tmp_path / "source"
    diagnostic_root = tmp_path / "diagnostic"
    source.mkdir()
    diagnostic_root.mkdir()
    (source / "units").mkdir()
    (source / "units" / "unit.json").write_text("{}\n", encoding="utf-8")
    source_hash = __import__("hashlib").sha256(b"{}\n").hexdigest()
    source_index = [
        {
            "path": "units/unit.json",
            "bytes": 3,
            "last_write_utc": "2026-08-31T09:46:46Z",
            "sha256": source_hash,
        }
    ]
    (diagnostic_root / "source-index.json").write_text(
        __import__("json").dumps(source_index), encoding="utf-8"
    )
    events = [
        {"event_id": 42, "message": "Sleep Reason: Application API"},
        {"event_id": 107, "message": "resumed"},
    ]
    (diagnostic_root / "power-events.json").write_text(
        __import__("json").dumps(events), encoding="utf-8"
    )
    diagnostic = {
        "completed_trace_count": 1,
        "planned_unit_count": 675,
        "design_unit_count": 675,
        "final_manifest_present": False,
        "summary_present": False,
        "campaign_process_present_at_capture": False,
        "stderr_bytes": 0,
        "last_progress_line": "[1/675] fixture",
        "admissibility": {
            "campaign_complete": True,
            "dataset_release_eligible": False,
            "outcome_analysis_eligible": False,
            "partial_trace_reusable": False,
            "resume_permitted": False,
        },
    }
    (diagnostic_root / "diagnostic.json").write_text(
        __import__("json").dumps(diagnostic), encoding="utf-8"
    )
    manifest = {"captured_file_sha256": {}}
    (diagnostic_root / "manifest.json").write_text(
        __import__("json").dumps(manifest), encoding="utf-8"
    )

    result = audit(diagnostic_root, source)

    assert result["passed"] is False
    assert "inadmissible field is true: campaign_complete" in result["errors"]
