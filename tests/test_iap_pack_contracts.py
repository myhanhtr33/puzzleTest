from __future__ import annotations

from pathlib import Path

import pytest

from utils.purchase_flow import run_pack_purchase_flow
from utils.ui_contracts import load_manifest, parse_drawio_xml


PROJECT_ROOT = Path(__file__).parents[1]
LOCATOR_DIR = PROJECT_ROOT / "locator generator"


def _discover_purchase_manifests() -> list[Path]:
    manifests = []
    for path in sorted(LOCATOR_DIR.glob("IAP_*.json")):
        manifest = load_manifest(path)
        if any(
            item.get("contractType") == "button" and item.get("buttonType") == "buy"
            for item in manifest.get("objects", [])
        ):
            manifests.append(path)
    return manifests


@pytest.mark.parametrize(
    "manifest_path",
    _discover_purchase_manifests(),
    ids=lambda path: path.stem,
)
def test_iap_pack_manifest_matches_drawio(manifest_path):
    drawio_path = manifest_path.with_suffix(".drawio")
    if not drawio_path.is_file():
        pytest.skip(f"No matching draw.io source for {manifest_path.name}")

    generated_manifest = parse_drawio_xml(
        drawio_path.read_bytes(), name=manifest_path.stem
    )
    assert generated_manifest == load_manifest(manifest_path)


@pytest.mark.real_device
@pytest.mark.iap_pack_purchase
@pytest.mark.parametrize(
    "manifest_path",
    _discover_purchase_manifests(),
    ids=lambda path: path.stem,
)
def test_iap_pack_purchase_flow(poco, dev, manifest_path):
    report = run_pack_purchase_flow(poco, load_manifest(manifest_path))
    assert report.passed, f"device={dev}\n{report.format()}"
