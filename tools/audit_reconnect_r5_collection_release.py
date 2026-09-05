"""Read-only source/fixture/staged-byte release gate with runtime predicates disabled."""
from datetime import datetime, timezone
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verify_reconnect_r5_collection import replay_fresh, verify_lock, SOURCES, LOCK
from tools.verify_reconnect_r5_journal import save, sha


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--development", required=True)
    parser.add_argument("--final", required=True)
    args = parser.parse_args()
    verify_lock()
    results = {}
    for label, directory in (("development", args.development), ("final", args.final)):
        root = (ROOT/directory).resolve()
        assert root.is_relative_to((ROOT/"evidence/verification").resolve())
        manifest = json.loads((root/"manifest.json").read_bytes())["captured_file_sha256"]
        assert set(manifest) == {p.name for p in root.iterdir() if p.is_file() and p.name != "manifest.json"}
        assert all(Path(n).name == n and sha((root/n).read_bytes()) == h for n, h in manifest.items())
        report = json.loads((root/"verification.json").read_bytes())
        assert report["verification_passed"] and report["development_only"] is (label == "development")
        assert report["evidence_label"] == "fixture" and not report["network_execution_authorized"] and not report["whole_protocol_verified"]
        with zipfile.ZipFile(root/"sources.zip") as archive:
            assert len(archive.namelist()) == len(report["source_sha256"]) and set(archive.namelist()) == set(report["source_sha256"])
            assert all(sha(archive.read(n)) == h for n, h in report["source_sha256"].items())
            if label == "final":
                assert set(archive.namelist()) == set((*SOURCES, LOCK))
                assert all(archive.read(n) == (ROOT/n).read_bytes() for n in archive.namelist())
        cases = {}
        for name, entry in report["cases"].items():
            with tempfile.TemporaryDirectory(prefix="safetwin-r5-collection-release-") as temporary:
                target = Path(temporary)/"fresh"
                with zipfile.ZipFile(root/(name+".zip")) as archive:
                    expected = entry["member_sha256"]
                    assert len(archive.namelist()) == len(expected) and set(archive.namelist()) == set(expected)
                    assert all(Path(n).name == n and sha(archive.read(n)) == h for n, h in expected.items())
                    archive.extractall(target)
                assert all(sha((target/n).read_bytes()) == h for n, h in expected.items())
                bundle = json.loads((target/"capture.json").read_bytes())
                with ExitStack() as stack:
                    for predicate in ("evaluate", "precheck", "validate_row", "recovery_candidate", "identity", "source_address", "log_lines", "trace_rows", "ping_result", "account_window"):
                        stack.enter_context(patch("sandbox.reconnect_r5_collection."+predicate, side_effect=AssertionError("candidate predicate forbidden during independent release audit")))
                    replay_fresh(bundle, target)
                cases[name] = dict(passed=True, expected_audit_error=bundle["audit_error"], collections=len(bundle["windows"]))
        results[label] = dict(passed=True, directory=directory, manifest_members=len(manifest), cases=cases)
    staged = [n for n in subprocess.check_output(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"], cwd=ROOT).decode().split("\0") if n]
    assert staged
    for name in staged:
        assert not name.startswith(("evidence/private/", "evidence/engineering/20260905T111542Z-reconnect-r3-build/", "evidence/verification/20260825T081310Z-phase7-analysis-freeze/"))
        assert subprocess.check_output(["git", "show", ":"+name], cwd=ROOT) == (ROOT/name).read_bytes(), name
    output = ROOT/"evidence/engineering"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-reconnect-r5-collection-release")
    output.mkdir(exist_ok=False)
    save(output/"release.json", dict(release_audit_passed=True, results=results, runtime_predicates_disabled=True,
                                    staged_file_sha256={n: sha((ROOT/n).read_bytes()) for n in staged}, auditor_sha256=sha(Path(__file__).read_bytes()),
                                    evidence_label="fixture", network_trials_executed=0, network_fix_validated=False, whole_protocol_verified=False))
    save(output/"manifest.json", dict(captured_file_sha256={"release.json": sha((output/"release.json").read_bytes())}))
    print(json.dumps(dict(output=str(output), release_audit_passed=True, staged_files=len(staged), cases_replayed=sum(len(r["cases"]) for r in results.values()))))


if __name__ == "__main__":
    raise SystemExit(main())
