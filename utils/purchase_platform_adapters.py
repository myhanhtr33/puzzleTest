from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Mapping, Protocol


class PurchasePlatformError(RuntimeError):
    pass


class PurchasePlatformAdapter(Protocol):
    name: str

    def after_buy_click(self, poco: Any, product_id: str) -> None: ...


@dataclass(frozen=True)
class WindowsEditorAdapter:
    name: str = "windows_editor"

    def after_buy_click(self, poco: Any, product_id: str) -> None:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            result = poco.invoke("busrush_qa_confirm_fake_store", productId=product_id)
            if isinstance(result, Mapping) and result.get("status") == "success":
                return
            if isinstance(result, Mapping) and result.get("status") == "not_ready":
                time.sleep(0.1)
                continue
            detail = result.get("message", result) if isinstance(result, Mapping) else result
            raise PurchasePlatformError(f"FakeStore confirmation failed: {detail}")
        raise PurchasePlatformError("FakeStore dialog did not appear within 20 seconds")


@dataclass(frozen=True)
class AndroidPlayAdapter:
    name: str = "android"

    def after_buy_click(self, poco: Any, product_id: str) -> None:
        return None


@dataclass(frozen=True)
class IOSStoreKitAdapter:
    name: str = "ios"

    def after_buy_click(self, poco: Any, product_id: str) -> None:
        return None


def adapter_for_runtime(runtime: Mapping[str, Any]) -> PurchasePlatformAdapter:
    platform = str(runtime.get("applicationPlatform", runtime.get("platform", ""))).lower()
    is_editor = bool(runtime.get("isEditor", False))

    if is_editor or "windowseditor" in platform:
        return WindowsEditorAdapter()
    if "android" in platform:
        return AndroidPlayAdapter()
    if "iphone" in platform or "ios" in platform:
        return IOSStoreKitAdapter()
    raise PurchasePlatformError(f"unsupported BusRush purchase platform: {platform!r}")
