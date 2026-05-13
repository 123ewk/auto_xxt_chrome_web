# auto_xxt_chrome_web — 学习通自动刷课脚本

基于 PyAutoGUI + 图像识别的前台自动化脚本，半自动操作 Chrome 网页版学习通，模拟真人观看视频、自动跳转下一节、处理弹窗。

## 环境要求

- Windows 10/11
- Python 3.10+
- Chrome 浏览器
- 学习通 Web 版（https://i.chaoxing.com）

## 快速开始

### 1. 虚拟环境

```bash
# 使用项目自带的虚拟环境
.venv\Scripts\activate    # CMD
# 或
source .venv/Scripts/activate  # Git Bash / PowerShell
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 截图模板（首次必须）

运行引导式截图工具，依次框选屏幕上对应的按钮/图标：

```bash
python main.py --calibrate
```

需要截图的模板列表（共 20 个）:

| 模板名 | 说明 | 截图位置 |
|--------|------|----------|
| `play_button` | 视频播放按钮 | 视频中央的 ▶ 按钮 |
| `next_section` | "下一节"按钮 | 视频结束后出现的按钮 |
| `complete_checkmark` | 完成对勾 | 任务完成后的 ✅ 标记 |
| `task_complete` | 任务完成文字 | "任务完成"等提示 |
| `back_to_course` | 返回课程 | 返回课程列表按钮 |
| `section_unlocked` | 解锁章节 | 新解锁的可点击章节 |
| `generic_next` | 通用下一步 | "继续"、"下一步"等文字按钮 |
| `speed_2x` | 2倍速标签 | 播放器上显示的 2x 标识 |
| `speed_1.5x` | 1.5倍速标签 | 播放器上显示的 1.5x 标识 |
| `speed_1x` | 1倍速标签 | 正常速度标识 |
| `mute_button` | 静音按钮 | 播放器上的喇叭图标 |
| `popup_confirm` | 弹窗确认 | 弹窗中的"确定"/"确认"按钮 |
| `popup_cancel` | 弹窗取消 | 弹窗中的"取消"按钮 |
| `popup_close` | 弹窗关闭 | 弹窗右上角 ✕ |
| `quiz_option_a` | 选项 A | 随堂测验的 A 选项 |
| `quiz_option_b` | 选项 B | 随堂测验的 B 选项 |
| `quiz_option_c` | 选项 C | 随堂测验的 C 选项 |
| `quiz_option_d` | 选项 D | 随堂测验的 D 选项 |
| `quiz_confirm` | 提交答案 | 测验的"提交"按钮 |
| `video_region` | 视频区域 | 视频播放器所在区域 |

### 4. 查看模板状态

```bash
python main.py --status
```

### 5. 开始刷课

```bash
# 手动打开 Chrome → 进入学习通课程 → 切换到有视频的章节
python main.py
```

脚本启动后有 5 秒倒计时，切换到 Chrome 窗口即可。

## CLI 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--calibrate` | 引导式模板截图 | - |
| `--status` | 查看模板状态 | - |
| `--speed N` | 播放速度倍率 | 2.0 |
| `--countdown N` | 启动倒计时秒数 | 5 |

### 示例

```bash
# 1.5 倍速运行，10 秒倒计时
python main.py --speed 1.5 --countdown 10
```

## 运行原理

```
手动打开课程页面
       ↓
  5 秒倒计时（切换到 Chrome）
       ↓
  ┌─── 检测弹窗 ──────────────┐
  │  · 模板匹配已知弹窗按钮    │
  │  · 轮廓检测未知弹窗区域    │
  └────────────────────────────┘
       ↓
  ┌─── 视频控制 ──────────────┐
  │  · 点击播放按钮            │
  │  · DevTools 静音           │
  │  · DevTools 加速 (或降级)  │
  └────────────────────────────┘
       ↓
  ┌─── 进度监控 ──────────────┐
  │  · 截图检测完成标记        │
  │  · 超时保护 (10分钟)       │
  └────────────────────────────┘
       ↓
  ┌─── 导航 ──────────────────┐
  │  · 点击"下一节"按钮        │
  │  · 检测新解锁章节          │
  └────────────────────────────┘
       ↓
  循环直到没有更多内容
```

## 加速降级策略

1. DevTools Console 注入 `video.playbackRate = 2`
2. 等待 3 秒检测速度标签
3. 失败则重试一次
4. 仍失败 → 回退到 1x 正常速度

## 安全机制

- **Fail-safe**: 鼠标移到屏幕左上角，脚本立即停止
- **半自动**: 登录等敏感操作由用户手动完成
- **超时保护**: 每个视频最多等待 10 分钟
- **日志记录**: 所有操作记录到 `logs/session.log`

## 目录结构

```
sua_ke/
├── main.py                  # 程序入口
├── config.py                # 全局配置
├── requirements.txt         # Python 依赖
├── README.md                # 本文件
├── actions/
│   ├── __init__.py
│   ├── video.py             # 视频播放/静音/加速/监控
│   ├── navigation.py        # 章节导航
│   └── popup.py             # 弹窗检测与处理
├── core/
│   ├── __init__.py
│   ├── screenshot.py        # 截图与模板匹配
│   ├── console.py           # Chrome DevTools 控制
│   └── clicker.py           # 点击封装 (重试+验证)
├── templates/               # PNG 模板图片
│   └── __init__.py
├── docs/plans/
│   └── 2026-05-13-auto-learning-design.md
└── logs/
    └── session.log
```

## 注意事项

1. 运行期间不要遮挡屏幕上的模板匹配区域
2. 确保模板图片是在当前屏幕分辨率下截取的
3. 不同的学习通页面版本可能需要重新截图
4. 建议先用 `--status` 确认模板齐全再运行
