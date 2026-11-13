from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from tests.ui_fakes.purchase_flow import fake_purchase_flow_poco
from utils.purchase_flow import run_pack_purchase_flow
from utils.reward_registry import StorageCheck, compare_storage_snapshots
from utils.ui_contract_reporting import (
    ContractReportCollector,
    activate_collector,
    build_pytest_html_extras,
    deactivate_collector,
    record_purchase_flow_report,
)
from utils.ui_contracts import load_manifest


PROJECT_ROOT = Path(__file__).parents[1]
MANIFEST_PATH = PROJECT_ROOT / "locator generator" / "BusRush" / "IAP_SmallBundle.json"


def test_purchase_storage_html_includes_snapshots_and_expected_check():
    report = SimpleNamespace(
        storage_before={"items": {"gold": {"kind": "quantity", "value": 10}}},
        storage_after={"items": {"gold": {"kind": "quantity", "value": 15}}},
        storage_checks=[StorageCheck("gold", True, "expected gold=15, got 15 (grant=5)")],
    )
    collector = ContractReportCollector()
    token = activate_collector(collector)
    try:
        record_purchase_flow_report(report, "SmallBundle")
        rendered = build_pytest_html_extras(collector)[0]["content"]
    finally:
        deactivate_collector(token)

    assert "Before (S0)" in rendered
    assert "&quot;value&quot;: 10" in rendered
    assert "&quot;value&quot;: 15" in rendered
    assert "expected gold=15, got 15 (grant=5)" in rendered


def test_iap_pack_flow_compares_complete_inventory_s0_to_s2():
    manifest = load_manifest(MANIFEST_PATH)
    poco, invoke = fake_purchase_flow_poco()
    poco.invoke_handler = invoke

    report = run_pack_purchase_flow(
        poco,
        manifest,
        poll_interval=0,
        checkers={"texture_image_match": lambda *_: None},
    )

    assert report.passed, report.format()
    assert {check.item_id for check in report.storage_checks} == {
        "gold",
        "booster_sort",
        "booster_shuffle",
        "booster_vip",
        "booster_slot",
        "live_amount",
        "unlimited_live",
    }
    assert poco("UIPack_SmallBundle").offspring("Button").click_count == 1
    assert report.storage_before["items"]["live_amount"]["value"] == 20
    assert report.storage_after["items"]["live_amount"]["value"] == 20


def test_ungranted_inventory_allows_regen_recorded_between_stamina_timestamps():
    s0_ticks = 638_964_000_000_000_000
    s2_ticks = s0_ticks + 61 * 10_000_000
    items = {
        "gold": {"kind": "quantity", "value": 400},
        "booster_sort": {"kind": "quantity", "value": 2},
        "booster_shuffle": {"kind": "quantity", "value": 3},
        "booster_vip": {"kind": "quantity", "value": 1},
        "booster_slot": {"kind": "quantity", "value": 0},
        "live_amount": {
            "kind": "stamina",
            "value": 2,
            "max": 10,
            "regenAmount": 1,
            "regenIntervalSeconds": 60,
            "lastDecreaseFromMaxTicks": s0_ticks,
        },
        "unlimited_live": {"kind": "expiry", "endTimeTicks": s0_ticks - 1},
    }

    checks = compare_storage_snapshots(
        {"capturedUtcTicks": s0_ticks, "items": items},
        {
            "capturedUtcTicks": s2_ticks,
            "items": {
                **items,
                "live_amount": {
                    **items["live_amount"],
                    "value": 3,
                    "lastDecreaseFromMaxTicks": s0_ticks + 60 * 10_000_000,
                },
            },
        },
        grants=[],
    )

    assert all(check.passed for check in checks), checks


def test_stamina_grant_and_natural_regen_near_same_time_are_both_counted():
    start_ticks = 638_964_000_000_000_000
    regen_interval_ticks = 60 * 10_000_000
    before_items = {
        item_id: {"kind": "quantity", "value": 0}
        for item_id in (
            "gold",
            "booster_sort",
            "booster_shuffle",
            "booster_vip",
            "booster_slot",
        )
    }
    before_items["live_amount"] = {
        "kind": "stamina",
        "value": 2,
        "max": 10,
        "regenAmount": 1,
        "regenIntervalSeconds": 60,
        "lastDecreaseFromMaxTicks": start_ticks,
    }
    before_items["unlimited_live"] = {"kind": "expiry", "endTimeTicks": start_ticks}
    after_items = {
        **before_items,
        "live_amount": {
            **before_items["live_amount"],
            "value": 4,
            "lastDecreaseFromMaxTicks": start_ticks + regen_interval_ticks,
        },
    }

    checks = compare_storage_snapshots(
        {"capturedUtcTicks": start_ticks, "items": before_items},
        {"capturedUtcTicks": start_ticks + regen_interval_ticks + 1, "items": after_items},
        grants=[{"rewardId": "live_amount", "amount": 1}],
        grant_time_ticks=start_ticks + regen_interval_ticks - 1,
    )

    stamina_check = next(check for check in checks if check.item_id == "live_amount")
    assert stamina_check.passed, stamina_check.message
