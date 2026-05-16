"""Section navigation — DOM-based via page.evaluate().

No OCR, no DevTools, no mouse clicks. Pure Playwright JS execution.
弹窗处理增加 Playwright 原生 locator.click(force=True) 兜底。
PPT 滚动增加 wheel 事件模拟 + nicescroll API 支持。
"""

import time

from loguru import logger
from playwright.sync_api import Page

from core.js_snippets import (
    navigate_next_js,
    check_nav_marker_js,
    scroll_to_bottom_js,
    scroll_ppt_gradually_js,
    detect_popup_js,
)


def scroll_ppt_container(page: Page) -> bool:
    """滚动 PPT 内容到底部。

    真实 DOM 结构（通过逐层诊断确认）：
      顶层 frame (studentstudy 页面)
        └─ #content1.chapter              ← 主页面滚动容器（不要动！）
             nicescroll #ascrail2001 挂在此元素上
             └─ iframe (knowledge/cards)
                  └─ iframe (pdf/index.html)
                       └─ iframe#panView (pan-yz.chaoxing.com/screen/v2/...)
                            └─ document.documentElement  ← PPT 真正的滚动目标！
                                 scrollH=4860, clientH=546, 可滚动=4314
                                 body overflow=auto，原生滚动，无 nicescroll

    关键发现：
      - #content1 是主页面滚动容器，滚动它会移动整个页面而非 PPT 内容
      - PPT 内容的滚动在 panView iframe 的 document.documentElement 上
      - panView frame 使用原生滚动，无 nicescroll
      - panView 是跨域 iframe，JS 无法跨域访问，必须由 Playwright 定位 frame

    执行策略：
    1. 查找 URL 含 pan-yz.chaoxing.com 或 screen/v2/file 的 frame（panView）
    2. 在该 frame 内执行 scroll_to_bottom_js() / scroll_ppt_gradually_js()
    3. 兜底：遍历所有 frame 尝试滚动

    Args:
        page: Playwright Page 对象。

    Returns:
        True 如果成功找到并滚动了滚动容器。
    """
    scrolled = False

    # 优先查找 panView frame（PPT 内容的真正所在 frame）
    panview_frame = None
    for frame in page.frames:
        url = frame.url
        if 'pan-yz.chaoxing.com' in url or 'screen/v2/file' in url:
            panview_frame = frame
            logger.info(f"找到 panView frame: {url[:80]}")
            break

    if panview_frame:
        # 方式1：直接 scrollTop 一次性滚到底（最可靠，不会冒泡到父 frame）
        try:
            result = panview_frame.evaluate(scroll_to_bottom_js())
            if result and result > 0:
                logger.info(f"PPT 容器滚动成功 (panView frame, scrollTop={result})")
                scrolled = True
        except Exception as e:
            logger.debug(f"panView frame scrollTop 滚动失败: {e}")

        # 方式2：逐步 scrollTop 递增（模拟自然滚动，可能触发浏览进度追踪）
        if not scrolled:
            try:
                result = panview_frame.evaluate(scroll_ppt_gradually_js())
                if result and result > 0:
                    logger.info(f"PPT 容器逐步滚动成功 (panView frame)")
                    scrolled = True
            except Exception as e:
                logger.debug(f"panView frame 逐步滚动失败: {e}")

    # 兜底：遍历所有 frame 尝试滚动（某些页面结构可能不同）
    # 只尝试非主 frame，且排除已经尝试过的 panView frame
    if not scrolled:
        for frame in page.frames:
            if frame == page:
                continue
            if frame == panview_frame:
                continue
            url = frame.url
            # 跳过主页面 frame（滚动它的 documentElement 等于滚动主页面）
            if 'studentstudy' in url or 'mycourse' in url:
                continue
            try:
                result = frame.evaluate(scroll_ppt_gradually_js())
                if result and result > 0:
                    logger.info(f"PPT 容器逐步滚动成功 (iframe: {frame.url[:60]})")
                    scrolled = True
                    break
            except Exception:
                pass

            try:
                frame.evaluate(scroll_to_bottom_js())
                logger.info(f"PPT 容器滚动成功 (iframe: {frame.url[:60]})")
                scrolled = True
                break
            except Exception:
                pass

    return scrolled


def click_popup_next_chapter(page: Page) -> bool:
    """点击弹窗内「下一节」按钮，导航到下一节。

    真实弹窗结构（通过深度诊断确认）：
      弹窗在顶层 frame（studentstudy 页面），不在 iframe 内
      页面有 10 个 .popDiv，只有 .popDiv[3] 含 .nextChapter 按钮
      按钮标签: <a>，文本: "下一节"
      onclick: closeDeleteWindow();PCount.next('3','1021706543','254631881','140506502','')

    深度诊断结果：
      closeDeleteWindow() → 不关闭此弹窗（.popDiv 数量不变）
      PCount.next()      → ✅ 成功导航到下一节
      Playwright click   → 被 maskDiv(z=999) 遮挡，force=True 也无法触发 onclick

    因此策略改为：直接从 onclick 属性提取 PCount.next() 调用并 eval 执行。

    Args:
        page: Playwright Page 对象。

    Returns:
        True 如果成功执行了 PCount.next() 导航。
    """
    # 策略1（最可靠）：JS 层提取 onclick 中的 PCount.next() 并直接调用
    js_extract_pcount = (
        "(function(){"
        "var all=document.querySelectorAll('.popDiv');"
        "for(var i=0;i<all.length;i++){"
        "var el=all[i];"
        # 注意：position:fixed 元素的 offsetParent 是 null，不能用 offsetParent 判断可见性
        # 改用 getComputedStyle 检查
        "var cs=window.getComputedStyle(el);"
        "if(!cs||cs.display==='none'||cs.visibility==='hidden')continue;"
        "var nc=el.querySelector('.nextChapter');"
        "if(!nc)continue;"
        # 从 onclick 属性提取 PCount.next(...) 调用
        "var oc=nc.getAttribute('onclick')||'';"
        "if(oc.indexOf('PCount.next')!==-1){"
        "try{"
        # 直接 eval 整个 onclick（含 closeDeleteWindow + PCount.next）
        "eval(oc);"
        "console.log('POPUP_CLICK: eval onclick → '+oc.substring(0,80));"
        "return true;"
        "}catch(e1){"
        # eval 失败则单独提取 PCount.next 调用
        "try{"
        "var m=oc.match(/PCount\\.next\\([^)]*\\)/);"
        "if(m){eval(m[0]);console.log('POPUP_CLICK: eval PCount.next → '+m[0]);return true;}"
        "}catch(e2){console.log('POPUP_CLICK: PCount.next failed: '+e2);}"
        "}"
        "}"
        # onclick 中没有 PCount.next，尝试文本匹配「下一节」
        "var links=el.querySelectorAll('a,button');"
        "for(var j=0;j<links.length;j++){"
        "var t=(links[j].textContent||'').trim();"
        "if(t==='下一节'){"
        "try{links[j].click();return true;}catch(e){}"
        "}"
        "}"
        "}"
        "return false;"
        "})()"
    )

    # 弹窗在顶层 frame，优先在顶层 frame 执行
    url_before = page.url
    for frame in page.frames:
        try:
            result = frame.evaluate(js_extract_pcount)
            if result:
                logger.info("弹窗「下一节」点击成功（PCount.next 调用）")
                return True
        except Exception:
            # PCount.next() 触发页面导航会销毁执行上下文，导致 evaluate 抛异常
            # 这是成功导航的标志，不是失败！检查 URL 是否变化
            try:
                if page.url != url_before:
                    logger.info("弹窗「下一节」点击成功（PCount.next 触发导航，执行上下文已销毁）")
                    return True
            except Exception:
                pass

    # 策略2：Playwright locator 兜底（mask 层可能不总是存在）
    for frame in page.frames:
        try:
            btn = frame.locator(".popDiv:has(.nextChapter) .nextChapter")
            if btn.count() > 0:
                btn.first.click(force=True, timeout=3000)
                logger.info("弹窗「下一节」按钮点击成功（Playwright locator）")
                return True
        except Exception:
            pass

    logger.warning("弹窗「下一节」点击失败：所有方式均未成功")
    return False


def _js_click_popup_next(page: Page) -> bool:
    """JS 层弹窗按钮点击兜底方案。

    深度诊断确认：
      closeDeleteWindow() 不关闭此弹窗，但 PCount.next() 能导航到下一节。
      因此优先提取并执行 PCount.next() 调用。

    Args:
        page: Playwright Page 对象。

    Returns:
        True 如果成功执行了 PCount.next() 导航。
    """
    js = (
        "(function(){"
        "var all=document.querySelectorAll('.popDiv');"
        "for(var i=0;i<all.length;i++){"
        "var el=all[i];"
        # position:fixed 元素的 offsetParent 是 null，改用 getComputedStyle
        "var cs=window.getComputedStyle(el);"
        "if(!cs||cs.display==='none'||cs.visibility==='hidden')continue;"
        "var nc=el.querySelector('.nextChapter');"
        "if(!nc)continue;"
        "var oc=nc.getAttribute('onclick')||'';"
        # 优先 eval 整个 onclick
        "try{eval(oc);return true;}catch(e){}"
        # 失败则单独提取 PCount.next
        "try{"
        "var m=oc.match(/PCount\\.next\\([^)]*\\)/);"
        "if(m){eval(m[0]);return true;}"
        "}catch(e){}"
        # 最后尝试 .click()
        "try{nc.click();return true;}catch(e){}"
        "}"
        "return false;"
        "})()"
    )

    url_before = page.url
    for frame in page.frames:
        try:
            result = frame.evaluate(js)
            if result:
                logger.info("JS 层弹窗点击成功")
                return True
        except Exception:
            # PCount.next() 触发导航会销毁执行上下文，检查 URL 变化
            try:
                if page.url != url_before:
                    logger.info("JS 层弹窗点击成功（导航触发，执行上下文已销毁）")
                    return True
            except Exception:
                pass

    return False


def detect_popup(page: Page) -> dict:
    """检测页面是否存在「任务点未完成」弹窗。

    Args:
        page: Playwright Page 对象。

    Returns:
        字典 {found: bool, hasNextChapter: bool}
    """
    for frame in page.frames:
        try:
            result = frame.evaluate(detect_popup_js())
            if result.get("found"):
                return result
        except Exception:
            pass
    return {"found": False, "hasNextChapter": False}


def try_click_next_section(page: Page) -> bool:
    """Navigate to the next section using DOM-based JS.

    改进流程：
    1. 先检测并处理弹窗（Playwright locator 优先）
    2. 再执行常规 DOM 导航
    3. 导航失败时再次检测弹窗并重试

    Args:
        page: Playwright Page 对象。

    Returns:
        True if navigation was triggered successfully.
    """
    url_before = page.url

    # --- Step 0: 检测并处理弹窗 ---
    popup = detect_popup(page)
    if popup.get("found"):
        logger.info("检测到弹窗，尝试点击「下一节」...")
        if popup.get("hasNextChapter"):
            if click_popup_next_chapter(page):
                time.sleep(2)
                if page.url != url_before:
                    logger.info("弹窗「下一节」点击后页面已跳转")
                    return True
                logger.info("弹窗点击后页面未跳转，继续常规导航")

    # --- Helper: call navigate_next_js in a frame and wait for result ---
    def _try_frame(frame, timeout=45000) -> bool:
        url_before_try = page.url
        try:
            frame.evaluate(navigate_next_js())
            frame.wait_for_function(check_nav_marker_js(), timeout=timeout)
        except Exception:
            try:
                if page.url != url_before_try:
                    logger.info("DOM 导航成功（URL已变化，执行上下文已销毁）")
                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except Exception:
                        time.sleep(1)
                    return True
            except Exception:
                pass
            return False

        try:
            is_done = frame.evaluate("!!window.__autoNavDone")
            failed_reason = frame.evaluate("window.__autoNavFailedReason")
        except Exception:
            is_done = False
            failed_reason = None

        if failed_reason == "task_unfinished":
            logger.warning("DOM 导航被阻止：任务点未完成")
            return False

        if is_done:
            return True

        return False

    # 1. Main frame
    logger.info("DOM 导航：查找下一节按钮（主 frame）...")
    if _try_frame(page, timeout=15000):
        if page.url != url_before:
            logger.info("DOM 导航成功（主 frame）")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                time.sleep(1)
            return True
        logger.info("主 frame 导航标记成功，URL 未变，检查 iframe...")

    # 2. Iframe fallback (e.g. iframe#panView on image/doc pages)
    logger.info("主 frame 导航未成功，尝试 iframe...")

    # 先用 scroll_ppt_container() 统一滚动 PPT（和第一个 PPT 走同一条路径）
    scroll_ppt_container(page)

    for frame in page.frames:
        if frame == page:
            continue
        url = frame.url
        # 只在 panView frame 尝试导航（其他 frame 没有下一节按钮）
        if 'pan-yz.chaoxing.com' not in url and 'screen/v2/file' not in url:
            continue
        logger.info(f"  iframe 尝试: {url[:80]}")

        if _try_frame(frame, timeout=15000):
            if page.url != url_before:
                logger.info(f"DOM 导航成功（iframe）")
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    time.sleep(1)
                return True
            else:
                logger.info("iframe 导航标记成功但 URL 未变")
        else:
            logger.info(f"  iframe 未找到按钮: {url[:60]}")

    # 3. 导航失败后再次检测弹窗（弹窗可能在导航过程中出现）
    popup = detect_popup(page)
    if popup.get("found") and popup.get("hasNextChapter"):
        logger.info("导航后检测到弹窗，重试点击「下一节」...")
        if click_popup_next_chapter(page):
            time.sleep(2)
            if page.url != url_before:
                logger.info("弹窗重试点击后页面已跳转")
                return True

    logger.warning("DOM 导航超时：所有 frame 均未找到导航按钮")
    return False


def has_more_content(page: Page) -> bool:
    """Check if there is more content to process.

    Simple heuristic via DOM check for completion indicators.

    Args:
        page: Playwright Page 对象。

    Returns:
        False if all content is complete.
    """
    js = (
        "("
        "function(){"
        "var d=document.body.innerText||'';"
        "return !("
        "d.indexOf('已完成全部任务')!==-1||"
        "d.indexOf('学习完成')!==-1||"
        "d.indexOf('全部完成')!==-1"
        ");"
        "})()"
    )
    try:
        result = page.evaluate(js)
        if not result:
            logger.info("检测到全部完成标记")
            return False
    except Exception:
        pass
    return True
