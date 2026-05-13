"""Global configuration for the auto-learning script."""

from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
LOGS_DIR = BASE_DIR / "logs"

# PyAutoGUI settings
# Fail-safe: move mouse to top-left corner to abort
PYAUTOGUI_FAILSAFE = True
PYAUTOGUI_PAUSE = 0.5  # second between pyautogui calls

# Screenshot / template matching
CONFIDENCE = 0.8         # default confidence for locateOnScreen
GRAYSCALE = True         # use grayscale for faster matching
SCREENSHOT_INTERVAL = 2  # seconds between screenshot checks

# Video monitoring
VIDEO_CHECK_INTERVAL = 5      # seconds between video state checks
VIDEO_FINISH_TIMEOUT = 600     # max seconds waiting for a video to finish (10 min)
SPEED_DEFAULT = 2.0            # target playback speed
SPEED_RETRY_COUNT = 1          # retries before falling back to 1x
SPEED_RETRY_INTERVAL = 3       # seconds to wait before speed retry

# Navigation
NEXT_SECTION_KEYWORDS = ["下一节", "下一个", "继续"]
SECTION_CHECK_INTERVAL = 3     # seconds between section-change checks

# Popup detection
POPUP_CHECK_INTERVAL = 2       # seconds between popup checks
POPUP_REGION_RATIO = 0.15      # top portion of screen to scan for popups

# Logging
LOG_FILE = LOGS_DIR / "session.log"
LOG_ROTATION = "10 MB"

# Chrome DevTools hotkey (Windows)
DEVTOOLS_HOTKEY = ["ctrl", "shift", "i"]
