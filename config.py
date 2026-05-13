"""Global configuration for the auto-learning script."""

from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent
LOGS_DIR = BASE_DIR / "logs"

# Tesseract OCR
TESSERACT_CMD = r"D:\Tesseract_OCR\tesseract.exe"
OCR_LANG = "chi_sim+eng"       # Chinese simplified + English
OCR_MIN_CONF = 0.6             # minimum confidence for OCR matches (0-1)

# PyAutoGUI settings
PYAUTOGUI_FAILSAFE = False     # disabled — we use Ctrl+C or explicit stop
PYAUTOGUI_PAUSE = 0.5          # seconds between pyautogui calls

# Video monitoring
VIDEO_CHECK_INTERVAL = 5       # seconds between video state checks
VIDEO_FINISH_TIMEOUT = 600     # max seconds waiting for a video to finish (10 min)
SPEED_DEFAULT = 2.0            # target playback speed
SPEED_RETRY_COUNT = 1          # retries before falling back to 1x
SPEED_RETRY_INTERVAL = 3       # seconds to wait before speed retry

# Navigation — OCR search texts
NEXT_SECTION_TEXTS = ["下一节", "下一个", "继续"]
BACK_TO_COURSE_TEXTS = ["返回课程", "返回"]
CONTINUE_TEXTS = ["继续", "下一步"]

# Popup detection (OCR)
POPUP_CHECK_INTERVAL = 2       # seconds between popup checks
POPUP_CONFIRM_TEXTS = ["确定", "确认", "知道了", "OK"]
POPUP_CANCEL_TEXTS = ["取消", "关闭"]
POPUP_CLOSE_TEXTS = ["×", "✕"]

# Quiz handling
QUIZ_OPTION_TEXTS = ["A", "B", "C", "D"]
QUIZ_CONFIRM_TEXTS = ["提交", "确定"]

# Chrome DevTools hotkey (Windows)
DEVTOOLS_HOTKEY = ["ctrl", "shift", "i"]

# Logging
LOG_FILE = LOGS_DIR / "session.log"
SECTION_CHECK_INTERVAL = 3      # seconds between section-change checks
START_COUNTDOWN = 5              # seconds to wait before starting automation

LOG_ROTATION = "10 MB"
