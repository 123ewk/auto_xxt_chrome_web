"""Click utilities with retry logic and verification."""

import time
from pathlib import Path
from typing import Callable, Optional

import pyautogui
from loguru import logger

import config
from core.screenshot import locate


def click(
    x: int,
    y: int,
    button: str = "left",
    duration: float = 0.2,
    verify_template: str | Path | None = None,
    verify_interval: float = 0.5,
    verify_timeout: float = 5.0,
) -> bool:
    """Click at the given coordinates with optional verification.

    Args:
        x, y: Screen coordinates to click.
        button: 'left' or 'right'.
        duration: Mouse movement duration in seconds.
        verify_template: If provided, wait for this template to appear/disappear.
        verify_interval: Check interval for verification.
        verify_timeout: Max wait time for verification.

    Returns:
        True if click was performed (and verified if verify_template given).
    """
    pyautogui.moveTo(x, y, duration=duration)
    time.sleep(0.2)
    pyautogui.click(button=button)
    logger.debug(f"Clicked ({x}, {y})")

    if verify_template:
        deadline = time.time() + verify_timeout
        while time.time() < deadline:
            found = locate(verify_template, confidence=0.7)
            if found:
                logger.debug(f"Verified template {Path(verify_template).name}")
                return True
            time.sleep(verify_interval)
        logger.warning(f"Verification timeout for {Path(verify_template).name}")
        return False

    return True


def click_center(
    box: tuple[int, int, int, int],
    **kwargs,
) -> bool:
    """Click the center of a bounding box.

    Args:
        box: (left, top, width, height) bounding box.
        **kwargs: Passed through to click().

    Returns:
        True if click succeeded.
    """
    x = box[0] + box[2] // 2
    y = box[1] + box[3] // 2
    return click(x, y, **kwargs)


def click_template(
    template_path: str | Path,
    region: tuple[int, int, int, int] | None = None,
    confidence: float | None = None,
    retries: int = 3,
    retry_interval: float = 1.0,
    **kwargs,
) -> bool:
    """Locate a template on screen and click its center.

    Args:
        template_path: Path to the template image.
        region: Search region.
        confidence: Matching confidence.
        retries: Number of retries if template not found.
        retry_interval: Seconds between retries.
        **kwargs: Additional args for click_center().

    Returns:
        True if template was found and clicked.
    """
    for attempt in range(1, retries + 1):
        box = locate(template_path, region=region, confidence=confidence)
        if box:
            logger.info(f"Found {Path(template_path).name} at ({box[0]}, {box[1]})")
            return click_center(box, **kwargs)

        if attempt < retries:
            logger.debug(
                f"Attempt {attempt}/{retries}: {Path(template_path).name} not found, "
                f"retrying in {retry_interval}s"
            )
            time.sleep(retry_interval)

    logger.warning(f"Template {Path(template_path).name} not found after {retries} attempts")
    return False


def wait_and_click(
    template_path: str | Path,
    timeout: int = 30,
    interval: float = 1.0,
    **kwargs,
) -> bool:
    """Wait for a template to appear, then click it.

    Args:
        template_path: Template to find and click.
        timeout: Max wait time.
        interval: Check interval.
        **kwargs: Passed to click_center().

    Returns:
        True if found and clicked.
    """
    from core.screenshot import wait_for_template

    box = wait_for_template(template_path, timeout=timeout, interval=interval)
    if box:
        return click_center(box, **kwargs)
    return False
