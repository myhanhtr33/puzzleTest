from __future__ import annotations

import base64
import json
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any


@dataclass
class ContractReportCollector:
    reports: list[tuple[str, Any]] = field(default_factory=list)
    purchase_reports: list[tuple[str, Any]] = field(default_factory=list)
    debug_images: list[Path] = field(default_factory=list)
    html_extras: list[dict[str, Any]] | None = None
    generated_extras: list[dict[str, Any]] = field(default_factory=list)


_ACTIVE_COLLECTOR: ContextVar[ContractReportCollector | None] = ContextVar(
    "ui_contract_report_collector", default=None
)


def activate_collector(collector: ContractReportCollector) -> Token:
    return _ACTIVE_COLLECTOR.set(collector)


def deactivate_collector(token: Token) -> None:
    _ACTIVE_COLLECTOR.reset(token)


def is_collecting() -> bool:
    return _ACTIVE_COLLECTOR.get() is not None


def record_contract_report(report: Any, name: str) -> None:
    collector = _ACTIVE_COLLECTOR.get()
    if collector is not None:
        collector.reports.append((name, report))
        _publish_extras(collector)


def record_purchase_flow_report(report: Any, name: str) -> None:
    collector = _ACTIVE_COLLECTOR.get()
    if collector is not None:
        collector.purchase_reports.append((name, report))
        _publish_extras(collector)


def record_debug_image(path: Path) -> None:
    collector = _ACTIVE_COLLECTOR.get()
    if collector is not None:
        collector.debug_images.append(path)


def attach_html_extras(collector: ContractReportCollector, html_extras: list[dict[str, Any]]) -> None:
    collector.html_extras = html_extras


def build_pytest_html_extras(collector: ContractReportCollector) -> list[dict[str, Any]]:
    import pytest_html

    extras: list[dict[str, Any]] = []
    if collector.reports:
        rows: list[str] = []
        for run_index, (name, report) in enumerate(collector.reports, start=1):
            for assertion in report.assertions:
                status = "pass" if assertion.passed else "fail"
                rows.append(
                    "<tr class='{status}'>"
                    "<td>{run_index}</td><td>{contract}</td><td>{test_id}</td>"
                    "<td>{assertion}</td><td>{status}</td><td>{message}</td></tr>".format(
                        status=status,
                        run_index=run_index,
                        contract=escape(name),
                        test_id=escape(assertion.test_id),
                        assertion=escape(assertion.assertion),
                        message=escape(assertion.message),
                    )
                )

        passed = sum(
            assertion.passed
            for _, report in collector.reports
            for assertion in report.assertions
        )
        failed = sum(
            len(report.failures)
            for _, report in collector.reports
        )
        summary = "{passed} passed, {failed} failed".format(
            passed=passed,
            failed=failed,
        )
        table = (
            "<h3>UI contract assertions: {summary}</h3>"
            "<table class='ui-contract-results'>"
            "<thead><tr><th>Run</th><th>Contract</th><th>testId</th>"
            "<th>Assertion</th><th>Result</th><th>Message</th></tr></thead>"
            "<tbody>{rows}</tbody></table>"
        ).format(summary=escape(summary), rows="".join(rows))
        extras.append(pytest_html.extras.html(table))

    if collector.purchase_reports:
        rows = []
        for run_index, (name, report) in enumerate(collector.purchase_reports, start=1):
            before_items = report.storage_before.get("items", {})
            after_items = report.storage_after.get("items", {})
            for check in report.storage_checks:
                before = json.dumps(before_items.get(check.item_id), sort_keys=True, ensure_ascii=False)
                after = json.dumps(after_items.get(check.item_id), sort_keys=True, ensure_ascii=False)
                rows.append(
                    "<tr class='{status}'>"
                    "<td>{run_index}</td><td>{name}</td><td>{item}</td>"
                    "<td><code>{before}</code></td><td><code>{after}</code></td>"
                    "<td>{expectation}</td><td>{status}</td></tr>".format(
                        status="pass" if check.passed else "fail",
                        run_index=run_index,
                        name=escape(name),
                        item=escape(check.item_id),
                        before=escape(before),
                        after=escape(after),
                        expectation=escape(check.message),
                    )
                )
        table = (
            "<h3>Purchase flow storage checks</h3>"
            "<table class='purchase-storage-results'>"
            "<thead><tr><th>Run</th><th>Test</th><th>Item</th>"
            "<th>Before (S0)</th><th>After (S2)</th><th>Expected / check</th>"
            "<th>Result</th></tr></thead><tbody>{rows}</tbody></table>"
        ).format(rows="".join(rows))
        extras.append(pytest_html.extras.html(table))

    for image_path in collector.debug_images:
        if image_path.is_file():
            encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
            extras.append(pytest_html.extras.image(encoded, name=image_path.name))

    return extras


def _publish_extras(collector: ContractReportCollector) -> None:
    if collector.html_extras is None:
        return
    collector.html_extras[:] = [
        extra
        for extra in collector.html_extras
        if all(extra is not generated for generated in collector.generated_extras)
    ]
    collector.generated_extras = build_pytest_html_extras(collector)
    collector.html_extras.extend(collector.generated_extras)
