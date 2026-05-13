"""Section navigation: detect and click to the next section/chapter."""

import time

from loguru import logger

import config
from core.clicker import click_template
from core.screenshot import locate


def try_click_next_section(templates: dict) -> bool:
    """Try to navigate to the next section.

    Tries multiple indicators in order:
    1. "next_section" — explicit next-section button
    2. "section_unlocked" — a locked section became available
    3. "back_to_course" — return to course list button

    Args:
        templates: Dictionary of template paths.

    Returns:
        True if navigation action was taken.
    """
    # Priority 1: Direct next-section button
    next_btn = templates.get("next_section")
    if next_btn and next_btn.exists():
        clicked = click_template(str(next_btn), confidence=0.7, retries=3, retry_interval=1)
        if clicked:
            logger.info("Clicked next section button")
            time.sleep(3)
            return True

    # Priority 2: Back to course
    back_btn = templates.get("back_to_course")
    if back_btn and back_btn.exists():
        clicked = click_template(str(back_btn), confidence=0.7, retries=2)
        if clicked:
            logger.info("Clicked back to course button")
            time.sleep(3)
            return True

    # Priority 3: Newly unlocked section
    unlocked = templates.get("section_unlocked")
    if unlocked and unlocked.exists():
        clicked = click_template(str(unlocked), confidence=0.7, retries=2)
        if clicked:
            logger.info("Clicked unlocked section")
            time.sleep(3)
            return True

    # Priority 4: Generic "continue" or "next" text buttons
    # Scan known button regions for common labels
    generic_next = templates.get("generic_next")
    if generic_next and generic_next.exists():
        clicked = click_template(str(generic_next), confidence=0.6, retries=2)
        if clicked:
            logger.info("Clicked generic next/continue button")
            time.sleep(3)
            return True

    logger.debug("No navigation button found")
    return False


def has_more_content(templates: dict) -> bool:
    """Check if there is more content to process.

    Typically: if a "video playing indicator" or "section content"
    template is still visible after navigation.

    Args:
        templates: Dictionary of template paths.

    Returns:
        True if more content exists.
    """
    # If we can see a video, there's more to do
    video_indicator = templates.get("video_region")
    if video_indicator and video_indicator.exists():
        return True

    # If play button is visible again, there's a new video
    play_btn = templates.get("play_button")
    if play_btn and play_btn.exists():
        return True

    return False
