#!/usr/bin/env python
"""
sua_ke — 学习通自动刷课脚本 (Playwright 版)

通过 Chrome DevTools Protocol (CDP) 控制浏览器，直接执行 JS，
无需 DevTools 键盘注入、无需 OCR、无需鼠标点击固定坐标。

Usage:
    python main.py                    # 正常模式
    python main.py --speed 1.5        # 1.5 倍速

操作流程:
    1. 关闭所有 Chrome 窗口
    2. 运行本脚本（脚本自动启动 Chrome + 打开课程页面）
    3. 手动登录学习通并切换到有视频的章节
    4. 脚本自动执行后续操作
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))


def _load_dotenv():
    """从项目根目录的 .env 文件加载环境变量（不覆盖已存在的变量）。"""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # 不覆盖已存在的环境变量（命令行设置的优先级更高）
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

from loguru import logger

import config
from core.browser import get_page, close_browser
from core.ocr import ocr_status
from actions.video import ensure_video_present, play_current_video, monitor_video_progress
from core.js_snippets import scroll_to_bottom_js
from actions.navigation import (
    try_click_next_section,
    has_more_content,
    scroll_ppt_container,
    click_popup_next_chapter,
    detect_popup,
)


def setup_logging():
    """Configure loguru logging."""
    config.LOGS_DIR.mkdir(exist_ok=True)
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level:7}</level> | {message}",
    )
    logger.add(
        config.LOG_FILE,
        rotation=config.LOG_ROTATION,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:7} | {name}:{line} | {message}",
    )
    logger.info("日志初始化完成")


def preflight_check() -> bool:
    """Run preflight checks before starting automation.

    With Playwright, the only external dependency is:
    - Tesseract OCR engine (for verifying pre-installation)

    Returns:
        True if all checks pass.
    """
    status = ocr_status()
    if not status["available"]:
        logger.error("Tesseract OCR 不可用！请检查安装。")
        print("\n错误: Tesseract OCR 未正确配置。")
        print(f"  配置路径: {status['tesseract_path']}")
        return False

    if "chi_sim" not in status["languages"]:
        logger.error("缺少中文语言包 (chi_sim)")
        print("\n错误: Tesseract 缺少中文语言包 (chi_sim)。")
        return False

    logger.info(f"OCR 引擎: {status['tesseract_path']}")
    logger.info(f"语言包: {status['languages']}")

    return True


def main_loop(stop_event=None):
    """Main automation loop — Playwright edition.

    1. Connect to Chrome via CDP
    2. Per cycle: check video → play → monitor → navigate → repeat

    Args:
        stop_event: Optional threading.Event for external stop.
    """
    logger.info("=== sua_ke Playwright 自动化开始 ===")
    logger.info(f"目标速度: {config.SPEED_DEFAULT}x")

    # Launch Chrome via Playwright
    page = get_page()

    # Auto-navigate to 学习通 (cookies from profile = auto-login)
    print("\n=== 正在导航到学习通 ===")
    page.goto("https://passport2.chaoxing.com/login?fid=&newversion=true&refer=https%3A%2F%2Fi.chaoxing.com")
    page.wait_for_load_state("domcontentloaded", timeout=10_000)

    # Check if login page appeared (cookie login might have failed)
    # If we see the phone input, auto-fill credentials
    try:
        phone_input = page.locator('input[type="text"], input[placeholder*="手机"], input[placeholder*="账号"]').first
        phone_input.wait_for(state="visible", timeout=3000)
        logger.info("检测到登录页面，自动填写账号密码...")

        phone_input.fill(os.environ.get("XXT_PHONE", ""))
        time.sleep(0.3)

        pwd_input = page.locator('input[type="password"]').first
        pwd_input.fill(os.environ.get("XXT_PASSWORD", ""))
        time.sleep(0.3)

        login_btn = page.locator('button:has-text("登录"), .btn-login, input[value*="登录"]').first
        login_btn.click()
        logger.info("已点击登录")

        page.wait_for_load_state("domcontentloaded", timeout=15_000)
        time.sleep(2)
    except Exception:
        logger.info("Cookie 登录有效，已跳过登录页")

    # Navigate to course URL if configured
    if config.COURSE_URL:
        logger.info(f"跳转到课程页面: {config.COURSE_URL}")
        page.goto(config.COURSE_URL, wait_until="domcontentloaded", timeout=30_000)
        # Give iframes and async content time to load
        time.sleep(5)

    # Forward browser console logs to Python logger (for diagnosing JS issues)
    page.on("console", lambda msg: logger.info(f"[BROWSER:{msg.type}] {msg.text}"))

    print(f"倒计时 {config.START_COUNTDOWN} 秒后开始... (Ctrl+C 中止)")
    for i in range(config.START_COUNTDOWN, 0, -1):
        print(f"  {i}...")
        time.sleep(1)

    cycle_count = 0

    while not (stop_event and stop_event.is_set()):
        cycle_count += 1
        url_at_cycle_start = page.url
        logger.info(f"--- 第 {cycle_count} 轮循环 ---")

        # 1. Check if video exists on page (returns count)
        video_count = 0
        try:
            video_count = ensure_video_present(page)
        except Exception as e:
            logger.error(f"视频检测出错: {e}")

        if video_count == 0:
            logger.info("无视频（可能是图片/文档页面），滚动 PPT 容器再跳转下一节")
            # 使用改进的 PPT 容器滚动（wheel 事件 + nicescroll API）
            try:
                scrolled = scroll_ppt_container(page)
                if not scrolled:
                    logger.warning("未找到 .fileBox 容器，尝试通用滚动")
                    for f in page.frames:
                        try:
                            f.evaluate(scroll_to_bottom_js())
                        except Exception:
                            pass
                time.sleep(1.5)
            except Exception as e:
                logger.warning(f"页面滚动失败: {e}")

            # 检测并处理弹窗（滚动后可能触发「任务点未完成」弹窗）
            popup = detect_popup(page)
            if popup.get("found") and popup.get("hasNextChapter"):
                logger.info("滚动后检测到弹窗，点击「下一节」...")
                if click_popup_next_chapter(page):
                    time.sleep(2)
                    if page.url != url_at_cycle_start:
                        logger.info("弹窗点击后页面已跳转，进入下一轮")
                        time.sleep(config.SECTION_CHECK_INTERVAL)
                        continue

            try:
                if try_click_next_section(page):
                    logger.info("DOM 导航成功，进入下一轮")
                else:
                    logger.warning("DOM 导航失败：找不到导航按钮")
            except Exception as e:
                logger.error(f"导航出错: {e}")

            time.sleep(config.SECTION_CHECK_INTERVAL)
            continue

        # 2. Play all videos on this page + inject auto-nav + quiz handler
        logger.info(f"开始处理 {video_count} 个视频")
        try:
            play_current_video(page)
        except Exception as e:
            logger.error(f"视频控制出错: {e}")

        # 3. Wait for auto-nav to fire (video ends → JS clicks 下一节)
        auto_nav_fired = False
        try:
            auto_nav_fired = monitor_video_progress(page, stop_event=stop_event)
        except Exception as e:
            logger.error(f"视频监控出错: {e}")

        if stop_event and stop_event.is_set():
            break

        # 4. If auto-nav fired, page has already navigated
        if auto_nav_fired:
            logger.info("自动导航成功，页面已跳转，进入下一轮")
        else:
            # Fallback: try DOM navigation
            logger.warning("自动导航未触发，尝试 DOM 导航作为后备")
            try:
                try_click_next_section(page)
            except Exception as e:
                logger.error(f"DOM 导航出错: {e}")

        # 5. Check if all courses are done
        if not has_more_content(page):
            logger.info("全部任务完成！自动化结束。")
            print("\n=== 全部完成 ===")
            return

        # Brief pause before next cycle
        time.sleep(config.SECTION_CHECK_INTERVAL)


def parse_args():
    parser = argparse.ArgumentParser(description="学习通自动刷课脚本 (Playwright 版)")
    parser.add_argument(
        "--speed",
        type=float,
        default=config.SPEED_DEFAULT,
        help=f"播放速度，默认 {config.SPEED_DEFAULT}x",
    )
    parser.add_argument(
        "--countdown",
        type=int,
        default=config.START_COUNTDOWN,
        help=f"启动前倒计时秒数，默认 {config.START_COUNTDOWN}",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    setup_logging()

    if args.speed != config.SPEED_DEFAULT:
        config.SPEED_DEFAULT = args.speed
        logger.info(f"速度覆盖: {args.speed}x")

    config.START_COUNTDOWN = args.countdown

    # Preflight check
    if not preflight_check():
        sys.exit(1)

    try:
        main_loop()
    except KeyboardInterrupt:
        logger.info("用户按 Ctrl+C 中止")
        print("\n已中止")
    finally:
        close_browser()
