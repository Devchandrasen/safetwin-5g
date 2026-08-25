"""Cross-check provenance links across the complete Phase 7 artifact chain."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.phase7_provenance import audit_chain  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--scalability", type=Path, required=True)
    args = parser.parse_args()
    campaign = args.campaign if args.campaign.is_absolute() else ROOT / args.campaign
    dataset = args.dataset if args.dataset.is_absolute() else ROOT / args.dataset
    analysis = args.analysis if args.analysis.is_absolute() else ROOT / args.analysis
    scalability = args.scalability if args.scalability.is_absolute() else ROOT / args.scalability

    audit_chain(
        campaign=campaign,
        dataset=dataset,
        analysis=analysis,
        scalability=scalability,
        project_root=ROOT,
    )
    print(
        "PASS: campaign -> dataset -> sealed analysis provenance, safety decisions, "
        "and evidence tiers are linked without claim promotion"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
