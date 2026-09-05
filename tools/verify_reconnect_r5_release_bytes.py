"""Retain pre-correction index normalization and verify byte-preserving release."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verify_reconnect_r5_collection import SOURCES, LOCK, verify_lock
from tools.verify_reconnect_r5_journal import save, sha


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect-mismatch", action="store_true")
    args = parser.parse_args()
    verify_lock()
    output = ROOT/"evidence/engineering"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-reconnect-r5-release-bytes")
    output.mkdir(exist_ok=False)
    names = (*SOURCES, LOCK, ".gitattributes", "tools/audit_reconnect_r5_collection_release.py", "tools/verify_reconnect_r5_release_bytes.py")
    source_hashes = {n: sha((ROOT/n).read_bytes()) for n in names}
    with zipfile.ZipFile(output/"sources.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for n in names:
            archive.writestr(n, (ROOT/n).read_bytes())
    staged = [n for n in subprocess.check_output(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"], cwd=ROOT).decode().split("\0") if n]
    assert staged and not any(n.startswith(("evidence/private/", "evidence/engineering/20260905T111542Z-reconnect-r3-build/", "evidence/verification/20260825T081310Z-phase7-analysis-freeze/")) for n in staged)
    mismatches = {}
    with zipfile.ZipFile(output/"index-working-differences.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for n in staged:
            raw = (ROOT/n).read_bytes()
            index = subprocess.check_output(["git", "show", ":"+n], cwd=ROOT)
            if raw != index:
                mismatches[n] = dict(working_sha256=sha(raw), index_sha256=sha(index), crlf_normalization_only=index == raw.replace(b"\r\n", b"\n"))
                archive.writestr("working/"+n, raw)
                archive.writestr("index/"+n, index)
    commands = {
        "attributes": ["git", "check-attr", "text", "eol", "--", "evidence/verification/20260905T224659Z-reconnect-r5-collection/tests.stdout.log", "evidence/verification/20260905T224927Z-reconnect-r5-collection/before-containers.json"],
        "release-audit": [sys.executable, "tools/audit_reconnect_r4_release.py"],
    }
    if not args.expect_mismatch:
        commands["tests"] = [sys.executable, "-m", "pytest", "-q"]
    results = {}
    for label, argv in commands.items():
        start = datetime.now(timezone.utc).isoformat()
        try:
            r = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=300 if label == "tests" else 40,
                               creationflags=subprocess.CREATE_NO_WINDOW, env=dict(os.environ, PYTHONPATH=str(ROOT/"src")+os.pathsep+str(ROOT)))
            code, stdout, stderr = r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired as exc:
            code, stdout, stderr = None, exc.stdout or b"", (exc.stderr or b"")+b"\nverification timeout\n"
        (output/(label+".stdout.log")).write_bytes(stdout)
        (output/(label+".stderr.log")).write_bytes(stderr)
        results[label] = dict(argv=argv, exit_code=code, started_at=start, completed_at=datetime.now(timezone.utc).isoformat())
        print(json.dumps(dict(check=label, exit_code=code)), flush=True)
    if args.expect_mismatch:
        passed = bool(mismatches) and all(v["crlf_normalization_only"] for v in mismatches.values()) and results["release-audit"]["exit_code"] == 1
        passed = passed and b"staged bytes differ:" in (output/"release-audit.stderr.log").read_bytes()
    else:
        passed = not mismatches and all(r["exit_code"] == 0 for r in results.values())
    passed = passed and all(sha((ROOT/n).read_bytes()) == h for n, h in source_hashes.items())
    save(output/"verification.json", dict(verification_passed=passed, expected_pre_correction_failure=args.expect_mismatch,
                                         commands=results, mismatches=mismatches, staged_files=len(staged), source_sha256=source_hashes,
                                         evidence_label="fixture", network_trials_executed=0, network_fix_validated=False))
    save(output/"manifest.json", dict(captured_file_sha256={p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}))
    print(json.dumps(dict(output=str(output), verification_passed=passed, expected_pre_correction_failure=args.expect_mismatch, mismatches=len(mismatches))))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
