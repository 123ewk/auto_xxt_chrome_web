# auto_xxt_chrome_web — 学习通自动刷课脚本 (Playwright 版)

基于 **Playwright + Chrome DevTools Protocol (CDP)** 的全自动刷课脚本。通过浏览器底层协议直接控制 Chrome，注入 JS 实现视频播放、静音、加速、弹窗处理、测验答题、章节导航，全程无需截图模板和 OCR 坐标点击。

## 目录

- [环境要求](#环境要求)
- [安装步骤](#安装步骤)
- [首次使用](#首次使用)
- [命令行参数](#命令行参数)
- [运行原理](#运行原理)
- [常见问题](#常见问题)
- [注意事项](#注意事项)

---

## 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10 或 11 |
| Python | 3.10 或更高 |
| 浏览器 | Google Chrome（系统安装版） |
| 学习通 | https://i.chaoxing.com |
| Tesseract OCR | 可选，仅用于启动前预检 |

---

## 安装步骤

### 1. 克隆项目

```bash
git clone git@github.com:123ewk/auto_xxt_chrome_web.git
cd auto_xxt_chrome_web
```

### 2. 虚拟环境

```bash
# Windows CMD:
python -m venv .venv
.venv\Scripts\activate

# PowerShell:
.venv\Scripts\Activate.ps1

# Git Bash:
source .venv/Scripts/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. 配置环境变量

脚本通过环境变量读取敏感信息（账号密码、课程链接），避免硬编码泄露：

```bash
# Windows PowerShell:
$env:XXT_PHONE = "你的手机号"
$env:XXT_PASSWORD = "你的密码"
$env:XXT_COURSE_URL = "https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=xxx&courseId=xxx&..."

# Windows CMD:
set XXT_PHONE=你的手机号
set XXT_PASSWORD=你的密码
set XXT_COURSE_URL=https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=xxx&courseId=xxx&...

# Git Bash:
export XXT_PHONE="你的手机号"
export XXT_PASSWORD="你的密码"
export XXT_COURSE_URL="https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=xxx&courseId=xxx&..."
```

| 环境变量 | 必填 | 说明 |
|----------|------|------|
| `XXT_PHONE` | Cookie 失效时必填 | 学习通手机号/账号 |
| `XXT_PASSWORD` | Cookie 失效时必填 | 学习通密码 |
| `XXT_COURSE_URL` | 是 | 课程页面链接（在学习通网页端打开课程 → 复制地址栏 URL） |
| `TESSERACT_CMD` | 否 | Tesseract 可执行文件路径，默认 `D:\Tesseract_OCR\tesseract.exe` |

> 也可以直接编辑 `config.py` 修改默认值，但**不要将含真实账号密码的 config.py 提交到 GitHub**。

### 5. 配置 Tesseract 路径（可选）

如需启用 OCR 预检，安装 Tesseract 并配置路径：

- 下载地址: https://github.com/UB-Mannheim/tesseract/wiki
- 安装时勾选 **Chinese (Simplified)** 语言包

通过环境变量配置：

```bash
set TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

> 不安装 Tesseract 不影响核心功能，仅跳过启动时的 OCR 可用性检查。

---

## 首次使用

```bash
# 激活虚拟环境
source .venv/Scripts/activate

# 运行脚本
python main.py
```

脚本会：
1. 提示关闭所有 Chrome 窗口（避免 Profile 锁冲突）
2. 自动复制 Chrome Profile 到临时目录并启动浏览器
3. 自动导航到学习通登录页（Cookie 有效则自动登录）
4. 倒计时后开始自动刷课

### 播放速度调整

```bash
# 1.5 倍速
python main.py --speed 1.5

# 2 倍速（默认）
python main.py --speed 2.0
```

### 延长准备时间

```bash
# 10 秒倒计时
python main.py --countdown 10
```

---

## 命令行参数

| 参数 | 作用 | 默认值 | 说明 |
|------|------|--------|------|
| `--speed` | 播放倍速 | 2.0 | 设为 1.0 则正常速度。平台限制时自动降级 |
| `--countdown` | 启动倒计时秒数 | 10 | 脚本开始操作前的等待时间 |

示例：

```bash
python main.py --speed 1.5 --countdown 8
```

### 紧急停止

- **Ctrl+C** — 终端中按 Ctrl+C 安全停止

---

## 运行原理

### 核心技术

脚本通过 Playwright 的 CDP 控制权，直接在浏览器中执行 JavaScript，替代传统的 OCR 识别 + 鼠标模拟：

```
Playwright 启动 Chrome (复制用户 Profile)
        ↓
addInitScript 注入视频限制绕过 (双层防御)
        ↓
page.evaluate() 执行 JS:
  · video.play() / video.muted / video.playbackRate
  · DOM 查找按钮 → .click() / MouseEvent / eval()
  · 测验自动答题 (radio/checkbox 状态机)
  · 弹窗自动关闭 (CSS 特征识别)
        ↓
Python 调度层: 检测 → 播放 → 监控 → 导航 → 循环
```

### 整体流程

```
运行 python main.py
        ↓
关闭 Chrome → 脚本复制 Profile → Playwright 启动 Chrome
        ↓
自动导航到学习通 → Cookie 登录 / 自动填写账号密码
        ↓
跳转到课程页面 → 倒计时
        ↓
┌───────────────────────────────────────┐
│ 主循环                                 │
│                                       │
│  1. 检测视频                           │
│     ├─ 有视频 → 注入 auto_nav + quiz   │
│     │   → 播放 + 静音 + 加速           │
│     │   → 监控进度 (任务点完成检测)      │
│     │   → 视频结束自动导航下一节         │
│     │   → 超时/未完成: 16x 高速重放      │
│     │                                 │
│     └─ 无视频 (PPT/文档页)              │
│         → 滚动 PPT 容器到底部           │
│         → 处理弹窗 → 导航下一节          │
│                                       │
│  2. 测验处理 (JS 事件驱动状态机)         │
│     · 单选: 逐个尝试选项               │
│     · 多选: 组合枚举 (从多到少)         │
│     · 答题后自动关闭结果弹窗             │
│     · 答题后 seek 视频到末尾恢复播放     │
│                                       │
│  3. 弹窗处理                           │
│     · 自动关闭非导航类弹窗              │
│     · 导航类弹窗 (含「下一节」) 留给导航  │
│     · Playwright locator.click 兜底    │
│                                       │
│  4. 检测是否全部完成                    │
│     · 检测「已完成全部任务」等文字        │
│     · 完成 → 退出循环                  │
└───────────────────────────────────────┘
```

### 视频限制绕过

学习通通过 JS 拦截 `currentTime`/`playbackRate` 的 setter 和注册限制性事件监听器来控制视频播放。脚本通过 `addInitScript` 在页面脚本之前注入双层防御：

1. **拦截 setter**：重写 `HTMLVideoElement.prototype` 的 `currentTime` 和 `playbackRate` setter，阻止平台重置
2. **阻止限制性监听器**：拦截 `addEventListener`，阻止含 `_0x` 的限制性事件监听器注册

### 加速降级

部分视频受平台限制无法加速，脚本自动处理：

```
设置 playbackRate=2 → 等待 3 秒检测 → 检测到 2x? → 是: 加速成功
                                              → 否: 重试一次
                                                     → 仍失败: 回退 1x 正常速度
```

### 高速重放

视频自然结束后若任务点仍未完成（观看时长不足），脚本启动 16x 高速重放，积累有效观看时长直到任务点完成。

### 模块说明

| 模块 | 作用 |
|------|------|
| `core/browser.py` | Playwright 浏览器管理：复制 Profile → 启动 Chrome → 注入绕过脚本 → 自动关闭 dialog |
| `core/js_snippets.py` | 所有 JS 注入代码段：视频控制、限制绕过、测验答题、弹窗检测、导航、滚动、状态查询 |
| `core/ocr.py` | OCR 工具（遗留模块，仅 `ocr_status()` 用于预检） |
| `actions/video.py` | 视频逻辑（Python 调度层）：检测视频 → 注入 JS → 监控进度 → 高速重放 |
| `actions/navigation.py` | 导航逻辑（Python 调度层）：弹窗检测 → 下一节点击 → PPT 滚动 → 完成检测 |

---

## 常见问题

### Q: 运行时提示「请关闭所有 Chrome 窗口」？

Chrome 会锁定用户 Profile 目录，Playwright 无法同时使用。关闭所有 Chrome 窗口后按 Enter 继续。

### Q: Cookie 登录失败？

首次运行时如果 Cookie 过期，脚本会自动检测登录页并填写账号密码。确保 `config.py` 中的 `COURSE_URL` 正确。

### Q: 视频加速无效？

这是学习通的限制，脚本会自动降级到 1x 正常速度继续运行。查看 `logs/session.log` 确认降级原因。

### Q: 测验答错了怎么办？

脚本采用穷举策略：单选逐个尝试，多选从最多选项组合开始枚举。答错后会自动关闭结果弹窗并重试。

### Q: 弹窗没被处理？

脚本通过 CSS 特征识别弹窗（fixed/absolute 定位 + 高 z-index + box-shadow），大部分弹窗可自动关闭。如果遇到新类型弹窗，可在 `core/js_snippets.py` 的 `_dismiss` 函数中添加关键词。

### Q: 脚本卡在某个章节不动了？

- 检查 `logs/session.log` 查看详细日志
- 视频超时保护为 2 小时（`VIDEO_FINISH_TIMEOUT`），超时后自动跳过
- 可在 `config.py` 中调整 `VIDEO_CHECK_INTERVAL` 和 `SECTION_CHECK_INTERVAL`

---

## 目录结构

```
sua_ke/
├── main.py                  # 程序入口 + 主循环
├── config.py                # 全局配置（课程链接、速度、超时等）
├── requirements.txt         # 依赖列表
├── README.md                # 本文件
├── actions/
│   ├── video.py             # 视频控制（Python 调度层）
│   └── navigation.py        # 章节导航 + 弹窗处理 + PPT 滚动
├── core/
│   ├── browser.py           # Playwright 浏览器管理
│   ├── js_snippets.py       # JS 注入代码段（视频/测验/弹窗/导航）
│   └── ocr.py               # OCR 工具（遗留，仅预检用）
├── docs/plans/
│   └── 2026-05-13-auto-learning-design.md
└── logs/
    └── session.log          # 日志文件
```

---

## 注意事项

1. **运行前关闭 Chrome** — Playwright 需要独占 Chrome Profile，否则会锁冲突
2. **Cookie 自动登录** — 脚本复制 Chrome Profile 保留登录状态，首次需手动登录一次
3. **不要做考试/作业** — 本脚本仅用于自动观看视频章节，测验答题为穷举策略
4. **查看日志** — `logs/session.log` 记录了每次操作的详细信息
5. **超时保护** — 每个视频最多等待 2 小时，超时自动跳过
6. **加速降级是正常行为** — 部分视频无法加速，脚本自动处理
7. **高速重放** — 视频结束后若任务点未完成，会自动 16x 重放积累观看时长
