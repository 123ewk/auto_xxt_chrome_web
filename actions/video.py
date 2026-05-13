"""Video detection, playback control and progress monitoring.

All video control is done through DevTools console injection.
No random mouse clicks — the script only interacts with DevTools.
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


def play_current_video() -> bool:
    """Play the current video via DevTools console injection.

    Opens DevTools and injects play() → mute() → speed() sequentially.
    No mouse clicks on the page.

    Returns:
        True if operations were executed.
    """
    logger.info("=== 处理视频 ===")

    # All video control happens through DevTools console injection
    logger.info("通过 DevTools 执行播放")
    click_play_button_if_paused()
    time.sleep(1.5)

    logger.info("通过 DevTools 执行静音")
    mute_video()
    time.sleep(1)

    logger.info("通过 DevTools 执行加速")
    set_speed_with_fallback_inline()

    return True


def set_speed_with_fallback_inline() -> float:
    """Set speed with fallback."""
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
    screen_w, screen_h = pyautogui.size()
    return (0, screen_h * 2 // 3, screen_w, screen_h // 3)
