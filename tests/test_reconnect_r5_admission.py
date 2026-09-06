"""Real temporary Git/filesystem fixtures; no daemon, socket or native APIs."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
from unittest.mock import patch

import pytest
from sandbox import reconnect_r5_admission as candidate
from tools.audit_reconnect_r5_admission import audit

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = "evidence/engineering/20260906T020000Z-reconnect-r5-network"
TIME = "2026-09-06T02:00:00+00:00"


def write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def git(root, *args):
    return subprocess.check_output(["git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false",
        "-c", "user.name=SafeTwin fixture", "-c", "user.email=fixture@invalid", *args], cwd=root, stderr=subprocess.STDOUT)


def build(root):
    root.mkdir()
    hashes = candidate.dependency_hashes(ROOT)
    for name in candidate.NEW_SOURCES:
        hashes[name] = candidate.sha((ROOT/name).read_bytes())
    for name in hashes:
        write(root/name, (ROOT/name).read_bytes())
    lock = dict(lock_id=candidate.ID, evidence_label="fixture", native_execution_enabled=False,
                network_execution_authorized=False, source_sha256=hashes)
    write(root/candidate.LOCK, candidate.encoded(lock)+b"\n")
    git(root, "init", "-q")
    git(root, "add", "--", *sorted(hashes), candidate.LOCK)
    git(root, "commit", "-q", "-m", "Temporary file admission fixture only")
    (root/"evidence/private").mkdir(parents=True, exist_ok=True)
    (root/"evidence/engineering").mkdir(parents=True, exist_ok=True)
    return approve(root)


def approve(root, edit=None, raw_edit=None):
    revision = git(root, "rev-parse", "HEAD").decode().strip()
    lock_digest = candidate.sha((root/candidate.LOCK).read_bytes())
    approval = candidate.approval_fields(revision, lock_digest, OUTPUT)
    approval.update(recorded_at="2026-09-06T01:59:00+00:00", expires_at="2026-09-06T02:59:00+00:00")
    if edit:
        edit(approval)
    raw = candidate.encoded(approval)+b"\n"
    if raw_edit:
        raw = raw_edit(raw)
    write(root/candidate.APPROVAL, raw)
    return candidate.FileAdmission(root, revision=revision, lock_digest=lock_digest,
        approval_digest=candidate.sha(raw), output=OUTPUT)


@pytest.fixture
def gate(tmp_path_factory, request):
    # Full pytest node names plus retained evidence paths exceeded MAX_PATH.
    # A stable short case directory preserves isolation and the original names
    # in metadata without changing global Windows/Git settings.
    case = tmp_path_factory.getbasetemp()/("a"+hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:10])
    case.mkdir(exist_ok=False)
    write(case/"case.json", candidate.encoded(dict(nodeid=request.node.nodeid, evidence_label="fixture"))+b"\n")
    original_run = subprocess.run
    def local_git_only(argv, *args, **kwargs):
        assert argv[0] == "git", "no other process allowed in these fixtures"
        return original_run(argv, *args, **kwargs)
    with patch("subprocess.run", side_effect=local_git_only), \
         patch("socket.socket", side_effect=AssertionError("network forbidden")), \
         patch("ctypes.WinDLL", side_effect=AssertionError("native API forbidden"), create=True):
        yield build(case/"admission-fixture")


def independent(gate, report):
    return audit(gate.root, report, revision=gate.revision, lock_digest=gate.lock_digest,
                 approval_digest=gate.approval_digest, output=gate.output, observed_at=TIME)


def test_committed_file_gate_and_candidate_disabled_audit(gate):
    report = gate.recheck(observed_at=TIME)
    with patch.object(candidate.FileAdmission, "recheck", side_effect=AssertionError("candidate disabled")), \
         patch.object(candidate, "committed_files", side_effect=AssertionError("candidate disabled")), \
         patch.object(candidate, "dependency_hashes", side_effect=AssertionError("candidate disabled")):
        result = independent(gate, report)
    write(gate.root.parent/"admission-report.json", candidate.encoded(report)+b"\n")
    write(gate.root.parent/"independent-report.json", candidate.encoded(result)+b"\n")
    assert result["file_audit_passed"] and result["source_count"] > 100
    assert not report["human_identity_verified"] and not report["network_execution_authorized"]
    assert not (gate.root/candidate.RECEIPT).exists() and not (gate.root/OUTPUT).exists()


@pytest.mark.parametrize("field,value", [
    ("status", "pending"), ("approved_by", "agent"), ("type", "standing-project-authorization"),
    ("environment", "live"), ("maximum_attempts", True), ("maximum_attempts", 2),
    ("live_actuation", 0), ("operator_validation", 0), ("rollback_plan", ""),
    ("repository_head", "a"*40), ("admission_lock_sha256", "b"*64),
    ("trials", ["r5:drop-a"]), ("image_ids", []), ("containers", []),
    ("output_path", "../outside"), ("expires_at", "2026-09-06T02:00:00+00:00"),
    ("expires_at", "2026-09-06T04:00:00+00:00"), ("recorded_at", "2026-09-06T02:01:00+00:00"),
    ("recorded_at", "2026-09-06T01:59:00"),
])
def test_exact_prior_approval_semantics(gate, field, value):
    gate = approve(gate.root, lambda a: a.update({field: value}))
    with pytest.raises((ValueError, PermissionError)):
        gate.recheck(observed_at=TIME)
    with pytest.raises((ValueError, PermissionError)):
        independent(gate, {})
    assert not (gate.root/candidate.RECEIPT).exists()


@pytest.mark.parametrize("raw_edit", [
    lambda b: b[:-2]+b',"maximum_attempts":1}\n',
    lambda b: b.replace(b'"maximum_attempts":1', b'"maximum_attempts":NaN'),
    lambda b: b'\xff', lambda b: b' '*1048577, lambda b: b'[]',
])
def test_malformed_approval(gate, raw_edit):
    gate = approve(gate.root, raw_edit=raw_edit)
    with pytest.raises((ValueError, PermissionError, TypeError)):
        gate.recheck(observed_at=TIME)
    with pytest.raises((ValueError, PermissionError, TypeError)):
        independent(gate, {})


@pytest.mark.parametrize("mode", ["working", "staged", "head", "missing", "lock", "approval-whitespace", "approval-missing"])
def test_real_file_and_revision_drift(gate, mode):
    source = gate.root/"sandbox/reconnect_r5_admission.py"
    original = source.read_bytes()
    if mode in ("working", "staged"):
        source.write_bytes(original+b"\n# fixture drift\n")
        if mode == "staged":
            git(gate.root, "add", "--", "sandbox/reconnect_r5_admission.py")
            source.write_bytes(original)
    elif mode == "head":
        git(gate.root, "commit", "--allow-empty", "-q", "-m", "Fixture HEAD drift")
    elif mode == "missing":
        source.rename(source.with_suffix(".missing"))
    elif mode == "lock":
        with (gate.root/candidate.LOCK).open("ab") as stream:
            stream.write(b" ")
    elif mode == "approval-whitespace":
        with (gate.root/candidate.APPROVAL).open("ab") as stream:
            stream.write(b" ")
    else:
        (gate.root/candidate.APPROVAL).rename(gate.root/"evidence/private/missing-approval.json")
    with pytest.raises((ValueError, OSError)):
        gate.recheck(observed_at=TIME)
    with pytest.raises((ValueError, OSError)):
        independent(gate, {})


@pytest.mark.parametrize("mode", ["missing-source", "extra-source", "enable-native", "enable-network", "tier"])
def test_committed_manifest_cannot_weaken_contract(gate, mode):
    path = gate.root/candidate.LOCK
    lock = json.loads(path.read_bytes())
    if mode == "missing-source":
        lock["source_sha256"].pop("sandbox/run_reconnect_r5.py")
    elif mode == "extra-source":
        lock["source_sha256"]["../outside"] = "a"*64
    elif mode == "enable-native":
        lock["native_execution_enabled"] = True
    elif mode == "enable-network":
        lock["network_execution_authorized"] = True
    else:
        lock["evidence_label"] = "sandbox-measured"
    path.write_bytes(candidate.encoded(lock)+b"\n")
    git(gate.root, "add", "--", candidate.LOCK)
    git(gate.root, "commit", "-q", "-m", "Rejected fixture manifest")
    gate = approve(gate.root)
    with pytest.raises(PermissionError):
        gate.recheck(observed_at=TIME)
    with pytest.raises(ValueError):
        independent(gate, {})


@pytest.mark.parametrize("name", [*candidate.OLDER_GUARDS, candidate.RECEIPT,
    "evidence/engineering/20000101T000000Z-reconnect-r5-network", OUTPUT])
def test_prior_attempt_and_older_guards_preserved(gate, name):
    sentinel = b"unowned fixture, do not alter\n"
    write(gate.root/name, sentinel)
    with pytest.raises(PermissionError):
        gate.reserve(observed_at=TIME)
    with pytest.raises(ValueError):
        independent(gate, {})
    assert (gate.root/name).read_bytes() == sentinel


def test_reservation_is_persistent_and_never_reopens(gate):
    assert gate.reserve(observed_at=TIME)["reserved"]
    receipt = (gate.root/candidate.RECEIPT).read_bytes()
    assert gate.recheck(observed_at=TIME)["reserved"]
    gate.close()
    assert (gate.root/candidate.RECEIPT).read_bytes() == receipt
    with pytest.raises(PermissionError):
        gate.reserve(observed_at=TIME)
    another = approve(gate.root)
    with pytest.raises(PermissionError):
        another.reserve(observed_at=TIME)
    assert (gate.root/candidate.RECEIPT).read_bytes() == receipt


def test_revocation_latches_even_if_approval_restored(gate):
    gate.reserve(observed_at=TIME)
    p = gate.root/candidate.APPROVAL
    original = p.read_bytes()
    p.write_bytes(original+b" ")
    with pytest.raises(PermissionError, match="approval bytes"):
        gate.recheck(observed_at=TIME)
    p.write_bytes(original)
    with pytest.raises(PermissionError, match="permanently closed"):
        gate.recheck(observed_at=TIME)
    gate.close()
    assert (gate.root/candidate.RECEIPT).exists()


def test_failed_receipt_fsync_consumes_attempt(gate):
    with patch("os.fsync", side_effect=OSError("fixture fsync failure")):
        with pytest.raises(OSError, match="fixture fsync failure"):
            gate.reserve(observed_at=TIME)
    receipt = (gate.root/candidate.RECEIPT).read_bytes()
    assert gate.closed and gate.failure
    with pytest.raises(PermissionError):
        approve(gate.root).reserve(observed_at=TIME)
    assert (gate.root/candidate.RECEIPT).read_bytes() == receipt


def test_two_actual_filesystem_contenders_only_one_reserves(gate):
    second = approve(gate.root)
    rendezvous = threading.Barrier(2)
    original = Path.open
    def race(p, mode="r", *args, **kwargs):
        if p == gate.root/candidate.RECEIPT and mode == "xb":
            rendezvous.wait(timeout=30)
        return original(p, mode, *args, **kwargs)
    def acquire(g):
        try:
            return g.reserve(observed_at=TIME)["reserved"]
        except OSError:
            return False
    with patch.object(Path, "open", race), ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(acquire, [gate, second]))
    gate.close(); second.close()
    assert sorted(outcomes) == [False, True]
    assert json.loads((gate.root/candidate.RECEIPT).read_bytes())["network_execution_authorized"] is False


def test_hardlinked_approval_rejected(gate):
    p = gate.root/candidate.APPROVAL
    os.link(p, p.with_name("linked-approval.json"))
    with pytest.raises(PermissionError, match="unsafe file"):
        gate.recheck(observed_at=TIME)
    with pytest.raises(ValueError, match="unsafe audit file"):
        independent(gate, {})


@pytest.mark.parametrize("field,value", [("file_gate_passed", False), ("network_execution_authorized", True),
    ("native_execution_enabled", True), ("reserved", True), ("evidence_label", "sandbox-measured"),
    ("human_identity_verified", True), ("sources", {}), ("observed_at", "2026-09-06T02:00:01+00:00")])
def test_independent_auditor_rejects_summary_tampering(gate, field, value):
    report = gate.recheck(observed_at=TIME)
    report[field] = value
    with pytest.raises(ValueError, match="snapshot mismatch"):
        independent(gate, report)


@pytest.mark.parametrize("output", ["../outside", "/tmp/output", "evidence\\engineering\\x", OUTPUT+"/..", OUTPUT+":stream"])
def test_constructor_path_scope(gate, output):
    with pytest.raises(PermissionError):
        candidate.FileAdmission(gate.root, revision=gate.revision, lock_digest=gate.lock_digest,
                                approval_digest=gate.approval_digest, output=output)


def test_check_cli_has_no_execution_or_reservation_option():
    result = subprocess.run([os.fspath(ROOT/".venv/Scripts/python.exe"), "-m", "sandbox.reconnect_r5_admission", "--help"],
                            cwd=ROOT, capture_output=True, timeout=20)
    assert result.returncode == 0
    assert b"--execute" not in result.stdout and b"--reserve" not in result.stdout


def test_archive_audit_ignores_global_or_local_autocrlf(gate):
    git(gate.root, "config", "core.autocrlf", "true")
    report = gate.recheck(observed_at=TIME)
    assert independent(gate, report)["file_audit_passed"]
    assert git(gate.root, "config", "--local", "--get", "core.autocrlf").strip() == b"true"


@pytest.mark.parametrize("name", ["GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"])
def test_redirected_git_environment_is_rejected(gate, name):
    with patch.dict(os.environ, {name: str(gate.root)}):
        with pytest.raises(PermissionError, match="redirected Git"):
            gate.recheck(observed_at=TIME)
        with pytest.raises(ValueError, match="redirected Git"):
            independent(gate, {})


@pytest.mark.parametrize("mode", ["receipt", "output"])
def test_owned_paths_cannot_be_substituted(gate, mode):
    gate.reserve(observed_at=TIME)
    if mode == "receipt":
        # Append through a second handle, without replacing or deleting evidence.
        with (gate.root/candidate.RECEIPT).open("ab") as stream:
            stream.write(b"changed\n")
    else:
        p = gate.root/OUTPUT
        p.rename(p.with_name(p.name+"-displaced"))
        p.mkdir()
    with pytest.raises(PermissionError, match="owned .* changed"):
        gate.recheck(observed_at=TIME)
    gate.close()


def test_authoritative_admission_manifest_matches_all_working_sources():
    lock = candidate.strict((ROOT/candidate.LOCK).read_bytes())
    expected = candidate.dependency_hashes(ROOT)
    expected.update({n: candidate.sha((ROOT/n).read_bytes()) for n in candidate.NEW_SOURCES})
    assert lock == dict(lock_id=candidate.ID, evidence_label="fixture", native_execution_enabled=False,
                        network_execution_authorized=False, source_sha256=expected)
    assert all(candidate.sha((ROOT/n).read_bytes()) == h for n, h in expected.items())
