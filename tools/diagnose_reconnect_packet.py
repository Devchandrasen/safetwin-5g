"""Read pinned source and replay an exact-method fixture, never alter services."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "config/experiments/reconnect-r2-images.json"
RUN = ROOT / "evidence/engineering/20260905T082014Z-reconnect-r2"
TEMPLATE = ROOT / "tools/packet_diagnosis/fixture.cpp"
PATHS = ("src/ue/app/task.cpp", "src/ue/nas/task.cpp", "src/ue/nas/sm/sap.cpp",
         "src/ue/nas/sm/resource.cpp", "src/ue/nas/sm/sm.hpp", "src/ue/nas/mm/proc.cpp",
         "src/ue/nas/mm/service.cpp", "src/ue/rls/task.cpp", "src/ue/rls/ctl_task.cpp",
         "src/gnb/gtp/task.cpp", "src/gnb/ngap/context.cpp", "LICENSE")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def method(source, signature):
    """Extract balanced braces; these two locked methods have no brace literals."""
    if source.count(signature) != 1:
        raise ValueError("non-unique method signature")
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for i in range(opening, len(source)):
        depth += (source[i] == "{") - (source[i] == "}")
        if depth == 0:
            return source[start:i + 1]
    raise ValueError("unclosed method")


def main():
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-packet-diagnosis")
    output.mkdir(parents=True, exist_ok=False)
    def save(name, data):
        (output / name).write_bytes((json.dumps(data, indent=2) + "\n").encode())
    lock = json.loads(LOCK.read_text())
    image, commit = lock["derived_image_id"], lock["upstream_commit"]
    records, sources, errors = [], [], []
    def command(name, argv, stdin=None, accepted=(0,)):
        row = {"name": name, "argv": argv, "started_at": datetime.now(timezone.utc).isoformat(),
               "stdin_sha256": digest(stdin) if stdin is not None else None}
        try:
            result = subprocess.run(argv, cwd=ROOT, input=stdin, capture_output=True, timeout=35)
            row.update(returncode=result.returncode, stdout=result.stdout.decode("utf-8"), stderr=result.stderr.decode("utf-8"))
        except subprocess.TimeoutExpired as exc:
            row.update(returncode=-999, stdout=(exc.stdout or b"").decode("utf-8", "replace"), stderr="bounded command timeout")
        row["completed_at"] = datetime.now(timezone.utc).isoformat()
        records.append(row)
        save("commands.json", records)
        if row["returncode"] not in accepted:
            raise RuntimeError(name + ": exit " + str(row["returncode"]))
        return row["stdout"]
    isolated = ["docker", "run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL",
                "--security-opt=no-new-privileges", "--cpus=1", "--memory=256m"]
    try:
        save("collector-sources.json", {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in (Path(__file__), TEMPLATE, LOCK)})
        save("r2-manifest.json", {"path": RUN.relative_to(ROOT).as_posix(), "sha256": digest((RUN / "manifest.json").read_bytes())})
        command("repository-head", ["git", "rev-parse", "HEAD"])
        command("gnb-before", ["docker", "inspect", "safetwin5g-gnb"])
        command("ue-before", ["docker", "inspect", "safetwin5g-ue"])
        command("derived-image", ["docker", "image", "inspect", image])
        command("retained-commit", isolated + [image, "timeout", "15", "git", "-C", "/usr/src/UERANSIM", "rev-parse", "HEAD"])
        command("retained-diff", isolated + [image, "timeout", "15", "git", "-C", "/usr/src/UERANSIM", "diff", "--name-only"])
        command("ue-binary", ["docker", "exec", "safetwin5g-ue", "timeout", "15", "sha256sum", "/opt/ueransim/bin/nr-ue"])
        for path in PATHS:
            local = "upstream-" + path.replace("/", "-")
            content = command("source:" + path, isolated + [image, "timeout", "15", "git", "-C", "/usr/src/UERANSIM", "show", "HEAD:" + path]).encode()
            (output / local).write_bytes(content)
            url = f"https://raw.githubusercontent.com/aligungr/UERANSIM/{commit}/{path}"
            external = urllib.request.urlopen(url, timeout=20).read()
            (output / ("official-" + local)).write_bytes(external)
            sources.append({"path": path, "local": local, "url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                            "image_sha256": digest(content), "official_sha256": digest(external), "byte_identical": content == external})
            save("sources.json", sources)
            if content != external:
                raise RuntimeError("official source mismatch: " + path)
        sap = (output / "upstream-src-ue-nas-sm-sap.cpp").read_text(encoding="utf-8")
        resource = (output / "upstream-src-ue-nas-sm-resource.cpp").read_text(encoding="utf-8")
        methods = method(sap, "void NasSm::handleUplinkDataRequest(") + "\n\n" + method(resource, "void NasSm::handleUplinkStatusChange(")
        (output / "exact-methods.cpp").write_bytes(methods.encode())
        template = TEMPLATE.read_text(encoding="utf-8")
        if template.count("// UPSTREAM_METHODS") != 1:
            raise ValueError("fixture insertion marker")
        fixture = template.replace("// UPSTREAM_METHODS", methods).encode()
        (output / "executed-fixture.cpp").write_bytes(fixture)
        compile_command = isolated + ["--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=32m", "-i", image, "timeout", "25", "sh", "-lc",
            "g++ -std=c++17 -Wall -Wextra -pedantic -x c++ - -o /tmp/packet-fixture && /tmp/packet-fixture"]
        command("compiler", isolated + [image, "timeout", "15", "g++", "--version"])
        command("exact-method-fixture", compile_command, fixture)
        # A deliberately wrong test-of-test fixture, never a proposed source patch.
        marker = b"if (m_mm->m_cmState == ECmState::CM_CONNECTED)"
        if fixture.count(marker) != 1:
            raise ValueError("mutation marker")
        mutant = fixture.replace(marker, b"if (true)")
        (output / "negative-control-fixture.cpp").write_bytes(mutant)
        command("negative-control-fixture", compile_command, mutant, accepted=(42,))
        command("gnb-after", ["docker", "inspect", "safetwin5g-gnb"])
        command("ue-after", ["docker", "inspect", "safetwin5g-ue"])
    except Exception as exc:
        errors.append(type(exc).__name__ + ": " + str(exc))
    save("summary.json", {"capture_completed": not errors, "errors": errors, "evidence_label": "fixture",
        "source_mechanism": "idle active-session method flags pending data without retaining or forwarding payload",
        "r2_loss_location_uniquely_observed": False, "network_fix_applied": False, "new_network_trials": 0,
        "network_fix_validated": False, "long_campaign_ready": False, "TNSM_ready": False,
        "live_actuation": False, "hardware_measured": False, "operator_validated": False})
    save("manifest.json", {"captured_file_sha256": {p.name: digest(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    print(output)
    print(json.dumps({"capture_completed": not errors, "errors": errors}))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
