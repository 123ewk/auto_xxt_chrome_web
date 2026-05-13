"""Click utilities with retry logic and verification."""

import time

import pyautogui
from loguru import logger


def click_center(box: tuple[int, int, int, int], button: str = "left", duration: float = 0.2) -> bool:
    """Click the center of a bounding box.

    Args:
        box: (left, top, width, height).
        button: 'left' or 'right'.
        duration: Mouse movement duration.

    Returns:
        True always.
    """
    x = box[0] + box[2] // 2
    y = box[1] + box[3] // 2
    pyautogui.moveTo(x, y, duration=duration)
    time.sleep(0.15)
    pyautogui.click(button=button)
    logger.debug(f"Clicked center of box ({x}, {y})")
    return True
