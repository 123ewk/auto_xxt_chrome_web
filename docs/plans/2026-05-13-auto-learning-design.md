# 学习通自动刷课脚本设计文档

- 日期: 2026-05-13
- 方案: PyAutoGUI + 图像识别（前台操作）

## 概述

半自动脚本，用户手动打开 Chrome 学习通课程页面后，脚本自动检测并播放视频、静音加速、监控进度、处理弹窗、跳转下一节。

## 架构

```
sua_ke/
├── main.py                 # 入口，CLI 参数解析，主循环
├── config.py               # 全局配置（阈值、超时、路径）
├── actions/
│   ├── video.py            # 视频播放/静音/加速/进度监控
│   ├── navigation.py       # 检测并点击"下一节"等导航按钮
│   └── popup.py            # 弹窗检测与处理（含随堂测验）
├── core/
│   ├── screenshot.py       # 屏幕截取、模板匹配、图像处理
│   ├── console.py          # Chrome DevTools Console 注入 JS
│   └── clicker.py          # 带重试和验证的点击封装
├── templates/              # PNG 模板图片目录
│   └── __init__.py         # 模板管理与状态检查
└── logs/
    └── session.log
```

## 核心流程

1. **预检** — 用户打开 Chrome 学习通页面 → 5 秒倒计时后开始
2. **弹窗处理** — 每轮循环先检测弹窗（模板匹配 + 轮廓检测）
3. **视频控制** — 检测播放按钮 → 点击播放 → DevTools 注入 `video.muted=true` 静音 → 注入 `video.playbackRate=2` 加速
4. **进度监控** — 周期性截图检测完成标记 / 下一节按钮 / 超时
5. **导航** — 检测到完成 → 点击"下一节" → 下一轮循环
6. **重复** — 直到没有更多内容

## 加速降级策略

1. 默认尝试 DevTools Console 注入 `playbackRate=2`
2. 等待 3 秒检测速度标签是否出现
3. 失败则重试一次
4. 仍失败 → 回退到 1x（降级），日志记录 Warning

## 关键技术选型

- **模板匹配**: `pyautogui.locateOnScreen(confidence=0.8, grayscale=True)`
- **JS 注入**: Chrome DevTools (`Ctrl+Shift+I`) → 输入 JS → Enter → 自动关闭
- **弹窗检测**: 轮廓检测 + ROI 裁剪 + 模板匹配
- **点击验证**: 点击后重截屏确认模板消失/出现

## CLI 使用

```
python main.py                          # 正常模式
python main.py --calibrate              # 引导式模板截图
python main.py --status                 # 查看模板状态
python main.py --speed 1.5              # 以 1.5 倍速运行
python main.py --speed 1.5 --countdown 10
```

## 使用步骤

1. `python main.py --calibrate` — 依次截取所有模板图片
2. 手动打开 Chrome，进入学习通课程视频页面
3. `python main.py` — 5 秒内切换到 Chrome 窗口
4. 脚本自动运行直至所有视频完成
