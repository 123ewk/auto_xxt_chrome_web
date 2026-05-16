"""Global configuration for the auto-learning script (Playwright edition)."""

import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent
LOGS_DIR = BASE_DIR / "logs"

# Tesseract OCR (preflight check only, not used in operational flow)
# 可通过环境变量 TESSERACT_CMD 覆盖
TESSERACT_CMD = os.environ.get("TESSERACT_CMD", r"D:\Tesseract_OCR\tesseract.exe")

# Chrome profile — None = auto-detect Windows default
CHROME_PROFILE_DIR = None

# Course URL — 要刷的课程页面链接
# 优先读取环境变量 XXT_COURSE_URL，否则使用下方默认值
# 获取方式：在学习通网页端打开课程 → 复制浏览器地址栏 URL
# 例如: https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=xxx&courseId=xxx&...
COURSE_URL = os.environ.get("XXT_COURSE_URL", "")

# Video monitoring
VIDEO_CHECK_INTERVAL = 2       # seconds between video state checks
VIDEO_FINISH_TIMEOUT = 7200    # max seconds waiting for a video to finish (2h)
SPEED_DEFAULT = 2.0            # target playback speed

# Navigation
SECTION_CHECK_INTERVAL = 1     # seconds between section-change checks

# Logging
LOG_FILE = LOGS_DIR / "session.log"
START_COUNTDOWN = 10           # seconds to wait before starting automation
LOG_ROTATION = "10 MB"
