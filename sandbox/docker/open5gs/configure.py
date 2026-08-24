"""Apply the minimal deterministic sandbox overrides to upstream configs."""

from pathlib import Path


CONFIG = Path("/opt/open5gs/etc/open5gs")


def replace_once(filename: str, old: str, new: str) -> None:
    path = CONFIG / filename
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match in {filename}, found {count}: {old!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


for database_config in ("pcf.yaml", "udr.yaml"):
    replace_once(
        database_config,
        "db_uri: mongodb://localhost/open5gs",
        "db_uri: mongodb://mongodb/open5gs",
    )

for direct_nrf_config in (
    "udr.yaml",
    "udm.yaml",
    "ausf.yaml",
    "pcf.yaml",
    "nssf.yaml",
    "bsf.yaml",
    "smf.yaml",
    "amf.yaml",
):
    replace_once(
        direct_nrf_config,
        "    client:\n"
        "#      nrf:\n"
        "#        - uri: http://127.0.0.10:7777\n"
        "      scp:\n"
        "        - uri: http://127.0.0.200:7777",
        "    client:\n"
        "      nrf:\n"
        "        - uri: http://127.0.0.10:7777",
    )

replace_once(
    "amf.yaml",
    "  ngap:\n    server:\n      - address: 127.0.0.5",
    "  ngap:\n    server:\n      - address: 10.53.0.3",
)
replace_once(
    "amf.yaml",
    "  metrics:\n    server:\n      - address: 127.0.0.5\n        port: 9090",
    "  metrics:\n    server:\n      - address: 10.53.0.3\n        port: 9090",
)
replace_once(
    "smf.yaml",
    "  metrics:\n    server:\n      - address: 127.0.0.4\n        port: 9090",
    "  metrics:\n    server:\n      - address: 10.53.0.3\n        port: 9091",
)
replace_once(
    "upf.yaml",
    "  gtpu:\n    server:\n      - address: 127.0.0.7",
    "  gtpu:\n    server:\n      - address: 10.53.0.3",
)
replace_once(
    "upf.yaml",
    "  metrics:\n    server:\n      - address: 127.0.0.7\n        port: 9090",
    "  metrics:\n    server:\n      - address: 10.53.0.3\n        port: 9092",
)
