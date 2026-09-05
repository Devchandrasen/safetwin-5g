import hashlib
import json
from pathlib import Path

import pytest

from tools.audit_phase7_resume import audit


def make_checkpoint(tmp_path: Path):
    checkpoint = tmp_path / "checkpoint"
    run = tmp_path / "run"
    checkpoint.mkdir()
    (run / "units").mkdir(parents=True)
    originals = {
        "units/saved.json": b'{"cleanup_verified":true}\r\n',
        "commands.jsonl": b'{"sequence":1}\r\n',
        "environment.json": b'{"session":"before"}\n',
    }
    for name, content in originals.items():
        (run / name).write_bytes(content)
        if name != "units/saved.json":
            (checkpoint / ("before-resume-" + name)).write_bytes(content)
    saved = {
        "saved_unit_count": 1,
        "source_files": {
            name: {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
            for name, content in originals.items()
        },
    }
    (checkpoint / "checkpoint.json").write_text(json.dumps(saved), encoding="utf-8")
    manifest = {"captured_file_sha256": {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in checkpoint.iterdir()
    }}
    (checkpoint / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return checkpoint, run


def test_resume_allows_append_and_new_environment_but_preserves_original(tmp_path):
    checkpoint, run = make_checkpoint(tmp_path)
    with (run / "commands.jsonl").open("ab") as stream:
        stream.write(b'{"sequence":1,"session":"after"}\n')
    (run / "environment.json").write_text('{"session":"after"}')
    result = audit(checkpoint, run)
    assert result["passed"] and result["saved_units_preserved"] == 1
    assert result["campaign_acceptance_evaluated"] is False


@pytest.mark.parametrize("mutation", ["truncate", "rewrite", "unit", "original-environment"])
def test_resume_rejects_loss_or_rewrite_of_prior_evidence(tmp_path, mutation):
    checkpoint, run = make_checkpoint(tmp_path)
    if mutation == "truncate":
        (run / "commands.jsonl").write_bytes(b"{}")
    elif mutation == "rewrite":
        (run / "commands.jsonl").write_bytes(b'{"sequence":9}\r\n')
    elif mutation == "unit":
        (run / "units" / "saved.json").write_bytes(b"{}\n")
    else:
        (checkpoint / "before-resume-environment.json").write_bytes(b"{}\n")
    with pytest.raises(ValueError):
        audit(checkpoint, run)
