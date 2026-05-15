"""Video detection, playback control and progress monitoring.

All video control is done through page.evaluate() — no DevTools,
no keyboard injection, no IME issues.

Multi-video support: auto_nav_js handles ALL videos on the page.
Plays each one, tries seek on each, applies 2x speed if blocked.
Only navigates to next section when ALL videos have ended.
"""

import time

from loguru import logger
from playwright.sync_api import Page

import config
from core.js_snippets import (
    video_detection_js,
    auto_nav_js,
    quiz_handler_js,
    clear_nav_marker_js,
    video_progress_js,
    task_point_status_js,
    retry_video_high_speed_js,
    seek_all_videos_to_end_js,
)


def ensure_video_present(page: Page) -> int:
    """Check if video elements exist on the current page.

    Args:
        page: Playwright Page object.

    Returns:
        Number of video elements found (0 = no videos).
    """
    logger.info("检测页面是否有视频...")

    # Wait for page and all iframes to finish loading
    try:
        page.wait_for_load_state("networkidle", timeout=30_000)
    except Exception:
        logger.warning("页面未完全加载，继续尝试...")

    # Retry up to 3 times (execution context can be destroyed during iframe loads)
    for attempt in range(3):
        try:
            count = page.evaluate(video_detection_js())
            if count > 0:
                logger.info(f"检测到 {count} 个视频元素")
            else:
                logger.warning("当前页面没有视频，跳过播放")
            return count
        except Exception as e:
            if attempt < 2:
                logger.warning(f"视频检测重试 {attempt + 1}/3: {e}")
                time.sleep(3)
            else:
                logger.error(f"视频检测失败: {e}")
                return 0

    return 0


def play_current_video(page: Page) -> bool:
    """Play ALL videos on the current page and set up auto-navigation.

    Injects bypass + auto_nav + quiz_handler into the main frame
    AND ALL iframe frames (including cross-origin). Playwright CDP
    gives us access to cross-origin frames that normal JS can't reach.

    Args:
        page: Playwright Page object.

    Returns:
        True if operations were executed.
    """
    logger.info("=== 处理视频（多视频模式）===")

    # Gather all frames (main + all iframes, including cross-origin)
    all_frames = page.frames
    logger.info(f"共 {len(all_frames)} 个 frame")

    # Log frame URLs for diagnosis
    for i, f in enumerate(all_frames):
        logger.info(f"  frame[{i}]: {f.url[:100]}")

    # Step 0: Clear stale nav marker in all frames
    for frame in all_frames:
        try:
            frame.evaluate(clear_nav_marker_js())
        except Exception as e:
            logger.warning(f"清除标记失败 frame={frame.url[:60]}: {e}")

    # Step 1: Inject auto-nav into ALL frames
    injected_count = 0
    for frame in all_frames:
        try:
            frame.evaluate(auto_nav_js(config.SPEED_DEFAULT))
            # Check if injection took effect
            result = frame.evaluate("window.__videosTotal")
            if result is not None:
                injected_count += 1
                logger.info(f"  frame 注入成功, 视频数={result}: {frame.url[:80]}")
            else:
                logger.warning(f"  frame 注入后 __videosTotal 未定义: {frame.url[:80]}")
        except Exception as e:
            logger.warning(f"  frame 注入失败: {frame.url[:60]} — {e}")

    # Step 2: Inject quiz handler into ALL frames
    for frame in all_frames:
        try:
            frame.evaluate(quiz_handler_js())
        except Exception as e:
            logger.warning(f"quiz 注入失败 frame={frame.url[:60]}: {e}")

    logger.info(f"auto_nav 已注入 {injected_count}/{len(all_frames)} 个 frame")
    return True


def monitor_video_progress(page: Page, stop_event=None) -> bool:
    """Wait for ALL videos to finish OR for task points to complete.

    Two-phase logic:
    1. While videos are playing, check task-point status in the loop.
       If task points complete early (aria-label → "任务点已完成"), seek all
       videos to end immediately → no need to wait for natural ended.
    2. After all videos ended (natural or forced), if task points are done,
       navigate. If task points still unfinished, start 16x retry replay.

    Args:
        page: Playwright Page object.
        stop_event: Optional threading.Event.

    Returns:
        True if all videos + task points finished and navigation triggered.
    """
    deadline = time.time() + config.VIDEO_FINISH_TIMEOUT
    last_progress_log = 0
    retry_injected = False

    # Give auto-nav time to initialize in all frames
    time.sleep(5)

    logger.info("=== 监控视频进度 + 任务点检测（16x 连续播放模式）===")

    while time.time() < deadline:
        if stop_event and stop_event.is_set():
            logger.info("收到停止信号")
            return False

        # ---- Check task-point completion early (during playback) ----
        try:
            task_status = page.evaluate(task_point_status_js())
            unfinished = task_status.get("unfinished", 0)
            total_tasks = task_status.get("total", 0)
        except Exception:
            unfinished = total_tasks = 0

        # If task points are done BEFORE all videos naturally ended
        if unfinished == 0:
            logger.info("任务点已完成！立即终止视频播放...")
            # Seek all videos to end in all frames
            for frame in page.frames:
                try:
                    frame.evaluate(seek_all_videos_to_end_js())
                except Exception:
                    pass
            time.sleep(1)

            # Now navigate
            logger.info("任务点已完成，执行导航...")
            from actions.navigation import try_click_next_section
            nav_ok = try_click_next_section(page)
            if nav_ok:
                time.sleep(2)
                return True
            else:
                logger.warning("导航被阻止（可能弹窗），继续等待...")

        # ---- Check video frame progress ----
        all_done = True
        total_videos = 0
        done_videos = 0

        for frame in page.frames:
            try:
                info = frame.evaluate(video_progress_js())
                t = info.get("total", 0)
                d = info.get("done", 0)
                total_videos += t
                done_videos += d
                if t > 0 and d < t:
                    all_done = False
                    break
            except Exception:
                pass

        # Log progress
        if time.time() - last_progress_log > 15:
            logger.info(f"视频总进度: {done_videos}/{total_videos}")
            last_progress_log = time.time()

        if all_done and total_videos > 0:
            # Videos ended naturally — check task point
            if unfinished == 0:
                logger.info("全部视频已结束且任务点已完成，执行导航...")
                from actions.navigation import try_click_next_section
                nav_ok = try_click_next_section(page)
                if nav_ok:
                    time.sleep(2)
                    return True
                logger.warning("导航被阻止，继续重试...")
            else:
                if not retry_injected:
                    logger.warning(
                        f"视频已结束但 {unfinished} 个任务点未完成，启动 16x 高速重放..."
                    )
                    for frame in page.frames:
                        try:
                            frame.evaluate(retry_video_high_speed_js())
                        except Exception as e:
                            logger.warning(f"高速重放注入失败: {e}")
                    retry_injected = True
                else:
                    logger.info(f"等待任务点完成... 剩余未完成: {unfinished}")

        time.sleep(config.VIDEO_CHECK_INTERVAL)

    logger.warning(f"视频监控超时 ({config.VIDEO_FINISH_TIMEOUT}s)")
    return False
