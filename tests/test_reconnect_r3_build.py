import copy
import io
import json
import tarfile

import pytest

from tools.audit_reconnect_r3_build import OFFICIAL, preserve_services, source_delta, sums
from tools.build_reconnect_r3 import BUILD, FREEZE, context_files, context_tar


def services():
    return [{"Name": "/safetwin5g-" + name, "Id": name, "Image": OFFICIAL, "RestartCount": 0,
             "Config": {}, "HostConfig": {}, "Mounts": [],
             "State": {"StartedAt": "fixed", "FinishedAt": "never", "Running": True, "Paused": False, "Restarting": False}}
            for name in ("ue", "gnb")]


def test_build_context_is_deterministic_and_frozen():
    files = context_files()
    raw = context_tar(files)
    assert raw == context_tar(files)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        assert [m.name for m in archive] == list(files)
        assert all(m.isfile() and m.mtime == 0 and m.uid == 0 for m in archive.getmembers())
    assert files["instrumentation.diff"] == (FREEZE / "instrumentation.diff").read_bytes()
    assert sums(files["expected-source.sha256"]) == json.loads((FREEZE / "overlay-hashes.json").read_text())


def test_build_recipe_has_no_download_or_service_mutation():
    recipe = (BUILD / "Dockerfile").read_text()
    script = (BUILD / "build.sh").read_text()
    assert recipe.startswith("# Local R2") and "FROM safetwin5g/ueransim:3.3.0-reconnect-r2" in recipe
    for forbidden in ("apt-get", "curl ", "wget ", "git clone", "docker ", "rm -"):
        assert forbidden not in script
    assert "timeout -k 10 600 cmake --build cmake-build-release --parallel 2" in script
    assert "git -c core.autocrlf=false apply --check" in script
    assert "cp cmake-build-release/nr-ue /opt/ueransim/bin/nr-ue" in script


def test_source_delta_requires_exact_overlay_only():
    before = {"a": "old", "b": "same"}
    after = {"a": "new", "b": "same", "src/utils/safetwin_trace_r3.hpp": "header"}
    overlay = {"a": "new", "src/utils/safetwin_trace_r3.hpp": "header"}
    source_delta(before, after, overlay)
    after["b"] = "unexpected"
    with pytest.raises(ValueError, match="source delta"): source_delta(before, after, overlay)


def test_source_delta_rejects_missing_and_extra_files():
    with pytest.raises(ValueError, match="inventory"): source_delta({"a": "1"}, {}, {})
    with pytest.raises(ValueError, match="inventory"): source_delta({}, {"extra": "1"}, {})


@pytest.mark.parametrize("key,value", [("Id", "new"), ("Image", "new"), ("RestartCount", 1), ("Config", {"new": 1}),
                                      ("HostConfig", {"Privileged": True}), ("Mounts", ["host"])])
def test_running_service_mutation_rejected(key, value):
    before = services(); after = copy.deepcopy(before); after[0][key] = value
    with pytest.raises(ValueError, match="container changed"): preserve_services(before, after)


@pytest.mark.parametrize("key,value", [("StartedAt", "new"), ("FinishedAt", "now"), ("Running", False), ("Paused", True), ("Restarting", True)])
def test_running_state_mutation_rejected(key, value):
    before = services(); after = copy.deepcopy(before); after[0]["State"][key] = value
    with pytest.raises(ValueError, match="state changed"): preserve_services(before, after)


def test_unchanged_services_pass_and_missing_service_fails():
    preserve_services(services(), services())
    with pytest.raises(ValueError, match="inventory"): preserve_services(services(), services()[:1])


def test_checksum_duplicate_and_malformed_rejected():
    row = "a" * 64 + "  file\n"
    assert sums(row.encode()) == {"file": "a" * 64}
    with pytest.raises(ValueError, match="duplicate"): sums((row + row).encode())
    with pytest.raises(ValueError, match="malformed"): sums(b"success file\n")
