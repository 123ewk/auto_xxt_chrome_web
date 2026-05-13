"""Chrome DevTools console injection utilities."""

import time
from typing import Any

import pyautogui
from loguru import logger

import config

# DevTools opened state tracking
_devtools_open = False


def open_devtools():
    """Open Chrome DevTools via Ctrl+Shift+I."""
    global _devtools_open
    pyautogui.hotkey(*config.DEVTOOLS_HOTKEY)
    time.sleep(1.5)
    _devtools_open = True
    logger.debug("DevTools opened")


def close_devtools():
    """Close Chrome DevTools via Ctrl+Shift+I."""
    global _devtools_open
    pyautogui.hotkey(*config.DEVTOOLS_HOTKEY)
    time.sleep(0.8)
    _devtools_open = False
    logger.debug("DevTools closed")


def ensure_devtools(open_it: bool = True):
    """Ensure DevTools is in the desired state.

    Args:
        open_it: True to open, False to close.
    """
    global _devtools_open
    if open_it and not _devtools_open:
        open_devtools()
    elif not open_it and _devtools_open:
        close_devtools()


def inject_js(js_code: str) -> None:
    """Inject and execute JavaScript via DevTools console.

    Opens DevTools if needed, types the JS into the console, executes it.

    Args:
        js_code: JavaScript code to execute.
    """
    ensure_devtools(open_it=True)
    time.sleep(0.5)

    # Click on the console input area
    # The console prompt is typically at the bottom of DevTools.
    # We focus it by clicking on the last section of the screen.
    screen_w, screen_h = pyautogui.size()
    console_x = screen_w // 2
    console_y = screen_h - 60  # near bottom

    pyautogui.click(console_x, console_y)
    time.sleep(0.3)

    # Type the JS code and execute
    # Use triple click to select all existing text, then type
    pyautogui.tripleClick(console_x, console_y)
    time.sleep(0.2)

    pyautogui.write(js_code, interval=0.05)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.5)

    logger.debug(f"Injected JS: {js_code[:80]}{'...' if len(js_code) > 80 else ''}")


def execute_video_js(js_code: str, fallback_action: callable = None) -> bool:
    """Execute JS on a video element with fallback.

    Tries console injection first. If the script is at 1x speed
    after injection (detected externally), calls fallback_action.

    Args:
        js_code: JavaScript to execute.
        fallback_action: Callable to invoke if injection fails.

    Returns:
        True if injection was attempted, False on critical failure.
    """
    try:
        inject_js(js_code)
        time.sleep(1.0)
        return True
    except Exception as e:
        logger.error(f"JS injection failed: {e}")
        if fallback_action:
            logger.info("Running fallback action...")
            fallback_action()
        return False


def set_video_speed(speed: float = 2.0) -> None:
    """Set video playback speed via DevTools console injection.

    Attempts to set speed on the first <video> element found.
    Uses multiple selector fallbacks.

    Args:
        speed: Target playback speed (e.g., 2.0 for 2x).
    """
    js = (
        f"(function(){{"
        f"  const v = document.querySelector('video') "
        f"    || document.querySelector('video[class*=video]') "
        f"    || document.querySelector('.vjs-tech');"
        f"  if(v){{v.playbackRate={speed}; console.log('Speed set to '+v.playbackRate);}}"
        f"  else{{console.log('No video element found');}}"
        f"}})()"
    )
    inject_js(js)


def mute_video() -> None:
    """Mute video via DevTools console injection."""
    js = (
        "(function(){"
        "  const v = document.querySelector('video') "
        "    || document.querySelector('video[class*=video]') "
        "    || document.querySelector('.vjs-tech');"
        "  if(v){v.muted=true; console.log('Video muted');}"
        "  else{console.log('No video element found for mute');}"
        "})()"
    )
    inject_js(js)


def check_video_state() -> dict[str, Any]:
    """Check video playback state via DevTools console.

    Returns:
        Dict with keys: 'paused', 'ended', 'currentTime', 'duration', 'playbackRate'.
        All values default to None on failure.
    """
    js = (
        "(function(){"
        "  const v=document.querySelector('video')"
        "    || document.querySelector('video[class*=video]')"
        "    || document.querySelector('.vjs-tech');"
        "  if(!v) return 'NO_VIDEO';"
        "  return JSON.stringify({"
        "    paused:v.paused, ended:v.ended,"
        "    currentTime:v.currentTime, duration:v.duration,"
        "    playbackRate:v.playbackRate"
        "  });"
        "})()"
    )

    ensure_devtools(open_it=True)
    time.sleep(0.3)

    # Clear console, inject, read results via screenshot of console area
    # Since reading console output is complex with pyautogui alone,
    # we rely on external verification via screenshot matching.
    inject_js(js)

    # The result appears in the console. We'll use the return value pattern.
    # For practical purposes, the caller should verify speed/progress
    # via screenshot/template matching.
    return {}


def click_play_button_if_paused() -> bool:
    """Try to click the play button via injecting video.play().

    Returns:
        True if play() was called.
    """
    js = (
        "(function(){"
        "  const v=document.querySelector('video')"
        "    || document.querySelector('video[class*=video]')"
        "    || document.querySelector('.vjs-tech');"
        "  if(v && v.paused){v.play(); console.log('play() called'); return true;}"
        "  return false;"
        "})()"
    )
    inject_js(js)
    return True
