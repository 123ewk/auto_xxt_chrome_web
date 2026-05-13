#!/usr/bin/env python
"""
sua_ke — 学习通自动刷课脚本 (OCR 版)

基于 OCR 文字识别的半自动刷课脚本。
无需截图模板，自动识别屏幕上中文字按钮。

Usage:
    python main.py                    # 正常模式
    python main.py --speed 1.5        # 1.5 倍速

操作流程:
    1. 手动在 Chrome 中打开学习通课程页面
    2. 切换到有视频的章节
    3. 运行本脚本
    4. 脚本通过 OCR 自动识别并操作
"""

import argparse
import sys
import time
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))

import pyautogui
from loguru import logger

import config
from actions.navigation import try_click_next_section, has_more_content
from actions.popup import detect_and_handle_popup, handle_quiz_popup
from actions.video import play_current_video, set_speed_with_fallback, monitor_video_progress
from core.ocr import ocr_status


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

    Verifies:
    - Tesseract OCR is installed and has Chinese language pack
    - Screen resolution is reasonable

    Returns:
        True if all checks pass.
    """
    status = ocr_status()
    if not status["available"]:
        logger.error("Tesseract OCR 不可用！请检查安装。")
        print("\n错误: Tesseract OCR 未正确配置。")
        print(f"  配置路径: {status['tesseract_path']}")
        print("  请确认已安装 Tesseract OCR 并包含中文语言包。")
        return False

    logger.info(f"OCR 引擎: {status['tesseract_path']}")
    logger.info(f"语言包: {status['languages']}")

    if "chi_sim" not in status["languages"]:
        logger.error("缺少中文语言包 (chi_sim)")
        print("\n错误: Tesseract 缺少中文语言包 (chi_sim)。")
        print("  请下载 chi_sim.traineddata 放到 tessdata 目录。")
        return False

    screen_w, screen_h = pyautogui.size()
    logger.info(f"屏幕分辨率: {screen_w}x{screen_h}")

    return True


def main_loop(stop_event=None):
    """Main automation loop.

    1. OCR pre-check → play → mute → speed → monitor
    2. On completion → navigate to next section
    3. Check for popups on every cycle
    4. Repeat until no more content

    Args:
        stop_event: Optional threading.Event for external stop.
    """
    logger.info("=== sua_ke OCR 自动化开始 ===")
    logger.info(f"目标速度: {config.SPEED_DEFAULT}x")

    # PyAutoGUI settings
    pyautogui.FAILSAFE = config.PYAUTOGUI_FAILSAFE
    pyautogui.PAUSE = config.PYAUTOGUI_PAUSE

    # Wait for user to focus the correct window
    print("\n=== 准备就绪 ===")
    print("请切换到 Chrome 学习通课程页面。")
    print(f"倒计时 {config.START_COUNTDOWN} 秒后开始... (Ctrl+C 中止)")
    for i in range(config.START_COUNTDOWN, 0, -1):
        print(f"  {i}...")
        time.sleep(1)

    cycle_count = 0

    while not (stop_event and stop_event.is_set()):
        cycle_count += 1
        logger.info(f"--- 第 {cycle_count} 轮循环 ---")

        # 1. Handle any popups first
        try:
            detect_and_handle_popup()
        except Exception as e:
            logger.error(f"弹窗检测出错: {e}")

        # 2. Check for quiz popups
        try:
            handle_quiz_popup()
        except Exception as e:
            logger.error(f"测验弹窗出错: {e}")

        # 3. Play current video
        try:
            play_current_video()
            set_speed_with_fallback()
        except Exception as e:
            logger.error(f"视频控制出错: {e}")

        # 4. Monitor progress
        try:
            completed = monitor_video_progress(stop_event=stop_event)
        except Exception as e:
            logger.error(f"视频监控出错: {e}")
            completed = False

        if stop_event and stop_event.is_set():
            break

        if not completed:
            logger.warning("视频未正常完成，继续检查是否有更多内容...")

        # 5. Navigate to next section
        try:
            navigated = try_click_next_section()
        except Exception as e:
            logger.error(f"导航出错: {e}")
            navigated = False

        # 6. Check if done
        if not navigated:
            if not has_more_content():
                logger.info("全部任务完成！自动化结束。")
                print("\n=== 全部完成 ===")
                return

        # Brief pause before next cycle
        time.sleep(config.SECTION_CHECK_INTERVAL)


def parse_args():
    parser = argparse.ArgumentParser(description="学习通自动刷课脚本 (OCR 版)")
    parser.add_argument(
        "--speed",
        type=float,
        default=config.SPEED_DEFAULT,
        help=f"播放速度，默认 {config.SPEED_DEFAULT}x",
    )
    parser.add_argument(
        "--countdown",
        type=int,
        default=5,
        help="启动前倒计时秒数，默认 5",
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
        sys.exit(0)
