"""Screen capture and template matching utilities."""

import time
from pathlib import Path
from typing import Optional

import pyautogui
import cv2
import numpy as np
from loguru import logger

import config


def capture(region: tuple[int, int, int, int] | None = None) -> "pyautogui.Image":
    """Take a screenshot of the whole screen or a specific region.

    Args:
        region: (x, y, width, height) tuple. If None, captures full screen.

    Returns:
        PIL Image object.
    """
    return pyautogui.screenshot(region=region)


def locate(
    template_path: str | Path,
    region: tuple[int, int, int, int] | None = None,
    confidence: float | None = None,
    grayscale: bool | None = None,
) -> tuple[int, int, int, int] | None:
    """Locate a template image on screen.

    Args:
        template_path: Path to the template image.
        region: Search region (x, y, w, h). If None, searches whole screen.
        confidence: Matching confidence (0-1). Defaults to config.CONFIDENCE.
        grayscale: Whether to use grayscale matching. Defaults to config.GRAYSCALE.

    Returns:
        (left, top, width, height) bounding box, or None if not found.
    """
    conf = confidence if confidence is not None else config.CONFIDENCE
    gray = grayscale if grayscale is not None else config.GRAYSCALE

    try:
        box = pyautogui.locateOnScreen(
            str(template_path),
            region=region,
            confidence=conf,
            grayscale=gray,
        )
        return box
    except pyautogui.ImageNotFoundException:
        return None
    except Exception as e:
        logger.warning(f"locate() error on {Path(template_path).name}: {e}")
        return None


def locate_all(
    template_path: str | Path,
    region: tuple[int, int, int, int] | None = None,
    confidence: float | None = None,
    grayscale: bool | None = None,
) -> list[tuple[int, int, int, int]]:
    """Find all occurrences of a template on screen.

    Returns:
        List of bounding boxes (left, top, width, height).
    """
    conf = confidence if confidence is not None else config.CONFIDENCE
    gray = grayscale if grayscale is not None else config.GRAYSCALE

    try:
        boxes = list(
            pyautogui.locateAllOnScreen(
                str(template_path),
                region=region,
                confidence=conf,
                grayscale=gray,
            )
        )
        return boxes
    except pyautogui.ImageNotFoundException:
        return []
    except Exception as e:
        logger.warning(f"locate_all() error on {Path(template_path).name}: {e}")
        return []


def find_region_for_popup(full_screen: Optional["pyautogui.Image"] = None) -> tuple[int, int, int, int] | None:
    """Detect a popup/dialog in the upper part of the screen.

    Uses edge detection + contour finding to locate dialog-like regions.

    Args:
        full_screen: Pre-captured screenshot. If None, captures now.

    Returns:
        Bounding box (x, y, w, h) of the largest dialog-like region, or None.
    """
    try:
        import cv2
        import numpy as np

        if full_screen is None:
            full_screen = capture()

        # Convert PIL to OpenCV
        img = cv2.cvtColor(np.array(full_screen), cv2.COLOR_RGB2BGR)
        h, w = img.shape[:2]

        # Crop top portion of the screen (popups usually appear in center)
        roi_h = int(h * config.POPUP_REGION_RATIO * 3)
        roi = img[h // 4 : h // 4 + roi_h, w // 4 : 3 * w // 4]

        # Edge detection
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        dilated = cv2.dilate(edges, None, iterations=3)

        # Find contours
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return None

        # Find largest contour
        largest = max(contours, key=cv2.contourArea)
        x, y, bw, bh = cv2.boundingRect(largest)

        # Offset back to screen coordinates
        screen_x = w // 4 + x
        screen_y = h // 4 + y

        return (screen_x, screen_y, bw, bh)
    except Exception as e:
        logger.debug(f"find_region_for_popup error: {e}")
        return None


def wait_for_template(
    template_path: str | Path,
    timeout: int = 30,
    interval: float = 1.0,
    region: tuple[int, int, int, int] | None = None,
    confidence: float | None = None,
) -> tuple[int, int, int, int] | None:
    """Wait for a template to appear on screen.

    Args:
        template_path: Template image path.
        timeout: Max wait time in seconds.
        interval: Check interval in seconds.
        region: Optional search region.
        confidence: Matching confidence.

    Returns:
        Bounding box if found within timeout, else None.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = locate(template_path, region=region, confidence=confidence)
        if result:
            return result
        time.sleep(interval)
    logger.warning(f"Timeout waiting for {Path(template_path).name} ({timeout}s)")
    return None


def capture_region_for_training(
    save_path: str | Path,
    description: str = "",
):
    """Capture a screen region and save it for creating templates later.

    Gives the user 5 seconds to position the mouse to select region corners.

    Args:
        save_path: Where to save the image.
        description: Optional description to print.
    """
    if description:
        print(f"\n{description}")
    logger.info("请将鼠标移动到要截图区域的左上角，然后按 Enter")
    print("Move to the top-left corner of the region and press Enter...")
    input()
    x1, y1 = pyautogui.position()
    logger.info(f"左上角坐标: ({x1}, {y1})")
    print("Move to the bottom-right corner and press Enter...")
    logger.info("请将鼠标移动到要截图区域的右下角，然后按 Enter")
    input()
    x2, y2 = pyautogui.position()
    logger.info(f"右下角坐标: ({x2}, {y2})")

    x, y = min(x1, x2), min(y1, y2)
    w, h = abs(x2 - x1), abs(y2 - y1)
    logger.info(f"截图区域: ({x}, {y}, {w}x{h})")

    img = pyautogui.screenshot(region=(x, y, w, h))
    img.save(str(save_path))
    file_size = Path(save_path).stat().st_size
    logger.info(f"模板已保存: {save_path} ({file_size} bytes)")
    print(f"Saved to {save_path}")
