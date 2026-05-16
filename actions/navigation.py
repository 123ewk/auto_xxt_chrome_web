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

    关于执行上下文销毁（Bug 2 fix）：
      PCount.next() 触发页面导航 → Playwright 销毁当前执行上下文 →
      frame.evaluate() 的 Promise 被 reject。这是**成功的标志**，不是失败。
      修复：捕获异常后 wait 0.5s 再检查 URL（给导航时间启动），
      且优先在顶层 frame 执行（弹窗始终在顶层），避免遍历所有 frame
      时每个都因上下文销毁而抛异常。

    Args:
        page: Playwright Page 对象。

    Returns:
        True 如果成功执行了 PCount.next() 导航。
    """
    # 策略1（最可靠）：JS 层提取 onclick 中的 PCount.next() 并直接调用
    js_extract_pcount = (
        "(function(){"
        # Search ALL popup-like elements (not just .popDiv — class may vary)
        "var all=document.querySelectorAll('.popDiv,div,section,aside,form');"
        "var _results=[];"  # diagnostic build-up
        "for(var i=0;i<all.length;i++){"
        "var el=all[i];"
        "var cs=window.getComputedStyle(el);"
        "if(!cs||cs.display==='none'||cs.visibility==='hidden')continue;"
        # Popup detection: position:fixed/absolute OR high z-index
        "var zi=cs.zIndex!=='auto'?parseInt(cs.zIndex):0;"
        "var isPopup=cs.position==='fixed'||cs.position==='absolute'||zi>50;"
        # Also accept elements with "任务点未完" text (task-unfinished popup)
        "var txt=(el.textContent||'');"
        "var hasTaskTxt=txt.indexOf('任务点未完')!==-1;"
        "if(!isPopup&&!hasTaskTxt)continue;"
        # Find .nextChapter button
        "var nc=el.querySelector('.nextChapter');"
        # Also search for links/buttons with "下一节" text
        "if(!nc||nc.offsetWidth===0){"
        "var links=el.querySelectorAll('a,button');"
        "for(var j=0;j<links.length;j++){"
        "var lt=(links[j].textContent||'').trim();"
        "if(lt.indexOf('下一节')!==-1&&links[j].offsetWidth>0){nc=links[j];break;}"
        "}"
        "}"
        "if(!nc||nc.offsetWidth===0){"
        "_results.push('popup['+i+']: no visible nextChapter, txt='+txt.substring(0,60));"
        "continue;"
        "}"
        # Found a candidate — try PCount.next first
        "var oc=nc.getAttribute('onclick')||'';"
        "_results.push('popup['+i+']: .nextChapter found, onclick='+oc.substring(0,80));"
        "if(oc.indexOf('PCount.next')!==-1){"
        "try{"
        "eval(oc);"
        "console.log('POPUP_CLICK: eval onclick OK');"
        "return true;"
        "}catch(e1){"
        "try{"
        "var m=oc.match(/PCount\\.next\\([^)]*\\)/);"
        "if(m){eval(m[0]);console.log('POPUP_CLICK: eval PCount.next OK');return true;}"
        "}catch(e2){console.log('POPUP_CLICK: eval failed: '+e2);}"
        "}"
        "}"
        # No PCount.next — try .click() + MouseEvent as fallback
        "try{nc.click();console.log('POPUP_CLICK: .click()');return true;}catch(e){}"
        "try{"
        "nc.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window}));"
        "console.log('POPUP_CLICK: MouseEvent');"
        "return true;"
        "}catch(e){}"
        "}"
        # No candidate found — log diagnostic and return it for Python-side logging
        "var diag='';"
        "if(_results.length===0){"
        "diag='POPUP_CLICK: no popup element found';"
        "}else{"
        "diag='POPUP_DIAG: '+_results.join(' | ');"
        "}"
        "console.log(diag);"
        # Return the diagnostic string so Python can log it
        "return diag;"
        "})()"
    )

    url_before = page.url
    frame_urls_before = {f.url for f in page.frames}

    # --- Phase A: top frame first (popups are almost always in the top frame) ---
    nav_exception = False
    try:
        result = page.evaluate(js_extract_pcount)
        if result is True:
            logger.info("弹窗「下一节」点击成功（PCount.next 调用）")
            return True
        if isinstance(result, str) and result:
            logger.warning(f"弹窗点击诊断(top): {result}")
        elif result is False:
            logger.warning("弹窗点击诊断(top): 未找到含'下一节'按钮的弹窗元素")
    except Exception as e:
        # PCount.next() 触发页面导航会销毁执行上下文，导致 evaluate 抛异常。
        # 这是成功的标志，不是失败！
        logger.info(f"弹窗点击异常（预期内，导航可能已触发）: {e}")
        nav_exception = True

    if nav_exception:
        time.sleep(0.5)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        try:
            new_frames = {f.url for f in page.frames}
            old_sig = {u for u in frame_urls_before if u and u != 'about:blank'}
            new_sig = {u for u in new_frames if u and u != 'about:blank'}
            if old_sig != new_sig or page.url != url_before:
                logger.info("弹窗「下一节」点击成功（PCount.next 触发导航）")
                return True
        except Exception:
            pass

    # --- Phase B: try ALL frames (popup might be in an iframe) ---
    for frame in page.frames:
        if frame == page:
            continue
        try:
            result = frame.evaluate(js_extract_pcount)
            if result is True:
                logger.info(f"弹窗「下一节」点击成功（iframe: {frame.url[:60]}）")
                return True
            if isinstance(result, str) and result:
                logger.warning(f"弹窗点击诊断({frame.url[:40]}): {result}")
        except Exception:
            time.sleep(0.3)
            try:
                new_frames = {f.url for f in page.frames}
                old_sig = {u for u in frame_urls_before if u and u != 'about:blank'}
                new_sig = {u for u in new_frames if u and u != 'about:blank'}
                if old_sig != new_sig:
                    logger.info(f"弹窗「下一节」点击成功（iframe 异常，frame 已变化）")
                    return True
            except Exception:
                pass

    # --- Phase C: Playwright locator 兜底（mask 层可能不总是存在）---
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
    frame_urls_before = {f.url for f in page.frames}
    for frame in page.frames:
        try:
            result = frame.evaluate(js)
            if result:
                logger.info("JS 层弹窗点击成功")
                return True
        except Exception:
            # PCount.next() triggers navigation → context destroyed → check frame structure
            try:
                new_frames = {f.url for f in page.frames}
                if page.url != url_before or new_frames != frame_urls_before:
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
    frame_urls_before = {f.url for f in page.frames}

    # --- Step 0: 检测并处理弹窗 ---
    popup = detect_popup(page)
    if popup.get("found"):
        logger.info("检测到弹窗，尝试点击「下一节」...")
        if popup.get("hasNextChapter"):
            if click_popup_next_chapter(page):
                time.sleep(2)
                # Check frame structure (not just page.url — 学习通 swaps iframes)
                new_frames = {f.url for f in page.frames}
                old_sig = {u for u in frame_urls_before if u and u != 'about:blank'}
                new_sig = {u for u in new_frames if u and u != 'about:blank'}
                if page.url != url_before or old_sig != new_sig:
                    logger.info("弹窗「下一节」点击后页面已跳转")
                    return True
                logger.info("弹窗点击后页面未跳转，继续常规导航")

    # --- Helper: call navigate_next_js in a frame and wait for result ---
    def _try_frame(frame, timeout=45000) -> bool:
        url_before_try = page.url
        frames_before = {f.url for f in page.frames}
        try:
            frame.evaluate(navigate_next_js())
            frame.wait_for_function(check_nav_marker_js(), timeout=timeout)
        except Exception:
            # Context destroyed — check if navigation happened
            time.sleep(0.5)
            try:
                new_frames = {f.url for f in page.frames}
                if page.url != url_before_try or new_frames != frames_before:
                    logger.info("DOM 导航成功（frame/URL 已变化，执行上下文已销毁）")
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

        # Marker not set — check if frame structure changed anyway
        try:
            new_frames = {f.url for f in page.frames}
            if new_frames != frames_before:
                logger.info("DOM 导航成功（frame 结构已变化，marker 未设但页面已变）")
                return True
        except Exception:
            pass

        return False

    # 1. Main frame (short timeout — popup-based nav needs quick fallback)
    logger.info("DOM 导航：查找下一节按钮（主 frame）...")
    if _try_frame(page, timeout=8000):
        new_frames = {f.url for f in page.frames}
        old_sig = {u for u in frame_urls_before if u and u != 'about:blank'}
        new_sig = {u for u in new_frames if u and u != 'about:blank'}
        if page.url != url_before or old_sig != new_sig:
            logger.info("DOM 导航成功（主 frame）")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                time.sleep(1)
            return True
        logger.info("主 frame 导航标记成功，frame/URL 未变，检查 iframe...")

    # 2. Popup retry immediately after main frame fails (don't wait for iframes)
    #    The main frame click may have triggered a task-unfinished popup that
    #    navigate_next_js's _findPopupInfo couldn't handle.
    popup = detect_popup(page)
    if popup.get("found") and popup.get("hasNextChapter"):
        logger.info("主 frame 未成功，检测到弹窗，点击「下一节」...")
        if click_popup_next_chapter(page):
            time.sleep(2)
            new_frames = {f.url for f in page.frames}
            old_sig = {u for u in frame_urls_before if u and u != 'about:blank'}
            new_sig = {u for u in new_frames if u and u != 'about:blank'}
            if page.url != url_before or old_sig != new_sig:
                logger.info("弹窗点击后页面已跳转")
                return True

    # 3. Iframe fallback (e.g. iframe#panView on image/doc pages)
    logger.info("尝试 iframe...")

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
            new_frames = {f.url for f in page.frames}
            old_sig = {u for u in frame_urls_before if u and u != 'about:blank'}
            new_sig = {u for u in new_frames if u and u != 'about:blank'}
            if page.url != url_before or old_sig != new_sig:
                logger.info(f"DOM 导航成功（iframe）")
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    time.sleep(1)
                return True
            else:
                logger.info("iframe 导航标记成功但 frame/URL 未变")
        else:
            logger.info(f"  iframe 未找到按钮: {url[:60]}")

    # 4. Final popup retry
    popup = detect_popup(page)
    if popup.get("found") and popup.get("hasNextChapter"):
        logger.info("最终检测到弹窗，重试点击「下一节」...")
        if click_popup_next_chapter(page):
            time.sleep(2)
            new_frames = {f.url for f in page.frames}
            old_sig = {u for u in frame_urls_before if u and u != 'about:blank'}
            new_sig = {u for u in new_frames if u and u != 'about:blank'}
            if page.url != url_before or old_sig != new_sig:
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
