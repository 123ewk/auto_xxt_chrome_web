"""Popup/dialog detection and handling."""

import time
from pathlib import Path

from loguru import logger

import config
from core.clicker import click_center, click_template
from core.screenshot import capture, locate, locate_all, find_region_for_popup


def detect_and_handle_popup(
    templates: dict,
    max_checks: int = 5,
) -> bool:
    """Scan for and handle any visible popup/dialog.

    Detection methods:
    1. Template match against known popup buttons (confirm/ok/cancel)
    2. Contour-based popup region detection (fallback)

    Args:
        templates: Dictionary of template paths.
        max_checks: Max times to look for popups.

    Returns:
        True if a popup was detected and handled.
    """
    for check in range(max_checks):
        # Method 1: Known popup button matching
        for key in ["popup_confirm", "popup_cancel", "popup_close", "quiz_option_a"]:
            tpl = templates.get(key)
            if not tpl or not tpl.exists():
                continue

            box = locate(str(tpl), confidence=0.75)
            if box:
                logger.info(f"Popup detected — found {key}")
                click_center(box)
                time.sleep(1)
                return True

        # Method 2: Generic popup region detection
        popup_region = find_region_for_popup()
        if popup_region:
            logger.info(f"Potential popup region found: {popup_region}")
            # Try to find and click a "confirm/ok" button within the region
            confirm_btn = templates.get("popup_confirm")
            if confirm_btn and confirm_btn.exists():
                box = locate(str(confirm_btn), region=popup_region, confidence=0.75)
                if box:
                    click_center(box)
                    time.sleep(1)
                    return True

        time.sleep(config.POPUP_CHECK_INTERVAL)

    return False


def handle_quiz_popup(templates: dict) -> bool:
    """Handle quiz/dialog popups that require selecting an option.

    Tries to:
    1. Detect question text area
    2. Click the correct answer template (if available)
    3. Or click the first available option (default to A)
    4. Click confirm/submit

    Args:
        templates: Dictionary of template paths.

    Returns:
        True if quiz was handled.
    """
    logger.info("Checking for quiz popup...")

    # Click the first available option (A by default)
    for opt_key in ["quiz_option_a", "quiz_option_b", "quiz_option_c", "quiz_option_d"]:
        tpl = templates.get(opt_key)
        if tpl and tpl.exists():
            box = locate(str(tpl), confidence=0.7)
            if box:
                logger.info(f"Clicking quiz option: {opt_key}")
                click_center(box)
                time.sleep(1)

                # Click confirm/submit
                confirm = templates.get("quiz_confirm")
                if confirm and confirm.exists():
                    click_template(str(confirm), confidence=0.7)
                    time.sleep(1)

                return True

    # No quiz option found — maybe it's just a confirmation popup
    confirm = templates.get("popup_confirm")
    if confirm and confirm.exists():
        click_template(str(confirm), confidence=0.7)
        time.sleep(1)
        return True

    return False
