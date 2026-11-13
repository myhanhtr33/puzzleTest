from __future__ import annotations

from tests.ui_fakes.small_bundle import fake_small_bundle_poco


TICKS_PER_SECOND = 10_000_000
BASE_TICKS = 638_964_000_000_000_000
GRANT_TICKS = BASE_TICKS + 5 * TICKS_PER_SECOND


def _snapshot(captured_ticks: int, values: dict[str, dict]) -> dict:
    return {
        "status": "success",
        "schemaVersion": 1,
        "capturedUtcTicks": captured_ticks,
        "items": values,
    }


def fake_purchase_flow_poco():
    s0_items = {
        "gold": {"kind": "quantity", "value": 1000},
        "booster_sort": {"kind": "quantity", "value": 2},
        "booster_shuffle": {"kind": "quantity", "value": 4},
        "booster_vip": {"kind": "quantity", "value": 1},
        "booster_slot": {"kind": "quantity", "value": 0},
        "live_amount": {
            "kind": "stamina",
            "value": 20,
            "max": 20,
            "regenAmount": 1,
            "regenIntervalSeconds": 900,
            "lastDecreaseFromMaxTicks": -1,
        },
        "unlimited_live": {
            "kind": "expiry",
            "endTimeTicks": BASE_TICKS - 3600 * TICKS_PER_SECOND,
        },
    }
    s2_items = {
        "gold": {"kind": "quantity", "value": 6000},
        "booster_sort": {"kind": "quantity", "value": 3},
        "booster_shuffle": {"kind": "quantity", "value": 5},
        "booster_vip": {"kind": "quantity", "value": 2},
        "booster_slot": {"kind": "quantity", "value": 1},
        "live_amount": {
            "kind": "stamina",
            "value": 20,
            "max": 20,
            "regenAmount": 1,
            "regenIntervalSeconds": 900,
            "lastDecreaseFromMaxTicks": -1,
        },
        "unlimited_live": {
            "kind": "expiry",
            "endTimeTicks": GRANT_TICKS + 3600 * TICKS_PER_SECOND,
        },
    }
    snapshots = [
        _snapshot(BASE_TICKS, s0_items),
        _snapshot(GRANT_TICKS + 2 * TICKS_PER_SECOND, s2_items),
    ]
    watch_state = {
        "runId": None,
        "purchaseStatus": "waiting",
        "successPopupSeen": False,
        "successPopupClosed": False,
        "failurePopupSeen": False,
        "rewardEntrySeen": False,
        "packRewardFlowCompleted": False,
        "grantTimeUtcTicks": GRANT_TICKS,
        "events": [],
    }

    def invoke(listener: str, kwargs: dict):
        if listener == "busrush_qa_get_runtime_context":
            return {
                "status": "success",
                "applicationPlatform": "WindowsEditor",
                "isEditor": True,
            }
        if listener == "busrush_qa_begin_purchase_watch":
            watch_state["runId"] = kwargs["runId"]
            return {"status": "success", "runId": kwargs["runId"]}
        if listener == "busrush_qa_get_reward_storage_snapshot":
            return snapshots.pop(0)
        if listener == "busrush_qa_confirm_fake_store":
            watch_state.update(
                purchaseStatus="succeeded",
                successPopupSeen=True,
                successPopupClosed=True,
                rewardEntrySeen=True,
                packRewardFlowCompleted=True,
                events=[
                    {"event": "purchase_success"},
                    {"event": "purchase_success_popup_visible"},
                    {"event": "purchase_success_close_success"},
                    {"event": "reward_entry_active"},
                    {"event": "pack_reward_flow_completed"},
                ],
            )
            return {"status": "success"}
        if listener == "busrush_qa_get_purchase_watch":
            return dict(watch_state)
        raise AssertionError(f"unexpected QA Poco command: {listener}")

    return fake_small_bundle_poco(), invoke
