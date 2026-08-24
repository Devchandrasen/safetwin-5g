"""Adapters from raw sandbox evidence into lossless, timestamped telemetry rows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from math import isfinite
from pathlib import Path
import re
from typing import Iterable


PROMETHEUS_SAMPLE = re.compile(
    r"^(?P<metric>[a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?:\{(?P<labels>.*)\})?\s+"
    r"(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"(?:\s+\d+)?$"
)
LABEL = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:\\.|[^"\\])*)"')
PING_SUMMARY = re.compile(
    r"(?P<sent>\d+) packets transmitted, (?P<received>\d+) received, "
    r"(?P<loss>[\d.]+)% packet loss"
)
PING_RTT = re.compile(
    r"rtt min/avg/max/mdev = "
    r"(?P<min>[\d.]+)/(?P<avg>[\d.]+)/(?P<max>[\d.]+)/(?P<mdev>[\d.]+) ms"
)


@dataclass(frozen=True)
class TelemetryRow:
    scenario_id: str
    stage: str
    observed_at: str
    source: str
    metric: str
    labels: dict[str, str]
    value: float
    unit: str
    evidence_label: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def parse_prometheus(text: str) -> list[tuple[str, dict[str, str], float]]:
    samples: list[tuple[str, dict[str, str], float]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = PROMETHEUS_SAMPLE.fullmatch(line)
        if not match:
            continue
        value = float(match.group("value"))
        if not isfinite(value):
            continue
        labels = {
            item.group(1): bytes(item.group(2), "utf-8").decode("unicode_escape")
            for item in LABEL.finditer(match.group("labels") or "")
        }
        samples.append((match.group("metric"), labels, value))
    return samples


def parse_ping(text: str) -> dict[str, tuple[float, str]]:
    summary = PING_SUMMARY.search(text)
    if not summary:
        raise ValueError("ping output lacks packet summary")
    metrics: dict[str, tuple[float, str]] = {
        "packets_transmitted": (float(summary.group("sent")), "packets"),
        "packets_received": (float(summary.group("received")), "packets"),
        "packet_loss_pct": (float(summary.group("loss")), "percent"),
    }
    rtt = PING_RTT.search(text)
    if rtt:
        for name in ("min", "avg", "max", "mdev"):
            metrics[f"rtt_{name}_ms"] = (float(rtt.group(name)), "milliseconds")
    return metrics


class EvidenceTelemetryAdapter:
    """Read the immutable files of one intervention bundle into long-form rows."""

    STAGES = ("baseline", "fault", "post-action", "rollback", "final")
    JOBS = ("amf", "smf", "upf")

    def __init__(self, bundle: Path):
        self.bundle = bundle.resolve()

    def rows(self) -> list[TelemetryRow]:
        manifest = json.loads(
            (self.bundle / "manifest.json").read_text(encoding="utf-8")
        )
        record = json.loads(
            (self.bundle / "intervention-record.json").read_text(encoding="utf-8")
        )
        command_times = self._command_times()
        evidence_label = manifest["evidence_label"]
        scenario_id = record["scenario_id"]
        rows: list[TelemetryRow] = []
        for stage in self.STAGES:
            ping_path = self.bundle / "ping" / f"{stage}.txt"
            ping_time = command_times[str(ping_path.relative_to(self.bundle)).replace("\\", "/")]
            for metric, (value, unit) in parse_ping(
                ping_path.read_text(encoding="utf-8")
            ).items():
                rows.append(
                    TelemetryRow(
                        scenario_id,
                        stage,
                        ping_time,
                        "ueransim-user-plane",
                        metric,
                        {},
                        value,
                        unit,
                        evidence_label,
                    )
                )
            for job in self.JOBS:
                relative = f"telemetry/{stage}-{job}-metrics.txt"
                observed_at = command_times[relative]
                text = (self.bundle / relative).read_text(encoding="utf-8")
                for metric, labels, value in parse_prometheus(text):
                    rows.append(
                        TelemetryRow(
                            scenario_id,
                            stage,
                            observed_at,
                            f"open5gs-{job}",
                            metric,
                            labels,
                            value,
                            "native",
                            evidence_label,
                        )
                    )
        return rows

    def _command_times(self) -> dict[str, str]:
        commands = (
            json.loads(line)
            for line in (self.bundle / "commands.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
        return {command["output_file"]: command["completed_at"] for command in commands}

    @staticmethod
    def write_jsonl(rows: Iterable[TelemetryRow], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row.to_dict(), sort_keys=True, separators=(",", ":")))
                handle.write("\n")
