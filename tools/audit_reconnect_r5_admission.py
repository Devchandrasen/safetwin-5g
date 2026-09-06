"""Independent, fresh filesystem replay of an UNRESERVED admission snapshot.

Uses Git archive instead of the candidate's batch-object reader. Does not import
candidate code, reserve a receipt, authenticate a human or authorize execution.
This is a contemporaneous file audit, not an offline experiment/clock audit.
"""
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile


def audit(root, report, *, revision, lock_digest, approval_digest, output, observed_at):
    root = Path(os.path.abspath(root))
    def check(value, message):
        if not value:
            raise ValueError(message)
    def digest(raw):
        return hashlib.sha256(raw).hexdigest()
    def json_bytes(raw):
        check(len(raw) <= 1048576, "JSON size")
        def pairs(items):
            value = {}
            for key, item in items:
                check(key not in value, "duplicate JSON key")
                value[key] = item
            return value
        def invalid(_):
            raise ValueError("nonfinite JSON")
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid)
    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    def path(name):
        check(type(name) is str and re.fullmatch(r"[A-Za-z0-9_./-]+", name), "path syntax")
        rel = PurePosixPath(name)
        check(not rel.is_absolute() and rel.as_posix() == name and ".." not in rel.parts, "path traversal")
        value = root.joinpath(*rel.parts)
        for p in (value, *value.parents):
            try:
                s = p.lstat()
            except FileNotFoundError:
                continue
            check(not stat.S_ISLNK(s.st_mode) and not getattr(s, "st_file_attributes", 0) & 0x400, "linked audit path")
        return value
    def read(name):
        p = path(name)
        s = p.stat()
        check(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_size <= 8388608, "unsafe audit file")
        value = p.read_bytes()
        t = p.stat()
        check(len(value) == s.st_size and all(getattr(s, k) == getattr(t, k) for k in
              ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")), "audit file changed")
        return value
    def git(*argv):
        check(not any(n in os.environ for n in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
              "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")), "audit redirected Git environment")
        # Git archive honours core.autocrlf. Override it for this read only;
        # never alter global/local settings or normalize evidence afterwards.
        result = subprocess.run(["git", "--no-replace-objects", "-c", "core.autocrlf=false", *argv], cwd=root, capture_output=True, timeout=30,
            env=dict(os.environ, GIT_NO_REPLACE_OBJECTS="1", GIT_OPTIONAL_LOCKS="0"),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        check(result.returncode == 0 and not result.stderr and len(result.stdout) <= 16777216, "audit Git failed")
        return result.stdout
    for value, length in ((revision, 40), (lock_digest, 64), (approval_digest, 64)):
        check(type(value) is str and re.fullmatch("[0-9a-f]{"+str(length)+"}", value), "audit pins required")
    check(re.fullmatch(r"evidence/engineering/[0-9]{8}T[0-9]{6}Z-reconnect-r5-network", output), "audit output scope")
    check(Path(git("rev-parse", "--show-toplevel").decode().strip()).resolve() == root.resolve(), "audit repository root")
    check(git("rev-parse", "HEAD").decode().strip() == revision, "audit HEAD changed")
    lock_name = "config/experiments/reconnect-r5-admission-lock.json"
    lock_raw = read(lock_name)
    check(digest(lock_raw) == lock_digest, "audit lock pin")
    lock = json_bytes(lock_raw)
    cid = "safetwin5g-reconnect-r5-file-admission-v1"
    check(type(lock) is dict and set(lock) == {"lock_id", "evidence_label", "native_execution_enabled", "network_execution_authorized", "source_sha256"}, "audit lock keys")
    check(lock["lock_id"] == cid and lock["evidence_label"] == "fixture" and lock["native_execution_enabled"] is False
          and lock["network_execution_authorized"] is False, "audit lock scope")
    # Independently anchor every pre-existing frozen release, including negatives.
    frozen = {
        "reconnect-r3-execution": "d4d763d241b097a39ed2399c0b9bf3a8bbce35a68cc1e4392b9c7296d67e26fc",
        "reconnect-r4-collection": "de219c80803a83584d171511e0be0e5bc24dfbd349f4be61668539bed707d9c5",
        "reconnect-r4-execution": "122b2285104c407eb68bbcb5e7183adc06c25e16c45e91e868dade95425a4da6",
        "reconnect-r5-clock": "0e2b17156f3aab4d1b9fa8bdf48727561ea1f10051291746e754ac86009c6cf4",
        "reconnect-r5-journal": "a2c000563b7b9674369968fd861e0b02d11896e847bfbb70d25c0e7063abe67b",
        "reconnect-r5-process": "97f529e39d4c40ba66a3f31c4ad6f0bfbca6348bb380f09065a7c08eda4cae0e",
        "reconnect-r5-host": "9d50ac6cb85f6a13ecd373a4a6c4f3add86eb23a3b5941ea330fcf18a48671a9",
        "reconnect-r5-collection": "3f10ad67b9b2af7b643f8c3fe4bf33084a99f71827b9dbabb6e81d02de0cf352",
        "reconnect-r5-budget": "b730c374485d3f5666e19efebb33cd2323648ed1c9f6af05d028810a5fb031f8",
        "reconnect-r5-execution": "c51512faa71b2c6d53271d68b79c34c60276358e9d0f3d406e4dbc46732c09e9",
    }
    required = {}
    for stem, checksum in frozen.items():
        name = "config/experiments/"+stem+"-lock.json"
        raw = read(name)
        check(digest(raw) == checksum, "audit historical lock changed")
        old = json_bytes(raw)
        entries = {name: checksum, **old["source_sha256"], **old.get("immutable_dependency_sha256", {})}
        for n, h in entries.items():
            check(n not in required or required[n] == h, "audit inconsistent dependency")
            required[n] = h
    new = {"sandbox/reconnect_r5_admission.py", "tools/audit_reconnect_r5_admission.py",
           "tools/verify_reconnect_r5_admission.py", "tests/test_reconnect_r5_admission.py", "docs/RECONNECT_R5_ADMISSION.md"}
    hashes = lock["source_sha256"]
    check(type(hashes) is dict and set(hashes) == set(required) | new and all(hashes[n] == h for n, h in required.items()), "audit source closure")
    hashes = {**hashes, lock_name: lock_digest}
    for n, h in hashes.items():
        path(n)
        check(type(h) is str and re.fullmatch("[0-9a-f]{64}", h), "audit digest syntax")
    archive = git("archive", "--format=tar", revision, "--", *sorted(hashes))
    actual = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        for member in tar:
            if member.isdir():
                continue
            check(member.isfile() and member.name in hashes and member.name not in actual, "unexpected archive member")
            raw = tar.extractfile(member).read()
            check(raw == read(member.name) and digest(raw) == hashes[member.name], "audit uncommitted source")
            actual[member.name] = dict(sha256=digest(raw), size=len(raw),
                git_blob=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest())
    check(set(actual) == set(hashes), "audit archive omitted inputs")
    check(not git("diff", "--cached", "--name-only", revision, "--", *sorted(hashes)), "audit staged source drift")
    policy = json_bytes(read("config/actions.json"))
    check(policy["allow_live_actuation"] is False and policy["require_human_approval"] is True, "audit policy")
    raw = read("evidence/private/reconnect-r5-approval.json")
    check(digest(raw) == approval_digest, "audit approval digest")
    approval = json_bytes(raw)
    expected = dict(contract_id=cid, protocol_id="safetwin5g-reconnect-r5-execution-v1", repository_head=revision,
        admission_lock_sha256=lock_digest, status="approved", approved_by="user", type="explicit-single-sandbox-diagnostic",
        environment="sandbox", maximum_attempts=1, output_path=output,
        trials=["r5:control-before", "r5:drop-a", "r5:drop-b", "r5:control-after"],
        containers=["safetwin5g-open5gs", "safetwin5g-gnb", "safetwin5g-ue"],
        image_ids=["sha256:13705fc29922cf019e8c7992b5b04b9c6c584d3848d29689f1d3db64334ae725",
                   "sha256:0c9773889f62ee848144b359349014ea8200c5edab995c303a3d38a75cc70c32"],
        rollback_plan="owned qdisc; independent official gNB and UE images; core,gNB,UE reset and health; fresh PDU; all 15 packets; telemetry; scope; owned host cleanup",
        live_actuation=False, operator_validation=False)
    check(type(approval) is dict and set(approval) == set(expected) | {"recorded_at", "expires_at"} and
          canonical({k: approval[k] for k in expected}) == canonical(expected), "audit approval scope")
    check(all(type(x) is str for x in (approval["recorded_at"], approval["expires_at"], observed_at)), "audit timestamp types")
    dates = [datetime.fromisoformat(x) for x in (approval["recorded_at"], approval["expires_at"], observed_at)]
    check(all(x.tzinfo is not None for x in dates), "audit approval timezone")
    start, end, now = dates
    check(start <= now < end and 0 < (end-start).total_seconds() <= 3600, "audit approval lifetime")
    for name in ("evidence/private/reconnect-r3-runtime.lock", "evidence/private/reconnect-r4-runtime.lock",
                 "evidence/private/reconnect-r5-runtime.lock", output):
        check(not path(name).exists(), "audit prior guard/output")
    check(not any(p.name.endswith("-reconnect-r5-network") for p in path("evidence/engineering").iterdir()), "audit prior attempt")
    check(git("rev-parse", "HEAD").decode().strip() == revision and read("evidence/private/reconnect-r5-approval.json") == raw,
          "audit authority changed during replay")
    result = dict(contract_id=cid, file_gate_passed=True, repository_head=revision, admission_lock_sha256=lock_digest,
        approval_sha256=approval_digest, output_path=output, receipt_path="evidence/private/reconnect-r5-runtime.lock",
        observed_at=observed_at, sources=actual, reserved=False, native_execution_enabled=False,
        network_execution_authorized=False, human_identity_verified=False, measurement_timing_verified=False, evidence_label="fixture")
    check(canonical(report) == canonical(result), "candidate file snapshot mismatch")
    return dict(file_audit_passed=True, source_count=len(actual), evidence_label="fixture",
                network_execution_authorized=False, native_execution_enabled=False,
                audit_scope="contemporaneous-unreserved-files-only")
