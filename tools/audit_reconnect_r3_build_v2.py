"""Versioned audit amendment: Docker mount order is not a mount mutation.

The captured v1 auditor stays byte-identical. Load it into a private module
namespace and change only the service-comparison input normalization. Every
mount field remains compared; duplicate destinations remain an error.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def canonical_services(rows):
    result = copy.deepcopy(rows)
    for row in result:
        mounts = row["Mounts"]
        destinations = [m["Destination"] for m in mounts]
        if any(not isinstance(d, str) or not d.startswith("/") for d in destinations) or len(set(destinations)) != len(destinations):
            raise ValueError("ambiguous mount destination")
        row["Mounts"] = sorted(mounts, key=lambda m: m["Destination"])
    return result


def audit(run):
    specification = importlib.util.spec_from_file_location("r3_build_v1_frozen", ROOT / "tools/audit_reconnect_r3_build.py")
    original = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(original)
    compare = original.preserve_services
    original.preserve_services = lambda before, after: compare(canonical_services(before), canonical_services(after))
    result = original.audit(run)
    result["auditor_revision"] = "r3-build-v2-mount-order-only"
    result["v1_auditor_and_raw_artifacts_unchanged"] = True
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--run", required=True)
    print(json.dumps(audit(parser.parse_args().run), indent=2))
