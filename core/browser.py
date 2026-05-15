"""Playwright browser management — launch Chrome with full CDP control.

Strategy:
1. Copy user's Chrome profile to a temp directory (avoids lock)
2. Launch Chrome via Playwright (NOT subprocess) using the temp profile
3. Playwright has full CDP control → page.evaluate() never hangs
4. addInitScript injects video restriction bypass before any page scripts
"""

import os
import shutil
from pathlib import Path

from loguru import logger
from playwright.sync_api import sync_playwright, Page, BrowserContext

import config
from core.js_snippets import video_bypass_init_js


def _find_chrome_exe() -> str:
    """Find the system Chrome executable."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return "chrome"


def _user_data_dir() -> str:
    """Get Chrome user data directory."""
    if config.CHROME_PROFILE_DIR:
        return config.CHROME_PROFILE_DIR
    return os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")


def _copy_profile() -> str:
    """Copy user's Chrome profile to temp dir so Playwright can use it.

    Chrome locks the profile directory, so we copy essential login state
    to a temp directory that Playwright's Chrome can lock exclusively.

    Returns:
        Path to the temp profile directory.
    """
    user_data = _user_data_dir()
    tmp_profile = os.path.join(os.environ.get("TEMP", "."), "sua_ke_chrome_profile")

    # Clean previous temp profile
    if os.path.exists(tmp_profile):
        try:
            shutil.rmtree(tmp_profile, ignore_errors=True)
        except Exception:
            pass

    os.makedirs(tmp_profile, exist_ok=True)

    try:
        for subdir in ["Default", "Local State"]:
            src = os.path.join(user_data, subdir)
            dst = os.path.join(tmp_profile, subdir)
            if os.path.exists(src):
                try:
                    if os.path.isdir(src):
                        shutil.copytree(
                            src, dst,
                            ignore=shutil.ignore_patterns(
                                "Cache", "Code Cache", "GPUCache",
                                "Service Worker", "Session Storage",
                                "IndexedDB", "shared_proto_db",
                                "WebStorage", "File System",
                            ),
                        )
                    else:
                        shutil.copy2(src, dst)
                except Exception as e:
                    logger.warning(f"复制 {subdir} 失败: {e}")
    except Exception as e:
        logger.warning(f"复制 profile 时出错: {e}")

    return tmp_profile


# Global state
_pw = None
_context: BrowserContext | None = None
_page: Page | None = None


def get_page() -> Page:
    """Launch Chrome via Playwright with the user's profile.

    Playwright has FULL CDP control over the browser — page.evaluate()
    will never hang indefinitely (unlike connectOverCDP).

    The video restriction bypass is injected via addInitScript, which
    runs before every page's scripts (including all iframes).

    Returns:
        Playwright Page object.
    """
    global _pw, _context, _page

    if _page and not _page.is_closed():
        return _page

    # Tell user to close any existing Chrome (profile lock)
    print("\n请关闭所有 Chrome 窗口后按 Enter 继续...")
    input()

    tmp_profile = _copy_profile()

    _pw = sync_playwright().start()

    # Use channel="chrome" to launch the system-installed Chrome
    # This preserves codecs and extensions that 学习通 needs
    _context = _pw.chromium.launch_persistent_context(
        user_data_dir=tmp_profile,
        headless=False,
        executable_path=_find_chrome_exe(),
        args=[
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
        ],
        viewport=None,  # Use the full window
    )

    # --- Video restriction bypass ---
    # addInitScript runs in ALL pages and iframes BEFORE any page scripts
    bypass_js = video_bypass_init_js()
    _context.add_init_script(bypass_js)
    logger.info("视频限制绕过已注册 (addInitScript)")

    # Get the default page (Chrome opens one automatically)
    if _context.pages:
        _page = _context.pages[0]
    else:
        _page = _context.new_page()

    # Auto-dismiss any dialogs that would block page.evaluate()
    _page.on("dialog", lambda dialog: dialog.dismiss())

    logger.info(f"Chrome 已启动，页面就绪")
    return _page


def close_browser():
    """Clean up Playwright resources."""
    global _pw, _context, _page
    try:
        if _context:
            _context.close()
    except Exception:
        pass
    try:
        if _pw:
            _pw.stop()
    except Exception:
        pass
    _context = None
    _page = None
    _pw = None
    logger.info("浏览器已关闭")
