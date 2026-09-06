"""Lossless R5 integration release, including failed pre-correction sources.

Only explicitly named R5 verification directories are read. Originals are
NEVER deleted, rewritten or retimed. Fresh final extraction is independently
replayed with candidate acceptance and process/socket/native APIs disabled.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_reconnect_r5_execution import audit_path


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def package(source, output, replay=False):
    source = source.resolve()
    assert source.parent == ROOT/"evidence/verification" and re.fullmatch(r"\d{8}T\d{6}Z-reconnect-r5-execution", source.name), "explicit verification scope"
    files = {p.relative_to(source).as_posix(): p for p in source.rglob("*") if p.is_file()}
    assert all(p.resolve().is_relative_to(source) and not p.is_symlink() for p in files.values()), "no external archive files"
    original_manifest = json.loads((source/"manifest.json").read_bytes())["sha256"]
    auxiliary = set(files)-set(original_manifest)-{"manifest.json"}
    assert set(original_manifest) <= set(files), "original evidence inventory missing"
    # One later collect-only diagnostic can produce bytecode when it discovers
    # archived tests. Preserve and explicitly inventory these auxiliary bytes;
    # NEVER rewrite the original verification manifest to include them.
    assert all("__pycache__" in Path(n).parts and n.endswith(".pyc") for n in auxiliary), "unexplained post-capture file"
    for n, h in original_manifest.items():
        assert sha(files[n].read_bytes()) == h, "original bytes changed: "+n
    test_report = json.loads((source/"report.json").read_bytes())
    for n, h in test_report["source_sha256"].items():
        assert sha((source/"sources"/n).read_bytes()) == h, "pre-test source bytes"
    name = source.name+".zip"
    archive_path = output/name
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n, path in sorted(files.items()):
            z.writestr(n, path.read_bytes())
    members = {n: sha(p.read_bytes()) for n, p in files.items()}
    with zipfile.ZipFile(archive_path) as z:
        assert set(z.namelist()) == set(members) and len(z.namelist()) == len(members) and z.testzip() is None
        assert all(sha(z.read(n)) == h for n, h in members.items()), "lossless archive verification"
        cases = []
        if replay:
            assert test_report["pytest_exit"] == 0 and test_report["source_unchanged"] and test_report["full_regression"]
            assert test_report["verification_passed"] and all(sha((ROOT/n).read_bytes()) == h for n, h in test_report["source_sha256"].items()), "final sources or verification drift"
            with tempfile.TemporaryDirectory(prefix="safetwin-r5-release-") as temporary:
                target = Path(temporary)
                assert all(not Path(n).is_absolute() and ".." not in Path(n).parts for n in z.namelist())
                z.extractall(target)
                from sandbox import run_reconnect_r5, reconnect_r5_budget, reconnect_r5_collection, reconnect_r5_host
                with patch.object(run_reconnect_r5.Runner, "execute", side_effect=AssertionError("candidate disabled")), \
                     patch.object(run_reconnect_r5, "clean", side_effect=AssertionError("candidate disabled")), \
                     patch.object(reconnect_r5_budget.RunnerBudget, "health", side_effect=AssertionError("candidate disabled")), \
                     patch.object(reconnect_r5_collection.Collector, "collect", side_effect=AssertionError("candidate disabled")), \
                     patch.object(reconnect_r5_host.HostGuard, "snapshot", side_effect=AssertionError("candidate disabled")), \
                     patch("subprocess.Popen", side_effect=AssertionError("release replay process forbidden")), \
                     patch("socket.socket", side_effect=AssertionError("release replay socket forbidden")), \
                     patch("ctypes.WinDLL", side_effect=AssertionError("release replay native API forbidden")):
                    for path in sorted(target.rglob("capture.json")):
                        b = json.loads(path.read_bytes())
                        if b.get("fixture_scope") != "invented-whole-protocol-no-process-no-network-no-power":
                            continue
                        record = dict(path=path.relative_to(target).as_posix(), case=b["case"], audit=None, rejection=None)
                        try:
                            record["audit"] = audit_path(path.parent)
                        except ValueError as exc:
                            assert b["case"] in ("execution-fsync", "ledger-fsync", "journal-fsync") and "storage failed" in str(exc)
                            record["rejection"] = str(exc)
                        else:
                            assert record["audit"]["protocol_execution_valid"] is (b["case"] == "complete")
                        cases.append(record)
                assert len({c["case"] for c in cases}) == 33, "complete retained case inventory"
    return dict(source=source.relative_to(ROOT).as_posix(), archive=name, archive_sha256=sha(archive_path.read_bytes()),
                members=members, auxiliary_post_capture={n: members[n] for n in sorted(auxiliary)},
                original_pytest_exit=test_report["pytest_exit"], original_source_unchanged=test_report["source_unchanged"],
                lossless_bytes_verified=True, final_independent_replay=replay, cases=cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--final", required=True, type=Path)
    args = parser.parse_args()
    paths = [p.resolve() for p in args.directories]
    assert len(paths) == len(set(paths)) and args.final.resolve() in paths
    output = ROOT/"evidence/engineering"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-reconnect-r5-execution-release")
    output.mkdir(exist_ok=False)
    report = dict(evidence_label="fixture", records=[], release_passed=False, network_execution_authorized=False, network_fix_validated=False, TNSM_ready=False)
    try:
        for path in paths:
            report["records"].append(package(path, output, path == args.final.resolve()))
            print(path.name+": lossless archive verified", flush=True)
        report["release_passed"] = True
    finally:
        (output/"release.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        (output/"manifest.json").write_text(json.dumps({"sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file() and p.name != "manifest.json"}}, indent=2)+"\n")
        print(output, flush=True)


if __name__ == "__main__":
    main()
