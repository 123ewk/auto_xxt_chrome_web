"""OCR utilities: screen capture → text recognition → coordinate location."""

import time
from pathlib import Path
from typing import Sequence

import pyautogui
import pytesseract
from loguru import logger

import config

# Set tesseract executable path
pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD


def capture_and_ocr(
    region: tuple[int, int, int, int] | None = None,
    lang: str = "chi_sim+eng",
) -> list[dict]:
    """Capture a screen region and perform OCR to extract text with positions.

    Args:
        region: (x, y, w, h) screen region. None = full screen.
        lang: Tesseract language(s). Default chi_sim+eng for Chinese + English.

    Returns:
        List of dicts: [{"text": str, "conf": float, "x": int, "y": int, "w": int, "h": int}, ...]
        Empty list if no text found.
    """
    screenshot = pyautogui.screenshot(region=region)

    try:
        data = pytesseract.image_to_data(
            screenshot,
            lang=lang,
            output_type=pytesseract.Output.DICT,
        )
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return []

    results = []
    n = len(data["text"])
    for i in range(n):
        text = data["text"][i].strip()
        conf = int(data["conf"][i])
        if text and conf > 0:
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            # Adjust coordinates if region was specified
            if region:
                x += region[0]
                y += region[1]
            results.append({
                "text": text,
                "conf": conf / 100.0,
                "x": x,
                "y": y,
                "w": w,
                "h": h,
            })

    return results


def find_text(
    target: str,
    region: tuple[int, int, int, int] | None = None,
    exact: bool = False,
    min_conf: float = 0.6,
) -> dict | None:
    """Find a specific text on screen and return its position.

    Performs OCR on the screen, then searches for the target text.
    Uses substring matching by default, exact matching optional.

    Args:
        target: Text to search for (e.g. "下一节", "确定", "继续").
        region: Optional search region to speed up OCR.
        exact: If True, requires exact match. If False, substring match.
        min_conf: Minimum confidence threshold (0-1).

    Returns:
        Dict with "x", "y", "w", "h", "text", "conf" of the best match, or None.
    """
    results = capture_and_ocr(region=region)
    if not results:
        return None

    best = None
    for r in results:
        if r["conf"] < min_conf:
            continue
        if exact and r["text"] == target:
            if best is None or r["conf"] > best["conf"]:
                best = r
        elif not exact and target in r["text"]:
            if best is None or r["conf"] > best["conf"]:
                best = r

    if best:
        logger.debug(f"Found '{target}' → '{best['text']}' at ({best['x']}, {best['y']}) conf={best['conf']:.2f}")
    else:
        logger.debug(f"Text '{target}' not found on screen")

    return best


def find_any_text(
    targets: Sequence[str],
    region: tuple[int, int, int, int] | None = None,
    exact: bool = False,
    min_conf: float = 0.6,
) -> dict | None:
    """Find the first matching text from a list.

    Args:
        targets: List of text strings to search for (e.g. ["下一节", "继续", "下一个"]).
        region: Optional search region.
        exact: Exact match or substring.
        min_conf: Minimum confidence.

    Returns:
        Best match dict from any of the targets, or None.
    """
    best = None
    for t in targets:
        result = find_text(t, region=region, exact=exact, min_conf=min_conf)
        if result:
            if best is None or result["conf"] > best["conf"]:
                best = result
    return best


def find_all_instances(
    target: str,
    region: tuple[int, int, int, int] | None = None,
    min_conf: float = 0.6,
) -> list[dict]:
    """Find all occurrences of a text on screen.

    Args:
        target: Text to search for.
        region: Optional search region.
        min_conf: Minimum confidence.

    Returns:
        List of all matching dicts.
    """
    results = capture_and_ocr(region=region)
    matches = []
    for r in results:
        if r["conf"] >= min_conf and target in r["text"]:
            matches.append(r)
    return matches


def click_text(
    target: str,
    region: tuple[int, int, int, int] | None = None,
    exact: bool = False,
    min_conf: float = 0.6,
    retries: int = 3,
    retry_interval: float = 1.0,
) -> bool:
    """Find text on screen and click its center.

    Args:
        target: Text to find and click.
        region: Optional search region.
        exact: Exact match or substring.
        min_conf: Minimum confidence.
        retries: Number of retry attempts.
        retry_interval: Seconds between retries.

    Returns:
        True if text was found and clicked.
    """
    for attempt in range(1, retries + 1):
        result = find_text(target, region=region, exact=exact, min_conf=min_conf)
        if result:
            cx = result["x"] + result["w"] // 2
            cy = result["y"] + result["h"] // 2
            pyautogui.moveTo(cx, cy, duration=0.2)
            time.sleep(0.2)
            pyautogui.click()
            logger.info(f"Clicked '{target}' at ({cx}, {cy})")
            return True

        if attempt < retries:
            logger.debug(f"Attempt {attempt}/{retries}: '{target}' not found, retrying in {retry_interval}s")
            time.sleep(retry_interval)

    logger.warning(f"Failed to click '{target}' after {retries} attempts")
    return False


def wait_for_text(
    target: str,
    timeout: float = 30.0,
    interval: float = 1.0,
    region: tuple[int, int, int, int] | None = None,
    min_conf: float = 0.6,
) -> dict | None:
    """Wait for a text to appear on screen.

    Args:
        target: Text to wait for.
        timeout: Max wait time in seconds.
        interval: Check interval in seconds.
        region: Optional search region.
        min_conf: Minimum confidence.

    Returns:
        Match dict if found, None on timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = find_text(target, region=region, min_conf=min_conf)
        if result:
            logger.info(f"'{target}' appeared after {timeout - (deadline - time.time()):.1f}s")
            return result
        time.sleep(interval)
    logger.warning(f"Timeout waiting for '{target}' ({timeout}s)")
    return None


def ocr_status() -> dict:
    """Check if OCR engine is operational.

    Returns:
        Dict with keys: "available" (bool), "tesseract_path" (str), "languages" (list).
    """
    import subprocess

    result = {
        "available": False,
        "tesseract_path": config.TESSERACT_CMD,
        "languages": [],
    }

    try:
        output = subprocess.check_output(
            [config.TESSERACT_CMD, "--list-langs"],
            stderr=subprocess.STDOUT,
            text=True,
        )
        # Parse language list from output
        lines = output.strip().split("\n")
        result["languages"] = [l.strip() for l in lines if l.strip() and not l.startswith("List")]
        result["available"] = len(result["languages"]) > 0
    except Exception as e:
        logger.error(f"Tesseract check failed: {e}")

    return result
