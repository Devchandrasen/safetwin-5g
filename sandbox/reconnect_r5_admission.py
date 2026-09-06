"""Filesystem-only R5 admission component. No native/network execution entrypoint.

Checks are cooperative, not a defence against an administrator replacing files.
A passing check verifies bytes and scope, NOT the identity of a human approver.
The actual runner, host admission and separate execution decision remain gated.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from datetime import datetime, timezone

ID = "safetwin5g-reconnect-r5-file-admission-v1"
LOCK = "config/experiments/reconnect-r5-admission-lock.json"
APPROVAL = "evidence/private/reconnect-r5-approval.json"
RECEIPT = "evidence/private/reconnect-r5-runtime.lock"
OLDER_GUARDS = ("evidence/private/reconnect-r3-runtime.lock", "evidence/private/reconnect-r4-runtime.lock")
NEW_SOURCES = ("sandbox/reconnect_r5_admission.py", "tools/audit_reconnect_r5_admission.py",
               "tools/verify_reconnect_r5_admission.py", "tests/test_reconnect_r5_admission.py",
               "docs/RECONNECT_R5_ADMISSION.md")
FROZEN = {
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
ROLLBACK = "owned qdisc; independent official gNB and UE images; core,gNB,UE reset and health; fresh PDU; all 15 packets; telemetry; scope; owned host cleanup"


def require(value, message):
    if not value:
        raise PermissionError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def strict(raw):
    require(len(raw) <= 1048576, "JSON exceeds 1 MiB")
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, "duplicate JSON key")
            result[k] = v
        return result
    def invalid(value):
        raise PermissionError("nonfinite JSON")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid)


def timestamp(value):
    require(type(value) is str, "timestamp must be text")
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, "timezone required")
    return result


def relative(name):
    require(type(name) is str and re.fullmatch(r"[A-Za-z0-9_./-]+", name), "unsafe relative pathname")
    p = PurePosixPath(name)
    require(not p.is_absolute() and name == p.as_posix() and all(x not in (".", "..") for x in p.parts), "unsafe relative pathname")
    return p


def path_under(root, name):
    p = root.joinpath(*relative(name).parts)
    # lstat catches dangling links too. Reparse points include Windows junctions.
    for q in (root, *root.parents):
        require(not q.is_symlink() and not q.is_junction(), "linked repository root")
    current = root
    for part in relative(name).parts:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "linked/reparse path: " + name)
    require(p.resolve().is_relative_to(root.resolve()), "path outside repository")
    return p


def read(root, name):
    p = path_under(root, name)
    with p.open("rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 8388608, "unsafe file: " + name)
        raw = stream.read(8388609)
        after = os.fstat(stream.fileno())
        require(len(raw) == info.st_size and all(getattr(after, k) == getattr(info, k) for k in
                ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")), "file changed while reading: " + name)
    require(p.stat().st_ino == info.st_ino, "file replaced while reading: " + name)
    return raw


def git(root, *args, input=None):
    # Local plumbing only. Disable replace refs and optional index updates.
    require(not any(n in os.environ for n in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")), "redirected Git environment")
    result = subprocess.run(["git", "--no-replace-objects", *args], cwd=root, input=input,
                            capture_output=True, timeout=30,
                            env=dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1"),
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    require(result.returncode == 0 and not result.stderr and len(result.stdout) <= 16777216, "local Git read failed")
    return result.stdout


def dependency_hashes(root):
    expected = {}
    for stem, digest in FROZEN.items():
        name = "config/experiments/" + stem + "-lock.json"
        raw = read(root, name)
        require(sha(raw) == digest, "frozen lock changed: " + name)
        old = strict(raw)
        entries = {name: digest, **old["source_sha256"], **old.get("immutable_dependency_sha256", {})}
        for source, checksum in entries.items():
            require(source not in expected or expected[source] == checksum, "conflicting frozen source")
            expected[source] = checksum
    return expected


def committed_files(root, revision, hashes):
    names = sorted(hashes)
    raw = git(root, "cat-file", "--batch", input="".join(revision+":"+n+"\n" for n in names).encode())
    cursor, records = 0, {}
    for name in names:
        end = raw.index(b"\n", cursor)
        parts = raw[cursor:end].split()
        require(len(parts) == 3 and parts[1] == b"blob" and parts[2].isdigit(), "committed file missing: " + name)
        size = int(parts[2]); content = raw[end+1:end+1+size]; cursor = end+2+size
        require(raw[cursor-1:cursor] == b"\n" and len(content) == size, "truncated Git object")
        working = read(root, name)
        require(working == content and sha(content) == hashes[name], "uncommitted/changed source: " + name)
        oid = hashlib.sha1(b"blob "+str(size).encode()+b"\0"+content).hexdigest()
        require(parts[0].decode() == oid, "invalid Git blob")
        records[name] = dict(sha256=sha(content), git_blob=oid, size=size)
    require(cursor == len(raw), "extra Git objects")
    staged = git(root, "diff", "--cached", "--name-only", revision, "--", *names)
    require(staged == b"", "staged changes to locked inputs")
    return records


def approval_fields(revision, lock_digest, output):
    # This is a validator schema, not an approval-writing or identity service.
    return dict(contract_id=ID, protocol_id="safetwin5g-reconnect-r5-execution-v1",
                repository_head=revision, admission_lock_sha256=lock_digest, status="approved",
                approved_by="user", type="explicit-single-sandbox-diagnostic", environment="sandbox",
                maximum_attempts=1, output_path=output,
                trials=["r5:control-before", "r5:drop-a", "r5:drop-b", "r5:control-after"],
                containers=["safetwin5g-open5gs", "safetwin5g-gnb", "safetwin5g-ue"],
                image_ids=["sha256:13705fc29922cf019e8c7992b5b04b9c6c584d3848d29689f1d3db64334ae725",
                           "sha256:0c9773889f62ee848144b359349014ea8200c5edab995c303a3d38a75cc70c32"],
                rollback_plan=ROLLBACK, live_actuation=False, operator_validation=False)


class FileAdmission:
    """Fresh file checks plus a permanent cooperative one-attempt reservation.

    No command dispatch, clock/power initialization, cleanup action or network
    permission is supplied. A future separately verified runner must integrate
    recheck() before each normal command without suppressing owned cleanup.
    """
    def __init__(self, root, *, revision, lock_digest, approval_digest, output):
        self.root = Path(os.path.abspath(root))
        for value, length in ((revision, 40), (lock_digest, 64), (approval_digest, 64)):
            require(type(value) is str and re.fullmatch("[0-9a-f]{"+str(length)+"}", value), "exact revision/digest required")
        require(re.fullmatch(r"evidence/engineering/[0-9]{8}T[0-9]{6}Z-reconnect-r5-network", output), "fixed output namespace")
        self.revision, self.lock_digest, self.approval_digest, self.output = revision, lock_digest, approval_digest, output
        self.handle, self.receipt_raw, self.receipt_identity, self.output_identity = None, None, None, None
        self.attempted, self.closed, self.failure = False, False, None

    def _check(self, observed_at):
        root = self.root
        require(not self.closed and self.failure is None, "file admission permanently closed")
        path_under(root, LOCK)
        require(Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve() == root.resolve(), "not exact Git checkout root")
        require(git(root, "rev-parse", "HEAD").decode().strip() == self.revision, "repository HEAD changed")
        lock_raw = read(root, LOCK)
        require(sha(lock_raw) == self.lock_digest, "admission lock digest changed")
        lock = strict(lock_raw)
        require(type(lock) is dict and set(lock) == {"lock_id", "evidence_label", "native_execution_enabled", "network_execution_authorized", "source_sha256"}, "exact lock keys")
        require(lock["lock_id"] == ID and lock["evidence_label"] == "fixture" and lock["native_execution_enabled"] is False
                and lock["network_execution_authorized"] is False, "file-only lock boundary")
        hashes = lock["source_sha256"]
        require(type(hashes) is dict, "source map")
        dependencies = dependency_hashes(root)
        require(set(hashes) == set(dependencies) | set(NEW_SOURCES), "complete source closure")
        for n, h in hashes.items():
            relative(n)
            require(type(h) is str and re.fullmatch("[0-9a-f]{64}", h), "source digest syntax")
        require(all(hashes[n] == h for n, h in dependencies.items()), "frozen source digest changed")
        files = committed_files(root, self.revision, {**hashes, LOCK: self.lock_digest})
        policy = strict(read(root, "config/actions.json"))
        require(policy["allow_live_actuation"] is False and policy["require_human_approval"] is True, "fail-closed policy")
        approval_raw = read(root, APPROVAL)
        require(sha(approval_raw) == self.approval_digest, "approval bytes changed")
        approval = strict(approval_raw)
        expected = approval_fields(self.revision, self.lock_digest, self.output)
        require(type(approval) is dict and set(approval) == set(expected) | {"recorded_at", "expires_at"}, "exact approval keys")
        require(encoded({k: approval[k] for k in expected}) == encoded(expected), "exact approval scope")
        before, expires, now = map(timestamp, (approval["recorded_at"], approval["expires_at"], observed_at))
        require(before <= now < expires and 0 < (expires-before).total_seconds() <= 3600, "approval prior/expiry gate")
        for guard in OLDER_GUARDS:
            require(not path_under(root, guard).exists(), "older runtime guard exists")
        receipt = path_under(root, RECEIPT)
        output = path_under(root, self.output)
        if self.handle is None:
            require(not receipt.exists() and not output.exists(), "prior attempt/receipt exists")
        else:
            require(read(root, RECEIPT) == self.receipt_raw and (receipt.stat().st_dev, receipt.stat().st_ino) == self.receipt_identity,
                    "owned receipt changed")
            require(output.is_dir() and (output.stat().st_dev, output.stat().st_ino) == self.output_identity, "owned output changed")
        engineering = path_under(root, "evidence/engineering")
        attempts = sorted(p.name for p in engineering.iterdir() if p.name.endswith("-reconnect-r5-network"))
        require(attempts == ([output.name] if self.handle is not None else []), "prior R5 attempt exists")
        # Repeat the cheap observations after the complete source scan.
        require(git(root, "rev-parse", "HEAD").decode().strip() == self.revision and read(root, APPROVAL) == approval_raw,
                "authority changed during check")
        return dict(contract_id=ID, file_gate_passed=True, repository_head=self.revision, admission_lock_sha256=self.lock_digest,
                    approval_sha256=self.approval_digest, output_path=self.output, receipt_path=RECEIPT,
                    observed_at=observed_at, sources=files, reserved=self.handle is not None,
                    native_execution_enabled=False, network_execution_authorized=False, human_identity_verified=False,
                    measurement_timing_verified=False, evidence_label="fixture")

    def recheck(self, *, observed_at=None):
        try:
            return self._check(observed_at or datetime.now(timezone.utc).isoformat())
        except BaseException as exc:
            self.failure = self.failure or type(exc).__name__ + ": " + str(exc)
            raise

    def reserve(self, *, observed_at=None):
        require(not self.attempted and not self.closed, "once-only reservation")
        self.attempted = True
        try:
            report = self.recheck(observed_at=observed_at)
            # This file is deliberately NEVER deleted, including partial writes.
            p = path_under(self.root, RECEIPT)
            self.handle = p.open("xb")
            info = os.fstat(self.handle.fileno())
            self.receipt_identity = (info.st_dev, info.st_ino)
            self.receipt_raw = encoded(dict(contract_id=ID, kind="file-reservation", owner_pid=os.getpid(),
                repository_head=self.revision, admission_lock_sha256=self.lock_digest,
                approval_sha256=self.approval_digest, output_path=self.output, observed_at=report["observed_at"],
                network_execution_authorized=False)) + b"\n"
            self.handle.write(self.receipt_raw); self.handle.flush(); os.fsync(self.handle.fileno())
            output = path_under(self.root, self.output)
            output.mkdir(exist_ok=False)
            self.output_identity = (output.stat().st_dev, output.stat().st_ino)
            return self.recheck(observed_at=observed_at)
        except BaseException as exc:
            self.failure = self.failure or type(exc).__name__ + ": " + str(exc)
            self.close()
            raise

    def close(self):
        self.closed = True
        if self.handle is not None:
            self.handle.close()
        # No unlink, truncation, completion flag or rollback claim.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--lock-sha256", required=True)
    parser.add_argument("--approval-sha256", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        report = FileAdmission(Path(__file__).resolve().parents[1], revision=args.revision,
            lock_digest=args.lock_sha256, approval_digest=args.approval_sha256, output=args.output).recheck()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps(dict(file_gate_passed=False, error=type(exc).__name__+": "+str(exc),
                              native_execution_enabled=False, network_execution_authorized=False)))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
