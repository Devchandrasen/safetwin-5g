"""Preserve exact pre-freeze source revisions behind the read-only preflights."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIX = ROOT / "evidence/engineering"


def main():
    output = PREFIX / "20260905T122339Z-reconnect-r3-preflight-source-archive"
    output.mkdir(exist_ok=False)
    names = ["20260905T122202Z-reconnect-r3-preflight", "20260905T122302Z-reconnect-r3-preflight", "20260905T122339Z-reconnect-r3-preflight"]
    captured = {}
    for index, name in enumerate(names):
        hashes = json.loads((PREFIX / name / "source-hashes.json").read_bytes())
        for path, digest in hashes.items():
            data = (ROOT / path).read_bytes()
            if path == "sandbox/run_reconnect_r3.py" and index < 2:
                data = data.replace(b'caps = {"CAP_NET_ADMIN", "CAP_NET_RAW"}', b'caps = {"NET_ADMIN", "NET_RAW"}')
            if path == "sandbox/reconnect_r3_measurement.py" and index == 0:
                data = data.replace(b'''object_format({key: '(index .HostConfig "' + key + '")' for key in HOST_FIELDS})''',
                                    b'''object_format({key: ".HostConfig." + key for key in HOST_FIELDS})''')
            if hashlib.sha256(data).hexdigest() != digest: raise RuntimeError("preflight source reconstruction mismatch: " + path)
            filename = f"preflight-{index + 1}-" + path.replace("/", "-")
            (output / filename).write_bytes(data)
            captured[filename] = {"preflight": name, "source": path, "sha256": digest}
    (output / "reconstruction.json").write_text(json.dumps(captured, indent=2) + "\n")
    manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
    (output / "manifest.json").write_text(json.dumps({"captured_file_sha256": manifest}, indent=2) + "\n")
    print(output)


if __name__ == "__main__": main()
