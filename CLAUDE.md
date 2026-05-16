# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (first time)
pip install -r requirements.txt
playwright install chromium

# Run the automation
python main.py

# With custom speed and countdown
python main.py --speed 1.5 --countdown 10
```

No build step, linter, or test suite exists in this project.

## Environment setup

Copy `.env.example` to `.env` and fill in real values:

| Variable | Required | Purpose |
|---|---|---|
| `XXT_PHONE` | Cookie失效时必填 | 学习通账号 |
| `XXT_PASSWORD` | Cookie失效时必填 | 学习通密码 |
| `XXT_COURSE_URL` | Yes | 课程页面URL |
| `TESSERACT_CMD` | No | Tesseract path (default: `D:\Tesseract_OCR\tesseract.exe`) |

`.env` is loaded by `_load_dotenv()` in `main.py:29-46` — existing env vars take priority over `.env` values.

## Architecture (Playwright Edition)

The project controls Chrome via **Playwright** (`chromium.launch_persistent_context`), which launches Chrome with the user's profile. All interactions happen through `page.evaluate()` — no DevTools, no keyboard injection, no OCR, no mouse clicks.

**Core flow** (`main.py` loop):
1. Connect to Chrome via CDP (`core/browser.py` — auto-launches Chrome with `--remote-debugging-port=9222` + user profile)
2. Check if video exists on page → `page.evaluate(video_detection_js())` — returns bool directly
3. Play video, seek to end, inject auto-nav + quiz handler — all via `page.evaluate()`
4. Monitor progress: `page.waitForFunction("!!window.__autoNavDone")` — Playwright-native wait, no polling
5. After nav → next cycle

**Layer separation**:
- `core/browser.py` — Chrome CDP launch, Playwright connection, page management
- `core/js_snippets.py` — All JS logic as Python string functions (ported from old console.py)
- `core/ocr.py` — Tesseract OCR (kept only for `ocr_status()` preflight check, NOT used operationally)
- `actions/video.py` — Video detection, play, seek, auto-nav, quiz handler → all `page.evaluate()`
- `actions/navigation.py` — DOM-based next-section click, popup detection/click, PPT scrolling, completion check (`has_more_content`)
- `config.py` — CDP port, speed, timeouts
- `main.py` — CLI entry point, logging, main loop

## Key design decisions

- **No DevTools needed**: CDP connection is transparent to the page. The old approach of keeping DevTools open to avoid focus-loss detection is no longer needed.
- **No IME switching**: `page.evaluate()`executes JS in page context directly — no keyboard input involved.
- **No clipboard**: JS is delivered as strings to `page.evaluate()`, not pasted.
- **No coordinate clicking**: Everything is DOM-based via JS.
- **Auto-nav detection**: JS sets `window.__autoNavDone = true` on success. Playwright's `page.waitForFunction("!!window.__autoNavDone")` waits for it natively (no title polling).
- **Seek detection**: `seek_to_end_js()` returns a Promise; `page.evaluate()` awaits it and returns True/False.
- **Chrome profile**: Script copies the user's Chrome profile to a temp directory to preserve 学习通 login state without locking the main profile.
- **Auto-login**: If cookie-based login is expired, script detects the login page and auto-fills `XXT_PHONE`/`XXT_PASSWORD` from `.env` (see `main.py:132-153`).
- **Emergency stop**: Ctrl+C in terminal.

## JS snippets (core/js_snippets.py)

All JS functions return Python strings ready for `page.evaluate()`:

| Function | Returns | Purpose |
|---|---|---|
| `video_bypass_init_js()` | void | **addInitScript** — intercept `currentTime`/`playbackRate` setters + block restriction listeners |
| `video_detection_js()` | bool | Check if `<video>` exists in document/iframes |
| `video_progress_js()` | dict | Return `{total, done, paused}` across frames |
| `task_point_status_js()` | dict | Check `.ans-job-icon` aria-label for `{total, unfinished}` |
| `play_video_js()` | bool | Play video if paused |
| `mute_video_js()` | bool | Mute video |
| `set_speed_js(speed)` | bool | Set `playbackRate` |
| `seek_to_end_js()` | Promise→bool | Seek to `duration-2`; resolves after 2s |
| `seek_all_videos_to_end_js()` | int | Seek ALL videos to end (used when task points complete early) |
| `retry_video_high_speed_js()` | int | Replay ended videos at 16x to accumulate watch time |
| `auto_nav_js(speed)` | void | Play ALL videos, mute + set speed, install `ended` listeners → set `__autoNavDone` |
| `quiz_handler_js()` | void | Event-driven quiz auto-answer (pause listener + MutationObserver + 1.5s poll) |
| `navigate_next_js()` | void | DOM-search 下一节 button, handle task-unfinished popup, retry, set `__autoNavDone` |
| `clear_nav_marker_js()` | void | Clear stale `sessionStorage.__autoNavDone` and window flag |
| `check_nav_marker_js()` | str | Expression for `waitForFunction()` — checks `__autoNavDone` OR `__autoNavFailedReason` |
| `detect_popup_js()` | dict | Detect position:fixed popups with "任务点未完" text → `{found, hasNextChapter}` |
| `scroll_to_bottom_js()` | int | Scroll PPT (panView frame `documentElement` or `.fileBox`) to bottom — NO wheel events |
| `scroll_ppt_gradually_js()` | Promise→int | Gradual scrollTop increments (200px/80ms) — simulates natural scroll without wheel events |

Key: `scroll_ppt_gradually_js` and `scroll_to_bottom_js` MUST only scroll `documentElement` in panView iframes (`pan-yz.chaoxing.com`). Scrolling the main frame's `documentElement` would move the entire page instead of PPT content.

## Dependencies

- `playwright` — Browser automation via CDP (installed via pip, connects to system Chrome)
- `loguru` — Structured logging to stderr + `logs/session.log`
- `pytesseract` + `pyautogui` — Only for preflight Tesseract check (not in operational flow)
