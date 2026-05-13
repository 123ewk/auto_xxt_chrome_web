"""Chrome DevTools console injection utilities.

Strategy:
1. Open DevTools with Ctrl+Shift+I
2. Click the Console panel area (right-middle of DevTools)
3. Paste JS code via clipboard (Ctrl+V) — avoids IME/keyboard issues
4. Press Enter to execute
"""

import time

import pyautogui
import pyperclip
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
    """Ensure DevTools is in the desired state."""
    global _devtools_open
    if open_it and not _devtools_open:
        open_devtools()
    elif not open_it and _devtools_open:
        close_devtools()


def _switch_to_english_ime():
    """Try to switch to English input method to avoid IME interference.

    Attempts multiple methods:
    1. Win+Space (Windows 10/11 IME switcher)
    2. Alt+Shift (legacy IME switcher)
    3. Ctrl+Space (IME toggle)
    """
    try:
        # Try Win+Space first (most reliable on Win10/11)
        pyautogui.hotkey("win", "space")
        time.sleep(0.5)
        # Press space again to select English if the menu opened
        pyautogui.press("space")
        time.sleep(0.3)
    except Exception:
        pass


def _focus_console():
    """Focus the DevTools Console panel and its input area.

    Clicks the right-middle area of the DevTools panel where
    the console input prompt is typically located.
    """
    screen_w, screen_h = pyautogui.size()

    # Click the right-middle area of the DevTools panel
    # where the console input prompt (>) appears
    input_x = int(screen_w * 0.85)
    input_y = screen_h - 600

    logger.debug(f"聚焦 Console 输入框 ({input_x}, {input_y})")
    pyautogui.click(input_x, input_y)
    time.sleep(0.5)


def _paste_and_execute(js_code: str):
    """Copy JS to clipboard and paste into the focused console input.

    This avoids all keyboard layout / IME issues from typing characters
    one by one.

    Args:
        js_code: JavaScript code to execute.
    """
    # Copy to clipboard
    pyperclip.copy(js_code)
    time.sleep(0.2)

    # Paste into console (Ctrl+V)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)

    # Execute
    pyautogui.press("enter")
    time.sleep(0.8)

    logger.debug(f"已粘贴并执行 JS ({len(js_code)} chars)")


def inject_js(js_code: str) -> None:
    """Inject and execute JavaScript via DevTools console.

    Opens DevTools, focuses the Console input, pastes JS code
    from clipboard, and executes it.

    Args:
        js_code: JavaScript code to execute.
    """
    ensure_devtools(open_it=True)

    # Switch to English IME to avoid interference
    _switch_to_english_ime()

    # Focus the Console input area
    _focus_console()

    # Paste and execute
    _paste_and_execute(js_code)


def execute_video_js(js_code: str, fallback_action: callable = None) -> bool:
    """Execute JS on a video element with fallback."""
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


def _video_find_js() -> str:
    """JS snippet to find a video element, including inside iframes.

    Returns:
        JS expression that evaluates to a video element or null.
    """
    return (
        "(function(){"
        "var v=document.querySelector('video')"
        "||document.querySelector('video[class*=video]')"
        "||document.querySelector('.vjs-tech');"
        "if(!v){"
        "var f=document.querySelectorAll('iframe');"
        "for(var i=0;i<f.length;i++){"
        "try{v=f[i].contentDocument.querySelector('video');if(v)break}catch(e){}"
        "}"
        "}"
        "return v;"
        "})()"
    )


def set_video_speed(speed: float = 2.0) -> None:
    """Set video playback speed via DevTools console injection.

    Tries main document first, then searches inside iframes.
    """
    js = (
        f"(function(){{"
        f"var v={_video_find_js()};"
        f"if(v){{v.playbackRate={speed};console.log('Speed:'+v.playbackRate);}}"
        f"else{{console.log('No video element');}}"
        f"}})()"
    )
    inject_js(js)


def mute_video() -> None:
    """Mute video via DevTools console injection."""
    js = (
        "(function(){"
        f"var v={_video_find_js()};"
        "if(v){v.muted=true;console.log('Muted');}"
        "else{console.log('No video for mute');}"
        "})()"
    )
    inject_js(js)


def click_play_button_if_paused() -> bool:
    """Call video.play() via DevTools if video exists and is paused.

    Searches main document and iframes for the video element.

    Returns:
        True if play command was sent.
    """
    js = (
        "(function(){"
        f"var v={_video_find_js()};"
        "if(v&&v.paused){v.play();console.log('Play');return true;}"
        "console.log('No paused video found');"
        "return false;"
        "})()"
    )
    inject_js(js)
    return True
