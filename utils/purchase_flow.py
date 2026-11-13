from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from utils.purchase_platform_adapters import adapter_for_runtime
from utils.reward_registry import StorageCheck, compare_storage_snapshots
from utils.ui_contracts import ContractReport, ManifestError, UIContractRunner, run_contract


@dataclass
class PurchaseFlowReport:
    run_id: str
    platform: str
    purchase_status: str
    watcher: Mapping[str, Any]
    storage_before: Mapping[str, Any]
    storage_after: Mapping[str, Any]
    storage_checks: list[StorageCheck]
    ui_before: ContractReport
    ui_after: ContractReport

    @property
    def passed(self) -> bool:
        event_names = [str(item.get("event", "")) for item in self.watcher.get("events", [])]
        required_events = (
            "purchase_success",
            "purchase_success_popup_visible",
            "purchase_success_close_success",
            "reward_entry_active",
            "pack_reward_flow_completed",
        )
        cursor = 0
        for event_name in event_names:
            if cursor < len(required_events) and event_name == required_events[cursor]:
                cursor += 1
        return (
            self.purchase_status == "succeeded"
            and bool(self.watcher.get("successPopupSeen"))
            and bool(self.watcher.get("successPopupClosed"))
            and bool(self.watcher.get("rewardEntrySeen"))
            and bool(self.watcher.get("packRewardFlowCompleted"))
            and cursor == len(required_events)
            and self.ui_before.passed
            and self.ui_after.passed
            and all(check.passed for check in self.storage_checks)
        )

    def format(self) -> str:
        lines = [
            f"Purchase flow {self.run_id} on {self.platform}: {self.purchase_status}",
            f"Popup success seen: {self.watcher.get('successPopupSeen')}",
            f"Popup success closed: {self.watcher.get('successPopupClosed')}",
            f"Reward entry active seen: {self.watcher.get('rewardEntrySeen')}",
            f"Pack reward flow complete: {self.watcher.get('packRewardFlowCompleted')}",
        ]
        lines.extend(
            f"- {'PASS' if check.passed else 'FAIL'} {check.item_id}: {check.message}"
            for check in self.storage_checks
        )
        if not self.ui_before.passed:
            lines.append(self.ui_before.format())
        if not self.ui_after.passed:
            lines.append(self.ui_after.format())
        return "\n".join(lines)


def _freeze(poco: Any) -> Any:
    freeze = getattr(poco, "freeze", None)
    return freeze() if callable(freeze) else poco


def _buy_button(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    buttons = [
        obj
        for obj in manifest.get("objects", [])
        if obj.get("contractType", "ui") == "button" and obj.get("buttonType") == "buy"
    ]
    if len(buttons) != 1:
        raise ManifestError(f"purchase flow requires exactly one buy button, found {len(buttons)}")
    return buttons[0]


def _grants_for_button(
    manifest: Mapping[str, Any], button: Mapping[str, Any]
) -> list[dict[str, Any]]:
    granted_ids = set(button.get("grants", []))
    rewards = [
        obj
        for obj in manifest.get("objects", [])
        if obj.get("contractType") == "reward" and obj.get("rewardId") in granted_ids
    ]
    missing = granted_ids - {obj.get("rewardId") for obj in rewards}
    if missing:
        raise ManifestError(f"buy button references reward nodes not present in contract: {sorted(missing)}")
    return [
        {
            "rewardId": obj["rewardId"],
            "amount": obj["amount"],
            "amountUnit": obj.get("amountUnit", "count"),
        }
        for obj in rewards
    ]


def _wait_for_terminal_watch(
    poco: Any,
    run_id: str,
    timeout_seconds: float,
    poll_interval: float,
) -> Mapping[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    latest: Mapping[str, Any] = {}
    while time.monotonic() < deadline:
        latest_raw = poco.invoke("busrush_qa_get_purchase_watch", runId=run_id)
        if not isinstance(latest_raw, Mapping):
            raise RuntimeError(f"invalid watcher response: {latest_raw!r}")
        latest = latest_raw
        purchase_status = str(latest.get("purchaseStatus", "waiting")).lower()
        watch_status = str(latest.get("watchStatus", "watching")).lower()
        if watch_status == "timed_out" and purchase_status == "succeeded":
            raise TimeoutError(f"purchase succeeded but reward flow did not settle: {dict(latest)}")
        if purchase_status in {"failed", "cancelled", "timed_out", "error"}:
            return latest
        if (
            purchase_status == "succeeded"
            and latest.get("successPopupSeen")
            and latest.get("rewardEntrySeen")
            and latest.get("packRewardFlowCompleted")
        ):
            return latest
        time.sleep(poll_interval)
    raise TimeoutError(
        "purchase watcher timed out; last state="
        f"{dict(latest) if latest else 'no response'}"
    )


def run_pack_purchase_flow(
    poco: Any,
    manifest: Mapping[str, Any],
    *,
    timeout_seconds: float = 360,
    poll_interval: float = 0.5,
    run_id: str | None = None,
    checkers: Mapping[str, Any] | None = None,
) -> PurchaseFlowReport:
    """Execute one diagram-defined purchase and compare complete S0/S2 inventory."""
    button = _buy_button(manifest)
    run_id = run_id or uuid.uuid4().hex

    runtime = poco.invoke("busrush_qa_get_runtime_context")
    if not isinstance(runtime, Mapping) or runtime.get("status", "success") != "success":
        raise RuntimeError(f"could not determine Unity runtime platform: {runtime!r}")
    adapter = adapter_for_runtime(runtime)
    active_checkers = dict(checkers or {})

    ui_before = run_contract(_freeze(poco), manifest, checkers=active_checkers)
    if not ui_before.passed:
        raise AssertionError(ui_before.format())

    watcher_start = poco.invoke(
        "busrush_qa_begin_purchase_watch",
        runId=run_id,
        productId=str(button["productId"]),
    )
    if not isinstance(watcher_start, Mapping) or watcher_start.get("status") != "success":
        raise RuntimeError(f"could not arm purchase watcher: {watcher_start!r}")

    storage_before = poco.invoke("busrush_qa_get_reward_storage_snapshot")
    if not isinstance(storage_before, Mapping) or storage_before.get("status") != "success":
        raise RuntimeError(f"could not read S0 inventory snapshot: {storage_before!r}")

    live_runner = UIContractRunner(poco, manifest)
    button_node = live_runner.resolve(str(button["testId"]))
    click = getattr(button_node, "click", None)
    if not callable(click):
        raise RuntimeError(f"buy node {button['testId']!r} does not support click()")
    click()
    adapter.after_buy_click(poco, str(button["productId"]))

    watcher = _wait_for_terminal_watch(poco, run_id, timeout_seconds, poll_interval)
    storage_after = poco.invoke("busrush_qa_get_reward_storage_snapshot")
    if not isinstance(storage_after, Mapping) or storage_after.get("status") != "success":
        raise RuntimeError(f"could not read final S2 inventory snapshot: {storage_after!r}")

    purchase_status = str(watcher.get("purchaseStatus", "error")).lower()
    is_success = purchase_status == "succeeded"
    grants = _grants_for_button(manifest, button) if is_success else []
    storage_checks = compare_storage_snapshots(
        storage_before,
        storage_after,
        grants,
        grant_time_ticks=(
            int(watcher["grantTimeUtcTicks"])
            if is_success and watcher.get("grantTimeUtcTicks") is not None
            else None
        ),
    )
    ui_after = run_contract(_freeze(poco), manifest, checkers=active_checkers)
    report = PurchaseFlowReport(
        run_id=run_id,
        platform=adapter.name,
        purchase_status=purchase_status,
        watcher=watcher,
        storage_before=storage_before,
        storage_after=storage_after,
        storage_checks=storage_checks,
        ui_before=ui_before,
        ui_after=ui_after,
    )
    from utils.ui_contract_reporting import record_purchase_flow_report

    record_purchase_flow_report(report, str(button.get("label", button["testId"])))
    if not report.passed:
        raise AssertionError(report.format())
    return report
