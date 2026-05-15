# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the automation
python main.py

# With custom speed and countdown
python main.py --speed 1.5 --countdown 10
```

No build step, linter, or test suite exists in this project.

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
- `actions/navigation.py` — DOM-based next-section click → `page.evaluate()` + `waitForFunction()`
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
- **Emergency stop**: Ctrl+C in terminal.

## JS snippets (core/js_snippets.py)

All JS functions return Python strings ready for `page.evaluate()`:

| Function | Returns | Purpose |
|---|---|---|
| `video_detection_js()` | bool | Check if `<video>` exists in document/iframes |
| `play_video_js()` | bool | Play video if paused |
| `mute_video_js()` | bool | Mute video |
| `set_speed_js(speed)` | bool | Set `playbackRate` |
| `seek_to_end_js()` | Promise→bool | Seek to `duration-2`; resolves after 2s |
| `auto_nav_js()` | void | Install `ended` listener + MutationObserver → click 下一节 |
| `quiz_handler_js()` | void | Install 2s-interval quiz auto-answer (single + multi-choice) |
| `navigate_next_js()` | void | DOM-search 下一节 button, retry 10x, set `__autoNavDone` |
| `clear_nav_marker_js()` | void | Clear stale `sessionStorage.__autoNavDone` and window flag |
| `check_nav_marker_js()` | str | Expression `!!window.__autoNavDone` for `waitForFunction()` |

## Dependencies

- `playwright` — Browser automation via CDP (installed via pip, connects to system Chrome)
- `loguru` — Structured logging to stderr + `logs/session.log`
- `pytesseract` + `pyautogui` — Only for preflight Tesseract check (not in operational flow)
