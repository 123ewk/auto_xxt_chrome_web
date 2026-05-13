"""Video detection, playback control and progress monitoring."""

import time
from pathlib import Path

import pyautogui
from loguru import logger

import config
from core.clicker import click_template, click
from core.console import (
    set_video_speed,
    mute_video,
    click_play_button_if_paused,
    check_video_state,
)


def play_current_video(templates: dict) -> bool:
    """Ensure the current video is playing.

    Strategy:
    1. Check if play button template is visible → click it
    2. Also inject video.play() via DevTools as a backup
    3. Mute the video
    4. Set playback speed (with fallback)

    Args:
        templates: Dictionary of template paths.

    Returns:
        True if the video appears to be playing.
    """
    logger.info("Checking video state...")

    # Step 1: Click play button if visible (PyAutoGUI)
    play_btn = templates.get("play_button")
    if play_btn and play_btn.exists():
        clicked = click_template(str(play_btn), confidence=0.7, retries=2)
        if clicked:
            logger.info("Clicked play button")
            time.sleep(2)

    # Step 2: Inject play() via DevTools
    logger.info("Injecting video.play() via DevTools...")
    click_play_button_if_paused()
    time.sleep(2)

    # Step 3: Mute
    logger.info("Muting video...")
    mute_video()
    time.sleep(1)

    # Step 4: Also try clicking mute button on player as backup
    mute_btn = templates.get("mute_button")
    if mute_btn and mute_btn.exists():
        click_template(str(mute_btn), confidence=0.7, retries=1)

    return True


def set_speed_with_fallback(templates: dict) -> float:
    """Try to set video speed, with fallback if it doesn't stick.

    Returns:
        The effective speed (2.0 on success, 1.0 on fallback).
    """
    speed = config.SPEED_DEFAULT

    for attempt in range(config.SPEED_RETRY_COUNT + 1):
        logger.info(f"Setting speed to {speed}x (attempt {attempt + 1})...")
        set_video_speed(speed)
        time.sleep(config.SPEED_RETRY_INTERVAL)

        # Verify: check if speed button shows the new speed
        speed_label = templates.get(f"speed_{speed}x")
        if speed_label and speed_label.exists():
            # Check if the current speed label is visible as confirmation
            found = False
            for _ in range(3):
                if speed_label.exists():
                    found = True
                    break
                time.sleep(1)
            if found:
                logger.info(f"Speed confirmed at {speed}x")
                return speed

        logger.warning(f"Speed {speed}x may not have been applied")

    # Fallback to normal speed
    if speed != 1.0:
        logger.warning(f"Falling back to 1x speed")
        set_video_speed(1.0)
        return 1.0

    return speed


def monitor_video_progress(
    templates: dict,
    stop_event=None,
) -> bool:
    """Monitor video playback until completion.

    Checks periodically:
    - Is the video still playing?
    - Has the "complete" indicator appeared?
    - Has the UI changed to indicate the video is done?
    - Timing-based safeguard timeout

    Args:
        templates: Dictionary of template paths.
        stop_event: Optional threading.Event for external stop.

    Returns:
        True if video completed, False on timeout/error.
    """
    logger.info("Monitoring video progress...")
    deadline = time.time() + config.VIDEO_FINISH_TIMEOUT

    # Templates that indicate video completion
    completion_markers = [
        templates.get("complete_checkmark"),
        templates.get("task_complete"),
    ]
    completion_markers = [t for t in completion_markers if t and t.exists()]

    while time.time() < deadline:
        if stop_event and stop_event.is_set():
            logger.info("Stop event received, exiting monitor")
            return False

        # Check for completion indicators
        for marker in completion_markers:
            if marker and marker.exists():
                logger.info(f"Completion marker detected: {marker.name}")
                return True

        # Check for "next section" button appearing (video done)
        next_btn = templates.get("next_section")
        if next_btn and next_btn.exists():
            logger.info("Next section button detected — video completed")
            return True

        # Heartbeat
        logger.debug("Video still in progress...")
        time.sleep(config.VIDEO_CHECK_INTERVAL)

    logger.warning(f"Video monitor timed out after {config.VIDEO_FINISH_TIMEOUT}s")
    return False
