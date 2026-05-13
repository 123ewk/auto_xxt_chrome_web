"""Section navigation — OCR-based detection of next-section elements."""

import time

import pyautogui
from loguru import logger

import config
from core.ocr import find_any_text, click_text


def try_click_next_section() -> bool:
    """Try to navigate to the next section via OCR text detection.

    Searches for navigation button texts in priority order:
    1. Next-section buttons ("下一节", "下一个", "继续")
    2. Back-to-course buttons ("返回课程", "返回")

    Args:
        templates: Unused, kept for API compatibility.

    Returns:
        True if a navigation action was taken.
    """
    # Priority 1: "下一节" / "下一个"
    clicked = click_text(
        config.NEXT_SECTION_TEXTS,
        min_conf=0.5,
        retries=3,
        retry_interval=1.5,
    )
    if clicked:
        logger.info("已点击下一节/继续按钮")
        time.sleep(3)
        return True

    # Priority 2: "返回课程"
    clicked = click_text(
        config.BACK_TO_COURSE_TEXTS,
        min_conf=0.5,
        retries=2,
        retry_interval=1.5,
    )
    if clicked:
        logger.info("已点击返回课程按钮")
        time.sleep(3)
        return True

    # Priority 3: "继续" / "下一步" (generic)
    clicked = click_text(
        config.CONTINUE_TEXTS,
        min_conf=0.5,
        retries=2,
        retry_interval=1.5,
    )
    if clicked:
        logger.info("已点击继续/下一步按钮")
        time.sleep(3)
        return True

    logger.debug("未检测到导航按钮")
    return False


def has_more_content() -> bool:
    """Check if there is more content to process.

    Simple heuristic: if we can still see the browser window and
    the page has not navigated to a final "complete" state,
    assume there's more content.

    Returns:
        True if likely more content exists.
    """
    # Check for "完成" completion text
    done = find_any_text(
        ["已完成全部任务", "学习完成", "全部完成"],
        min_conf=0.4,
    )
    if done:
        logger.info("检测到全部完成标记")
        return False

    # Default to assuming there's more (will timeout naturally if not)
    return True
