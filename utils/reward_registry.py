from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


TICKS_PER_SECOND = 10_000_000


@dataclass(frozen=True)
class RewardDefinition:
    reward_id: str
    storage_kind: str
    amount_unit: str


@dataclass(frozen=True)
class StorageCheck:
    item_id: str
    passed: bool
    message: str


BUSRUSH_REWARDS: dict[str, RewardDefinition] = {
    "gold": RewardDefinition("gold", "quantity", "count"),
    "booster_sort": RewardDefinition("booster_sort", "quantity", "count"),
    "booster_shuffle": RewardDefinition("booster_shuffle", "quantity", "count"),
    "booster_vip": RewardDefinition("booster_vip", "quantity", "count"),
    "booster_slot": RewardDefinition("booster_slot", "quantity", "count"),
    "live_amount": RewardDefinition("live_amount", "stamina", "count"),
    "unlimited_live": RewardDefinition("unlimited_live", "expiry", "seconds"),
}


def _number(value: Any, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} is not numeric: {value!r}") from exc


def _item_value(snapshot: Mapping[str, Any], item_id: str) -> Mapping[str, Any]:
    items = snapshot.get("items")
    if not isinstance(items, Mapping) or item_id not in items:
        raise ValueError(f"snapshot is missing item {item_id!r}")
    item = items[item_id]
    if not isinstance(item, Mapping):
        raise ValueError(f"snapshot item {item_id!r} must be an object")
    return item


def _aggregate_grants(
    grants: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
) -> dict[str, Decimal]:
    grant_totals: dict[str, Decimal] = {}
    for grant in grants:
        reward_id = str(grant.get("rewardId", grant.get("itemId", ""))).strip()
        if reward_id not in BUSRUSH_REWARDS:
            raise ValueError(f"unknown granted rewardId {reward_id!r}")
        definition = BUSRUSH_REWARDS[reward_id]
        unit = str(grant.get("amountUnit", definition.amount_unit))
        if unit != definition.amount_unit:
            raise ValueError(
                f"{reward_id}: amountUnit {unit!r} does not match {definition.amount_unit!r}"
            )
        amount = _number(grant.get("amount"), f"grant {reward_id}.amount")
        if amount % 1 != 0:
            raise ValueError(f"grant {reward_id}.amount must be an integer")
        grant_totals[reward_id] = grant_totals.get(reward_id, Decimal(0)) + amount

    return grant_totals


def compare_storage_snapshots(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    grants: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    grant_time_ticks: int | None = None,
    time_tolerance_seconds: int = 60,
) -> list[StorageCheck]:
    """Compare every registered BusRush item, including items absent from the pack."""
    before_items = before.get("items")
    after_items = after.get("items")
    if not isinstance(before_items, Mapping) or not isinstance(after_items, Mapping):
        raise ValueError("both snapshots must contain an items object")

    known_ids = set(BUSRUSH_REWARDS)
    missing_before = known_ids - set(before_items)
    missing_after = known_ids - set(after_items)
    unknown_before = set(before_items) - known_ids
    unknown_after = set(after_items) - known_ids
    if missing_before or missing_after:
        raise ValueError(
            f"incomplete inventory snapshot; before missing={sorted(missing_before)}, "
            f"after missing={sorted(missing_after)}"
        )
    if unknown_before or unknown_after:
        raise ValueError(
            f"snapshot contains unregistered items; before={sorted(unknown_before)}, "
            f"after={sorted(unknown_after)}"
        )

    grant_totals = _aggregate_grants(grants)
    checks: list[StorageCheck] = []

    for item_id, definition in BUSRUSH_REWARDS.items():
        s0 = _item_value(before, item_id)
        s2 = _item_value(after, item_id)
        grant = grant_totals.get(item_id, Decimal(0))

        if definition.storage_kind == "quantity":
            expected = _number(s0.get("value"), f"S0 {item_id}.value") + grant
            actual = _number(s2.get("value"), f"S2 {item_id}.value")
            passed = actual == expected
            checks.append(
                StorageCheck(
                    item_id,
                    passed,
                    f"expected {item_id}={expected}, got {actual} (grant={grant})",
                )
            )
            continue

        if definition.storage_kind == "stamina":
            before_quantity = int(s0.get("value", -1))
            actual = int(s2.get("value", -1))
            maximum = int(s0.get("max", 0))
            regen_amount = int(s0.get("regenAmount", 0))
            regen_interval = int(s0.get("regenIntervalSeconds", 0))
            before_last_ticks = int(s0.get("lastDecreaseFromMaxTicks", -1))
            after_last_ticks = int(s2.get("lastDecreaseFromMaxTicks", -1))

            regen_steps = 0
            if (
                before_last_ticks >= 0
                and after_last_ticks >= before_last_ticks
                and regen_amount > 0
                and regen_interval > 0
            ):
                interval_ticks = regen_interval * TICKS_PER_SECOND
                regen_steps = (after_last_ticks - before_last_ticks) // interval_ticks

            natural_regen = regen_steps * regen_amount
            expected = min(maximum, before_quantity + int(grant) + natural_regen)
            checks.append(
                StorageCheck(
                    item_id,
                    actual == expected,
                    f"expected {item_id}={expected}, got {actual} "
                    f"(grant={grant}, natural regen={natural_regen})",
                )
            )
            continue

        if definition.storage_kind == "expiry":
            before_end = int(s0.get("endTimeTicks", -1))
            after_end = int(s2.get("endTimeTicks", -1))
            if grant:
                if grant_time_ticks is not None:
                    grant_at = int(grant_time_ticks)
                    expected_end = max(before_end, grant_at) + int(grant) * TICKS_PER_SECOND
                    tolerance = time_tolerance_seconds * TICKS_PER_SECOND
                    passed = abs(after_end - expected_end) <= tolerance
                    message = (
                        f"expected {item_id} endTimeTicks around {expected_end}, got {after_end} "
                        f"(tolerance={time_tolerance_seconds}s)"
                    )
                else:
                    passed = False
                    message = "grant timestamp is missing for expiry comparison"
            else:
                passed = after_end == before_end
                message = f"expected {item_id} endTimeTicks unchanged at {before_end}, got {after_end}"
            checks.append(StorageCheck(item_id, passed, message))
            continue

        checks.append(StorageCheck(item_id, False, f"unsupported storage kind {definition.storage_kind!r}"))

    return checks
