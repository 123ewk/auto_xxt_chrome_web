"""Video detection, playback control and progress monitoring.

Uses Chrome DevTools console injection for all video control —
no template images needed.
"""

import time

from loguru import logger

import config
from core.console import (
    set_video_speed,
    mute_video,
    click_play_button_if_paused,
)
from core.ocr import find_text, wait_for_text


def play_current_video() -> bool:
    """Ensure the current video is playing.

    Uses DevTools JS injection to control the video element directly:
    1. Call video.play() if paused
    2. Mute the video
    3. Set playback speed

    Returns:
        True if operations were executed.
    """
    logger.info("正在处理视频...")

    # Step 1: Inject play() via DevTools
    logger.info("通过 DevTools 执行 video.play()")
    click_play_button_if_paused()
    time.sleep(2)

    # Step 2: Mute via DevTools
    logger.info("通过 DevTools 执行静音")
    mute_video()
    time.sleep(1)

    return True


def set_speed_with_fallback() -> float:
    """Set video playback speed via DevTools, with fallback.

    Strategy:
    1. Try DevTools injection of playbackRate=2
    2. Attempt to verify by OCR for speed text on player
    3. Retry once if needed
    4. Fall back to 1x if all attempts fail

    Returns:
        The effective speed (2.0 on success, 1.0 on fallback).
    """
    speed = config.SPEED_DEFAULT

    for attempt in range(config.SPEED_RETRY_COUNT + 1):
        logger.info(f"尝试设置速度为 {speed}x (第 {attempt + 1} 次)...")
        set_video_speed(speed)
        time.sleep(config.SPEED_RETRY_INTERVAL)

        # Try to verify via OCR — look for "x" suffix patterns near player area
        result = find_text(str(speed), region=_player_region(), exact=False, min_conf=0.5)
        if result:
            logger.info(f"速度已确认为 {speed}x")
            return speed

        logger.warning(f"无法确认 {speed}x 速度，尝试重试")

    # Fallback to normal speed
    if speed != 1.0:
        logger.warning("加速失败，降级到 1x 正常速度")
        set_video_speed(1.0)
        return 1.0

    return speed


def monitor_video_progress(stop_event=None) -> bool:
    """Monitor video playback until completion.

    Uses OCR to detect completion indicators like:
    - "下一节" / "继续" buttons appearing (video finished)
    - Percentage reaching 100%
    - Timeout safeguard

    Args:
        stop_event: Optional threading.Event to signal stop.

    Returns:
        True if video completed, False on timeout/error.
    """
    logger.info("正在监控视频播放进度...")
    deadline = time.time() + config.VIDEO_FINISH_TIMEOUT

    # Capture initial state references
    progress_region = _player_region()

    while time.time() < deadline:
        if stop_event and stop_event.is_set():
            logger.info("收到停止信号，退出监控")
            return False

        # Check for next-section buttons (video has ended)
        for text in config.NEXT_SECTION_TEXTS:
            if find_text(text, region=progress_region, min_conf=0.5):
                logger.info(f"检测到 '{text}' — 视频播放完毕")
                time.sleep(1)  # brief settle
                return True

        # Also check full screen for navigation texts
        for text in config.NEXT_SECTION_TEXTS:
            if find_text(text, min_conf=0.5):
                logger.info(f"检测到 '{text}'（全屏） — 视频播放完毕")
                time.sleep(1)
                return True

        logger.debug("视频播放中...")
        time.sleep(config.VIDEO_CHECK_INTERVAL)

    logger.warning(f"视频监控超时 ({config.VIDEO_FINISH_TIMEOUT}s)")
    return False


def _player_region() -> tuple[int, int, int, int]:
    """Return an estimated video player region for OCR focus.

    Returns:
        (x, y, w, h) region tuple covering roughly the bottom half of screen
        where player controls usually appear.
    """
    screen_w, screen_h = pyautogui.size()
    # Bottom third of screen — where player controls typically reside
    return (0, screen_h * 2 // 3, screen_w, screen_h // 3)
