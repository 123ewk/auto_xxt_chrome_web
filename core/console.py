"""Chrome DevTools console injection utilities.

Strategy for focusing the console:
1. Open DevTools with Ctrl+Shift+I
2. Click the Console tab position (top of DevTools panel)
3. Click the console input area (bottom of DevTools panel)
4. Type and execute JS
"""

import time

import pyautogui
from loguru import logger

import config

# DevTools opened state tracking
_devtools_open = False


def open_devtools():
    """Open Chrome DevTools via Ctrl+Shift+I."""
    global _devtools_open
    pyautogui.hotkey(*config.DEVTOOLS_HOTKEY)
    time.sleep(2.0)
    _devtools_open = True
    logger.info("DevTools 已打开")


def close_devtools():
    """Close Chrome DevTools via Ctrl+Shift+I."""
    global _devtools_open
    pyautogui.hotkey(*config.DEVTOOLS_HOTKEY)
    time.sleep(1.0)
    _devtools_open = False
    logger.info("DevTools 已关闭")


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


def _focus_console():
    """Focus the DevTools Console panel and its input area.

    Works by:
    1. Clicking the Console tab at the top of the DevTools panel area
    2. Clicking the console input at the bottom

    Assumes DevTools is docked to the bottom (most common layout).
    """
    screen_w, screen_h = pyautogui.size()

    # Estimate where DevTools panel starts from the bottom
    # DevTools docked to bottom usually occupies the bottom 35-40% of screen
    devtools_top_y = int(screen_h * 0.62)  # where DevTools panel starts
    tab_bar_y = devtools_top_y + 15         # roughly middle of tab bar

    # --- Step 1: Click the Console tab ---
    # Console tab is typically the 2nd tab after "Elements"
    # Position: ~150-250px from left edge, at the top of DevTools panel
    console_tab_x = 200
    console_tab_y = tab_bar_y

    logger.debug(f"点击 Console 标签页 ({console_tab_x}, {console_tab_y})")
    pyautogui.click(console_tab_x, console_tab_y)
    time.sleep(1.0)  # wait for panel switch

    # --- Step 2: Click the console input area ---
    # After switching to Console panel, the input area is at the bottom of panel
    input_y = screen_h - 50    # near bottom of screen
    input_x = screen_w // 2

    logger.debug(f"点击 Console 输入框 ({input_x}, {input_y})")
    pyautogui.click(input_x, input_y)
    time.sleep(0.5)

    logger.debug("Console 输入框已聚焦")


def _click_in_console_and_type(js_code: str):
    """Type JS code into the focused console input and execute.

    Args:
        js_code: JavaScript code to execute.
    """
    # Type the JS code with small delay between characters for reliability
    pyautogui.write(js_code, interval=0.05)
    time.sleep(0.3)
    # Execute
    pyautogui.press("enter")
    time.sleep(0.8)
    logger.debug(f"已执行 JS: {js_code[:60]}{'...' if len(js_code) > 60 else ''}")


def inject_js(js_code: str) -> None:
    """Inject and execute JavaScript via DevTools console.

    Opens DevTools, focuses the Console panel, types JS, and executes it.

    Args:
        js_code: JavaScript code to execute.
    """
    ensure_devtools(open_it=True)

    # Focus the Console panel and its input
    _focus_console()

    # Type and execute the JS code
    _click_in_console_and_type(js_code)


def execute_video_js(js_code: str, fallback_action: callable = None) -> bool:
    """Execute JS on a video element with fallback.

    Args:
        js_code: JavaScript to execute.
        fallback_action: Callable if injection fails.

    Returns:
        True if injection was attempted.
    """
    try:
        inject_js(js_code)
        time.sleep(1.0)
        return True
    except Exception as e:
        logger.error(f"JS 注入失败: {e}")
        if fallback_action:
            logger.info("执行备用方案...")
            fallback_action()
        return False


def _video_selector_js() -> str:
    """JavaScript snippet to find a video element with multiple selectors.

    Returns:
        JS code string that assigns the found video element to variable 'v'.
    """
    return (
        "var v=document.querySelector('video')"
        "||document.querySelector('video[class*=video]')"
        "||document.querySelector('.vjs-tech');"
    )


def set_video_speed(speed: float = 2.0) -> None:
    """Set video playback speed via DevTools console injection.

    Args:
        speed: Target playback speed (e.g., 2.0 for 2x).
    """
    js = (
        f"(function(){{"
        f"  {_video_selector_js()}"
        f"  if(v){{v.playbackRate={speed};console.log('Speed:'+v.playbackRate);}}"
        f"  else{{console.log('No video element');}}"
        f"}})()"
    )
    inject_js(js)


def mute_video() -> None:
    """Mute video via DevTools console injection."""
    js = (
        "(function(){"
        f"  {_video_selector_js()}"
        "  if(v){v.muted=true;console.log('Muted');}"
        "  else{console.log('No video for mute');}"
        "})()"
    )
    inject_js(js)


def click_play_button_if_paused() -> bool:
    """Call video.play() via DevTools if the video is paused.

    Returns:
        True if the play command was sent.
    """
    js = (
        "(function(){"
        f"  {_video_selector_js()}"
        "  if(v&&v.paused){v.play();console.log('Play');return true;}"
        "  return false;"
        "})()"
    )
    inject_js(js)
    return True
