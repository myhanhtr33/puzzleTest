from __future__ import annotations

import argparse
from dataclasses import dataclass
import sys

import win32gui
import win32process


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    process_id: int


def list_visible_top_level_windows() -> list[WindowInfo]:
    windows: list[WindowInfo] = []

    def collect(hwnd: int, _: object) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True

        title = win32gui.GetWindowText(hwnd).strip()
        class_name = win32gui.GetClassName(hwnd).strip()
        if not title:
            return True

        _, process_id = win32process.GetWindowThreadProcessId(hwnd)
        windows.append(WindowInfo(hwnd, title, class_name, process_id))
        return True

    win32gui.EnumWindows(collect, None)
    return windows


def select_game_windows(
    windows: list[WindowInfo], title_filter: str | None, class_filter: str | None
) -> list[WindowInfo]:
    if title_filter or class_filter:
        return [
            window
            for window in windows
            if (not title_filter or title_filter.casefold() in window.title.casefold())
            and (not class_filter or class_filter.casefold() in window.class_name.casefold())
        ]

    return [
        window
        for window in windows
        if "unity" in window.class_name.casefold()
        or "gameview" in window.class_name.casefold()
    ]


def main() -> int:
    reconfigure_stdout = getattr(sys.stdout, "reconfigure", None)
    if reconfigure_stdout is not None:
        reconfigure_stdout(errors="backslashreplace")

    parser = argparse.ArgumentParser(
        description="Find the visible top-level game window and print its Airtest Windows URI."
    )
    parser.add_argument("--title", help="case-insensitive substring of the window title")
    parser.add_argument("--class", dest="class_filter", help="case-insensitive class-name substring")
    args = parser.parse_args()

    windows = list_visible_top_level_windows()
    candidates = select_game_windows(windows, args.title, args.class_filter)

    if len(candidates) == 1:
        window = candidates[0]
        print(f"HWND: {window.hwnd} | HEX: {hex(window.hwnd)}")
        print(f"TITLE: {window.title}")
        print(f"CLASS: {window.class_name} | PID: {window.process_id}")
        print(f"Airtest URI: Windows:///{window.hwnd}")
        return 0

    if candidates:
        print(f"Found {len(candidates)} matching top-level windows; no window selected:")
        for window in candidates:
            print(
                f"HWND: {window.hwnd} | TITLE: {window.title} | "
                f"CLASS: {window.class_name} | PID: {window.process_id}"
            )
        print("Narrow the result with --title or --class.")
        return 2

    print("No matching game window found.")
    if windows:
        print("Visible top-level windows:")
        for window in windows:
            print(
                f"HWND: {window.hwnd} | TITLE: {window.title} | "
                f"CLASS: {window.class_name} | PID: {window.process_id}"
            )
        print("Select a window with --title and/or --class.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
