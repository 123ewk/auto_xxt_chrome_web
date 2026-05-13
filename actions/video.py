"""Video detection, playback control and progress monitoring.

Video control flow:
1. Click the page (non-video area) to give Chrome focus
2. Open DevTools first (before any play happens)
3. Inject all JS commands: play → mute → speed
4. Close DevTools to avoid detection

This avoids the issue where opening DevTools mid-playback
triggers the platform's anti-cheat pause.
"""

import time

import pyautogui
from loguru import logger

import config
from core.console import (
    set_video_speed,
    mute_video,
    click_play_button_if_paused,
    close_devtools,
)
from core.ocr import find_text


def _focus_chrome():
    """Click a neutral area of the Chrome window to ensure it has focus.

    Clicks the very top-left of the screen (Chrome tab bar area)
    to focus Chrome without interacting with the video player.
    """
    pyautogui.click(50, 30)  # top-left: Chrome tab/address bar area
    time.sleep(1)


def play_current_video() -> bool:
    """Play the current video.

    Sequence:
    1. Focus Chrome window (neutral click on tab area)
    2. Open DevTools and inject play/mute/speed commands
    3. Close DevTools to minimize detection window

    Returns:
        True if operations were executed.
    """
    logger.info("=== 处理视频 ===")

    # Step 1: Focus Chrome
    _focus_chrome()

    # Step 2: Open DevTools and inject all commands sequentially
    # DevTools is opened first so the platform only sees one focus
    # transition (page → DevTools), then immediately injects everything
    logger.info("通过 DevTools 执行播放、静音、加速")
    click_play_button_if_paused()
    time.sleep(1)
    mute_video()
    time.sleep(1)
    set_speed_with_fallback_inline()

    # Step 3: Close DevTools so the page can focus back
    # close_devtools()

    return True


def set_speed_with_fallback_inline() -> float:
    """Set speed with fallback (inline version, no separate DevTools open)."""
    speed = config.SPEED_DEFAULT

    for attempt in range(config.SPEED_RETRY_COUNT + 1):
        logger.info(f"尝试设置速度为 {speed}x (第 {attempt + 1} 次)")
        set_video_speed(speed)
        time.sleep(config.SPEED_RETRY_INTERVAL)

        result = find_text(str(speed), region=_player_region(), exact=False, min_conf=0.4)
        if result:
            logger.info(f"速度已确认为 {speed}x")
            return speed

    if speed != 1.0:
        logger.warning("加速失败，降级到 1x 正常速度")
        set_video_speed(1.0)
        return 1.0
    return speed


def set_speed_with_fallback() -> float:
    """Alias for external callers."""
    return set_speed_with_fallback_inline()


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

        for text in config.NEXT_SECTION_TEXTS:
            if find_text(text, region=progress_region, min_conf=0.5):
                logger.info(f"检测到 '{text}' — 视频播放完毕")
                time.sleep(1)
                return True

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
