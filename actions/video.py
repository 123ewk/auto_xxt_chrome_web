"""Video detection, playback control and progress monitoring.

Strategy:
1. Click the video area first to focus the page
2. Use DevTools console injection for play/mute/speed
3. Monitor via OCR for completion markers
"""

import time

import pyautogui
from loguru import logger

import config
from core.console import (
    set_video_speed,
    mute_video,
    click_play_button_if_paused,
)
from core.ocr import find_text


def _click_video_area():
    """Click the center area of the screen where the video player usually is.

    This ensures:
    - The Chrome page has focus (not some other window)
    - The video player might start playing from the click
    - Any overlay/play-button in the player gets clicked
    """
    screen_w, screen_h = pyautogui.size()
    # Video player is typically in the upper 2/3 of the screen
    video_x = screen_w // 2
    video_y = screen_h // 3
    logger.info(f"点击视频区域 ({video_x}, {video_y})")
    pyautogui.click(video_x, video_y)
    time.sleep(2)


def play_current_video() -> bool:
    """Ensure the current video is playing.

    Steps:
    1. Click the video area to give Chrome focus
    2. Use DevTools to call video.play()
    3. Mute via DevTools

    Returns:
        True if operations were executed.
    """
    logger.info("=== 处理视频 ===")

    # Step 0: Click the video area first to focus the page
    logger.info("点击视频区域以聚焦页面")
    _click_video_area()

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

    Returns:
        The effective speed (2.0 on success, 1.0 on fallback).
    """
    speed = config.SPEED_DEFAULT

    for attempt in range(config.SPEED_RETRY_COUNT + 1):
        logger.info(f"尝试设置速度为 {speed}x (第 {attempt + 1} 次)")
        set_video_speed(speed)
        time.sleep(config.SPEED_RETRY_INTERVAL)

        # Try to verify by OCR — look for speed indicator on player
        result = find_text(str(speed), region=_player_region(), exact=False, min_conf=0.4)
        if result:
            logger.info(f"速度已确认为 {speed}x")
            return speed

        logger.warning(f"无法确认 {speed}x 速度")

    # Fallback
    if speed != 1.0:
        logger.warning("加速失败，降级到 1x 正常速度")
        set_video_speed(1.0)
        return 1.0

    return speed


def monitor_video_progress(stop_event=None) -> bool:
    """Monitor video playback until completion.

    Uses OCR to detect "下一节"/"继续" etc. as completion indicators.

    Args:
        stop_event: Optional threading.Event.

    Returns:
        True if video completed.
    """
    logger.info("=== 监控视频进度 ===")
    deadline = time.time() + config.VIDEO_FINISH_TIMEOUT

    progress_region = _player_region()

    while time.time() < deadline:
        if stop_event and stop_event.is_set():
            logger.info("收到停止信号")
            return False

        # Check for next-section buttons (video completed)
        for text in config.NEXT_SECTION_TEXTS:
            if find_text(text, region=progress_region, min_conf=0.5):
                logger.info(f"检测到 '{text}' — 视频播放完毕")
                time.sleep(1)
                return True

        # Also check full screen
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
    """Return estimated video player bottom area for OCR scanning.

    Returns:
        (x, y, w, h) — bottom portion of screen where player controls are.
    """
    screen_w, screen_h = pyautogui.size()
    return (0, screen_h * 2 // 3, screen_w, screen_h // 3)
