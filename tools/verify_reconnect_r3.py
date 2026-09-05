"""Capture the R3 source freeze and executable fixtures without an image build."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.reconnect_r3_source import SOURCES, RETAINED, HEADER, source_tree
from tools.diagnose_reconnect_packet import method

CONTEXT = HEADER.parent


def fixture(instrumented):
    base = (ROOT / "tools/packet_diagnosis/fixture.cpp").read_text(encoding="utf-8")
    sap = source_tree()[SOURCES[0]].decode() if instrumented else (RETAINED / "upstream-src-ue-nas-sm-sap.cpp").read_text(encoding="utf-8")
    resource = (RETAINED / "upstream-src-ue-nas-sm-resource.cpp").read_text(encoding="utf-8")
    methods = method(sap, "void NasSm::handleUplinkDataRequest(") + "\n\n" + method(resource, "void NasSm::handleUplinkStatusChange(")
    logger = '''struct Logger {
    std::vector<std::string> traces;
    template<class... Args> void debug(const char *format, Args... args) {
        char line[512]; std::snprintf(line, sizeof(line), format, args...);
        if (std::string(line).find("ST3 ") == 0) traces.emplace_back(line);
    }
};
struct LoggerRef {
    Logger *value;
    LoggerRef(Logger *p): value(p) {}
    Logger *operator->() { return value; }
    Logger *get() { return value; }
};'''
    base = base.replace("struct Logger { template<class... Args> void debug(Args...) {} };", logger)
    base = base.replace("Logger *m_logger;", "LoggerRef m_logger;")
    base = base.replace("// UPSTREAM_METHODS", methods)
    extra = '''
        {
            World w;
            std::string packet(84, '\\0');
            packet[0] = 0x45; packet[3] = 84; packet[9] = 1;
            const unsigned char flow[] = {10,45,0,2,10,45,0,1};
            for (int i = 0; i < 8; ++i) packet[12+i] = static_cast<char>(flow[i]);
            packet[20] = 8; packet[24] = 0x27; packet[25] = 0x11; packet[27] = 1;
            w.input(packet);
            check(w.sink.packets.empty() && w.mm.requests == 1, "valid idle packet still not forwarded");
            w.mm.m_cmState = ECmState::CM_CONNECTED; packet[27] = 2; w.input(packet);
            check(w.sink.packets == std::vector<std::pair<int, std::string>>{{1, packet}}, "only valid connected packet forwarded");
            check(w.logger.traces.size() == TRACE_COUNT, "instrumented trace count");
            if (TRACE_COUNT) {
                check(w.logger.traces[0].find("stage=nas_in") != std::string::npos, "ingress trace");
                check(w.logger.traces[1].find("stage=nas_idle") != std::string::npos, "idle trace");
                check(w.logger.traces[3].find("stage=nas_forward") != std::string::npos, "forward trace");
                for (const auto &line : w.logger.traces) std::cout << line << '\\n';
            }
            ++cases;
        }
'''.replace("TRACE_COUNT", "4" if instrumented else "0")
    base = base.replace('        std::cout << "FIXTURE_CASES="', extra + '        std::cout << "FIXTURE_CASES="')
    base = base.replace("return cases == 60 ? 0 : 43;", "return cases == 61 ? 0 : 43;")
    return ("#include <cstdio>\n" + HEADER.read_text(encoding="utf-8") + "\n" + base).encode()


def main():
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r3-freeze")
    output.mkdir(parents=True, exist_ok=False)
    def save(name, data): (output / name).write_bytes((json.dumps(data, indent=2) + "\n").encode())
    checks, errors = [], []
    def command(name, argv, stdin=None, accepted=(0,)):
        row = {"name": name, "argv": argv, "started_at": datetime.now(timezone.utc).isoformat(), "stdin_sha256": hashlib.sha256(stdin).hexdigest() if stdin else None}
        try:
            result = subprocess.run(argv, cwd=ROOT, input=stdin, capture_output=True, timeout=55)
            row.update(returncode=result.returncode, stdout=result.stdout.decode("utf-8"), stderr=result.stderr.decode("utf-8"))
        except subprocess.TimeoutExpired as exc:
            row.update(returncode=-999, stdout=(exc.stdout or b"").decode("utf-8", "replace"), stderr="bounded timeout")
        row["completed_at"] = datetime.now(timezone.utc).isoformat()
        checks.append(row); save("commands.json", checks)
        if row["returncode"] not in accepted: raise RuntimeError(name + ": exit " + str(row["returncode"]))
        return row["stdout"]
    try:
        sources = ["tools/reconnect_r3_source.py", "tools/reconnect_r3_trace.py", "tools/verify_reconnect_r3.py", "tests/test_reconnect_r3.py",
                   "config/experiments/reconnect-r3-trace.json", "docs/RECONNECT_R3_TRACE_PROTOCOL.md"]
        sources += [p.relative_to(ROOT).as_posix() for p in CONTEXT.iterdir() if p.is_file()]
        save("source-hashes.json", {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources})
        command("repository-head", ["git", "rev-parse", "HEAD"])
        command("source-provenance", [sys.executable, "tools/audit_reconnect_packet.py", "--run", RETAINED.relative_to(ROOT).as_posix()])
        config = json.loads((ROOT / "config/experiments/reconnect-r3-trace.json").read_text())
        command("official-before", ["docker", "inspect", "safetwin5g-gnb", "safetwin5g-ue"])
        command("base-image", ["docker", "image", "inspect", config["base_image_id"]])
        command("new-tag-absence", ["docker", "image", "ls", "--no-trunc", "--format", "{{.ID}}", config["future_image_tag"]])
        command("ping-help", ["docker", "exec", "safetwin5g-ue", "timeout", "15", "ping", "-h"], accepted=(0,2))
        tree, hashes, patch = source_tree(), {}, []
        for path, content in tree.items():
            name = "overlay-" + path.replace("/", "-")
            (output / name).write_bytes(content)
            hashes[path] = hashlib.sha256(content).hexdigest()
            old = (RETAINED / ("upstream-" + path.replace("/", "-"))).read_text(encoding="utf-8") if path in SOURCES else ""
            patch.extend(difflib.unified_diff(old.splitlines(True), content.decode().splitlines(True), fromfile="a/" + path if old else "/dev/null", tofile="b/" + path))
        (output / "instrumentation.diff").write_bytes("".join(patch).encode())
        save("overlay-hashes.json", hashes)
        compiler = ["docker", "run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                    "--cpus=1", "--memory=256m", "--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=32m", "-i", config["base_image_id"],
                    "timeout", "25", "sh", "-lc", "g++ -std=c++17 -Wall -Wextra -pedantic -x c++ - -o /tmp/r3-fixture && /tmp/r3-fixture"]
        parser = (CONTEXT / "parser_fixture.cpp").read_text().replace("// TRACE_HEADER", HEADER.read_text()).encode()
        for name, data in (("parser-fixture", parser), ("baseline-nas-fixture", fixture(False)), ("instrumented-nas-fixture", fixture(True))):
            (output / (name + ".cpp")).write_bytes(data)
            command(name, compiler, data)
        command("full-tests", [sys.executable, "-m", "pytest", "-q"])
        command("statistical-lock", [sys.executable, "-c", "from tools.run_phase7_analysis import verify_analysis_lock; print(verify_analysis_lock()['lock_id'])"])
        command("official-after", ["docker", "inspect", "safetwin5g-gnb", "safetwin5g-ue"])
    except Exception as exc: errors.append(type(exc).__name__ + ": " + str(exc))
    save("summary.json", {"capture_completed": not errors, "errors": errors, "evidence_label": "fixture", "new_image_built": False,
                          "sandbox_image_applied": False, "network_trials": 0, "network_fix_validated": False, "TNSM_ready": False})
    save("manifest.json", {"captured_file_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}})
    print(output)
    print(json.dumps({"capture_completed": not errors, "errors": errors}))
    return 0 if not errors else 2


if __name__ == "__main__": raise SystemExit(main())
