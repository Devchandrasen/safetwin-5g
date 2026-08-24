"""CLI wrapper for freezing an intervention dataset release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.dataset import build_release  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_bundle", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = build_release(args.source_bundle, args.output)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
