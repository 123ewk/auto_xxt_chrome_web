#!/usr/bin/env python
"""
sua_ke — 学习通自动刷课脚本 (PyAutoGUI + 识图)

Usage:
    python main.py                    # 正常模式
    python main.py --calibrate        # 截取模板图片
    python main.py --status           # 查看模板状态

半自动模式:
    1. 手动在 Chrome 中打开学习通课程页面
    2. 切换到有视频的章节
    3. 运行本脚本
    4. 脚本会自动播放、静音、加速、检测弹窗、跳到下一节
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
from core.clicker import click_template
from core.screenshot import capture_region_for_training
from templates import load_templates, list_missing, print_status


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
    logger.info("Logging initialized")


def calibrate_templates():
    """Interactive template capture mode.

    Guides the user through capturing each missing template image.
    """
    templates = load_templates()
    missing = list_missing(templates)

    if not missing:
        print("All templates already captured!")
        return

    print(f"\n=== Template Calibration ===")
    print(f"Need to capture {len(missing)} templates.")
    print("For each template, you'll select a region on screen.\n")
    print("Tips:")
    print("  - Make sure the element is visible on screen")
    print("  - Select only the button/icon itself (tight crop)")
    print("  - PNG format will be saved automatically\n")
    input("Press Enter to start...")

    for name in missing:
        print(f"\n--- Capturing: {name} ---")
        capture_region_for_training(
            save_path=config.TEMPLATES_DIR / f"{name}.png",
            description=f"Position the '{name}' element on screen, then continue.",
        )

    # Verify
    print("\n=== Verification ===")
    print_status(load_templates())


def main_loop(stop_event=None):
    """Main automation loop.

    1. Detect video → play → mute → speed → monitor
    2. On completion → navigate to next section
    3. Check for popups on every cycle
    4. Repeat until no more content

    Args:
        stop_event: Optional threading.Event to signal stop.
    """
    logger.info("=== sua_ke automation started ===")
    logger.info(f"Templates dir: {config.TEMPLATES_DIR}")
    logger.info(f"Speed target: {config.SPEED_DEFAULT}x")
    logger.info(f"Fail-safe: {'ON' if config.PYAUTOGUI_FAILSAFE else 'OFF'}")

    # Enable PyAutoGUI fail-safe (move mouse to corner to abort)
    pyautogui.FAILSAFE = config.PYAUTOGUI_FAILSAFE
    pyautogui.PAUSE = config.PYAUTOGUI_PAUSE

    # Wait for user to focus the correct window
    print("\n=== Ready ===")
    print("Switch to your Chrome window with the course page.")
    print(f"Starting in 5 seconds... (move mouse to top-left to abort)")
    for i in range(5, 0, -1):
        print(f"  {i}...")
        time.sleep(1)

    # Load templates
    templates = load_templates()
    missing = list_missing(templates)
    if missing:
        logger.warning(f"Missing templates: {', '.join(missing)}")
        logger.warning("Run 'python main.py --calibrate' to capture them")

    cycle_count = 0

    while not (stop_event and stop_event.is_set()):
        cycle_count += 1
        logger.info(f"--- Cycle {cycle_count} ---")

        # 1. Handle any popups first
        try:
            detect_and_handle_popup(templates)
        except Exception as e:
            logger.error(f"Popup detection error: {e}")

        # 2. Check for quiz popups
        try:
            handle_quiz_popup(templates)
        except Exception as e:
            logger.error(f"Quiz popup error: {e}")

        # 3. Play current video
        try:
            play_current_video(templates)
            set_speed_with_fallback(templates)
        except Exception as e:
            logger.error(f"Video play/speed error: {e}")

        # 4. Monitor progress
        try:
            completed = monitor_video_progress(templates, stop_event=stop_event)
        except Exception as e:
            logger.error(f"Video monitor error: {e}")
            completed = False

        if stop_event and stop_event.is_set():
            break

        if not completed:
            logger.warning("Video did not complete normally, checking for more content...")

        # 5. Navigate to next section
        try:
            navigated = try_click_next_section(templates)
        except Exception as e:
            logger.error(f"Navigation error: {e}")
            navigated = False

        # 6. Check if there's more content
        if not navigated:
            has_more = has_more_content(templates)
            if not has_more:
                logger.info("No more content detected — automation complete!")
                logger.info("=== Done ===")
                return

        # Brief pause before next cycle
        time.sleep(config.SECTION_CHECK_INTERVAL)


def parse_args():
    parser = argparse.ArgumentParser(description="学习通自动刷课脚本")
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="截取模板图片（引导式）",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="查看模板状态",
    )
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
        help="启动前的倒计时秒数，默认 5",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    setup_logging()

    if args.speed != config.SPEED_DEFAULT:
        config.SPEED_DEFAULT = args.speed
        logger.info(f"Speed override: {args.speed}x")

    if args.status:
        templates = load_templates()
        print_status(templates)
        sys.exit(0)

    if args.calibrate:
        calibrate_templates()
        sys.exit(0)

    if args.countdown != 5:
        # The countdown is handled in main_loop, just pass it along usage.
        pass

    main_loop()
