"""Screen capture utility (lightweight wrapper around pyautogui)."""

import pyautogui


def capture(region: tuple[int, int, int, int] | None = None):
    """Take a screenshot of the whole screen or a specific region.

    Args:
        region: (x, y, w, h) or None for full screen.

    Returns:
        PIL Image.
    """
    return pyautogui.screenshot(region=region)
