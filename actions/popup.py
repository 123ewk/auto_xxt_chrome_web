"""Popup/dialog detection and handling via OCR."""

import time

from loguru import logger

import config
from core.ocr import click_text, find_any_text


def detect_and_handle_popup(
    max_checks: int = 5,
) -> bool:
    """Scan for and handle any visible popup/dialog via OCR.

    Detects popups by looking for known button texts:
    - Confirmation buttons: "确定", "确认", "知道了"
    - Cancel buttons: "取消"
    - Close buttons: "×"

    Args:
        max_checks: Max detection cycles before giving up.

    Returns:
        True if a popup was detected and handled.
    """
    for check in range(max_checks):
        # Try confirm buttons
        clicked = click_text(config.POPUP_CONFIRM_TEXTS, min_conf=0.5, retries=1)
        if clicked:
            logger.info("已点击弹窗确认按钮")
            time.sleep(1)
            return True

        # Try cancel buttons
        clicked = click_text(config.POPUP_CANCEL_TEXTS, min_conf=0.5, retries=1)
        if clicked:
            logger.info("已点击弹窗取消按钮")
            time.sleep(1)
            return True

        # Try close buttons
        clicked = click_text(config.POPUP_CLOSE_TEXTS, min_conf=0.3, retries=1)
        if clicked:
            logger.info("已点击弹窗关闭按钮")
            time.sleep(1)
            return True

        time.sleep(config.POPUP_CHECK_INTERVAL)

    return False


def handle_quiz_popup() -> bool:
    """Handle quiz/dialog popups that require selecting an option.

    Strategy:
    1. Try to find and click option A (default choice)
    2. If found, look for submit/confirm button

    Args:
        templates: Unused, kept for API compatibility.

    Returns:
        True if quiz was handled.
    """
    logger.info("检查随堂测验弹窗...")

    # Try clicking the first available quiz option
    for opt in config.QUIZ_OPTION_TEXTS:
        clicked = click_text(opt, min_conf=0.5, retries=2, retry_interval=0.8)
        if clicked:
            logger.info(f"已点击选项 {opt}")
            time.sleep(1)

            # Click submit/confirm
            click_text(config.QUIZ_CONFIRM_TEXTS, min_conf=0.5, retries=2)
            time.sleep(1)
            return True

    # Maybe it's just a confirmation dialog without quiz options
    clicked = click_text(config.POPUP_CONFIRM_TEXTS, min_conf=0.5, retries=2)
    if clicked:
        logger.info("已点击弹窗确认（非测验）")
        time.sleep(1)
        return True

    return False
