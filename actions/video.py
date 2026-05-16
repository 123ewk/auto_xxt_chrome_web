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
    video_diagnostic_js,
    video_ready_for_seek_js,
    auto_nav_js,
    quiz_handler_js,
    clear_nav_marker_js,
    video_progress_js,
    task_point_status_js,
    task_point_can_seek_js,
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
                # --- diagnostic: explain why detection returned 0 ---
                for frame in page.frames:
                    try:
                        diag = frame.evaluate(video_diagnostic_js())
                        if diag:
                            import json
                            d = json.loads(diag)
                            if d.get("rawVideos", 0) > 0 or d.get("hasVideoJS"):
                                logger.warning(
                                    f"[诊断] frame={frame.url[:80]} "
                                    f"rawVideos={d.get('rawVideos')} "
                                    f"hasVideoJS={d.get('hasVideoJS')} "
                                    f"filteredCount={d.get('filteredCount')} "
                                    f"videoIFrames={d.get('videoIFrames')} "
                                    f"details={d.get('rawVideoDetails')}"
                                )
                    except Exception:
                        pass
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
                if result == 0:
                    # Diagnostic: why did auto_nav find 0 videos?
                    try:
                        diag = frame.evaluate(video_diagnostic_js())
                        if diag:
                            import json
                            d = json.loads(diag)
                            logger.warning(
                                f"[注入诊断] frame={frame.url[:80]} "
                                f"rawVideos={d.get('rawVideos')} "
                                f"hasVideoJS={d.get('hasVideoJS')} "
                                f"filteredCount={d.get('filteredCount')} "
                                f"details={d.get('rawVideoDetails')}"
                            )
                    except Exception:
                        pass
            else:
                logger.warning(f"  frame 注入后 __videosTotal 未定义: {frame.url[:80]}")
        except Exception as e:
            logger.warning(f"  frame 注入失败: {frame.url[:60]} — {e}")
            # Diagnostic on injection failure
            try:
                diag = frame.evaluate(video_diagnostic_js())
                if diag:
                    import json
                    d = json.loads(diag)
                    if d.get("rawVideos", 0) > 0 or d.get("hasVideoJS"):
                        logger.warning(
                            f"[注入失败诊断] frame={frame.url[:80]} "
                            f"rawVideos={d.get('rawVideos')} "
                            f"hasVideoJS={d.get('hasVideoJS')} "
                            f"details={d.get('rawVideoDetails')}"
                        )
            except Exception:
                pass

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

    # Record the set of frame URLs at monitor start.  Navigation within the
    # 学习通 course page swaps iframe content WITHOUT changing the top-frame URL,
    # so we must track frame-level changes, not page.url.
    frame_urls_start = {f.url for f in page.frames}

    # Give auto-nav time to initialize in all frames
    time.sleep(2)

    # ---- Check seekability BEFORE the loop (not gated on task completion) ----
    # Read .task-condition text for "不可拖拽" to decide fast (seek) vs slow (2x) path.
    can_seek = False
    seekability_checked = False
    for frame in page.frames:
        try:
            info = frame.evaluate(task_point_can_seek_js())
            if info and info.get("total", 0) > 0:
                can_seek = info.get("draggable", False)
                all_blocked = info.get("allBlocked", False)
                logger.info(
                    f"任务点拖拽检测: draggable={can_seek} "
                    f"allBlocked={all_blocked} "
                    f"details={info.get('details')}"
                )
                seekability_checked = True
                break
        except Exception:
            pass
    if not seekability_checked:
        can_seek = False
        logger.info("任务点拖拽检测: 未找到 .task-condition，假定不可拖拽")

    # ---- Act on seekability immediately ----
    if can_seek:
        logger.info("视频可拖拽，等待元数据加载后 seek 到末尾...")
        video_ready = False
        for _ in range(20):  # max 20s wait for metadata
            ready = False
            for frame in page.frames:
                try:
                    if frame.evaluate(video_ready_for_seek_js()):
                        ready = True
                        break
                except Exception:
                    pass
            if ready:
                video_ready = True
                break
            time.sleep(1)
        if video_ready:
            logger.info("视频元数据已就绪，seek 到末尾...")
            for frame in page.frames:
                try:
                    frame.evaluate(seek_all_videos_to_end_js())
                except Exception:
                    pass
            time.sleep(2)
        else:
            logger.warning("视频元数据超时未加载，跳过 seek")
    else:
        logger.info("视频不可拖拽，等待 2x 自然播放结束...")

    logger.info("=== 监控视频进度 + 任务点检测 ===")

    while time.time() < deadline:
        if stop_event and stop_event.is_set():
            logger.info("收到停止信号")
            return False

        # Navigation may swap iframe content without changing the top-frame URL.
        # Compare the FULL set of frame URLs (not substring) — a new video
        # section will have the same iframe pattern but different video src.
        try:
            current_frame_urls = {f.url for f in page.frames}
            # Strip about:blank and empty URLs — they're noise
            old_significant = {u for u in frame_urls_start if u and u != 'about:blank'}
            new_significant = {u for u in current_frame_urls if u and u != 'about:blank'}
            if old_significant != new_significant:
                # Frame structure changed — navigation happened
                logger.info("Frame 结构已变化（导航成功），返回主循环重新检测")
                return True
        except Exception:
            pass

        # ---- Check task-point completion ----
        total_tasks = 0
        unfinished = 0
        for frame in page.frames:
            try:
                ts = frame.evaluate(task_point_status_js())
                t = ts.get("total", 0)
                u = ts.get("unfinished", 0)
                total_tasks += t
                unfinished += u
            except Exception:
                pass

        # Task points already done → navigate immediately
        if total_tasks > 0 and unfinished == 0:
            logger.info("任务点已完成，执行导航...")
            from actions.navigation import try_click_next_section
            nav_ok = try_click_next_section(page)
            if nav_ok:
                time.sleep(2)
                return True
            try:
                new_frames = {f.url for f in page.frames}
                old_sig = {u for u in frame_urls_start if u and u != 'about:blank'}
                new_sig = {u for u in new_frames if u and u != 'about:blank'}
                if old_sig != new_sig:
                    logger.info("Frame 结构已变化（导航成功），返回主循环重新检测")
                    time.sleep(2)
                    return True
            except Exception:
                pass
            logger.warning("导航被阻止（可能弹窗），继续等待...")

        # ---- Check video frame progress ----
        all_done = True
        total_videos = 0
        done_videos = 0
        paused_videos = 0

        for frame in page.frames:
            try:
                info = frame.evaluate(video_progress_js())
                t = info.get("total", 0)
                d = info.get("done", 0)
                p = info.get("paused", 0)
                total_videos += t
                done_videos += d
                paused_videos += p
                if t > 0 and d < t:
                    all_done = False
            except Exception:
                pass

        # Diagnostic: when all frames report 0 videos, check raw DOM state
        if total_videos == 0:
            for frame in page.frames:
                try:
                    diag = frame.evaluate(video_diagnostic_js())
                    if diag:
                        import json
                        d = json.loads(diag)
                        if d.get("rawVideos", 0) > 0 or d.get("hasVideoJS"):
                            logger.warning(
                                f"[视频进度诊断] frame={frame.url[:80]} "
                                f"rawVideos={d.get('rawVideos')} "
                                f"hasVideoJS={d.get('hasVideoJS')} "
                                f"filteredCount={d.get('filteredCount')} "
                                f"details={d.get('rawVideoDetails')}"
                            )
                except Exception:
                    pass

        # Log progress
        if time.time() - last_progress_log > 15:
            progress_msg = f"视频总进度: {done_videos}/{total_videos}"
            if paused_videos > 0:
                progress_msg += f" (暂停: {paused_videos})"
            logger.info(progress_msg)
            last_progress_log = time.time()

        # 有暂停的视频说明 seek 被拦截，不能算完成
        if paused_videos > 0:
            all_done = False

        if all_done and total_videos > 0:
            # Videos ended naturally — check task point
            # Require total_tasks > 0: avoid false positive from empty query result
            if total_tasks > 0 and unfinished == 0:
                logger.info("全部视频已结束且任务点已完成，执行导航...")
                from actions.navigation import try_click_next_section
                nav_ok = try_click_next_section(page)
                if nav_ok:
                    time.sleep(2)
                    return True
                # Check frame-level change (iframe content swap doesn't change page.url)
                try:
                    new_frames = {f.url for f in page.frames}
                    old_sig = {u for u in frame_urls_start if u and u != 'about:blank'}
                    new_sig = {u for u in new_frames if u and u != 'about:blank'}
                    if old_sig != new_sig:
                        logger.info("Frame 结构已变化（导航成功），返回主循环重新检测")
                        time.sleep(2)
                        return True
                except Exception:
                    pass
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
