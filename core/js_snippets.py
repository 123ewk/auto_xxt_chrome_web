"""JavaScript snippets ported from core/console.py.

All functions were previously injected via DevTools clipboard paste.
Now they're delivered via page.evaluate() — no DevTools, no keyboard.

Some functions use Promises for async results that Playwright
natively awaits via page.evaluate().
"""

# ---------------------------------------------------------------------------
# Shared: video element finder (used by multiple snippets)
# ---------------------------------------------------------------------------

_VIDEO_FINDER = (
    "function _fv(d){"
    "var v=d.querySelector('video')||d.querySelector('.vjs-tech');"
    "if(v)return v;"
    "var fs=d.querySelectorAll('iframe');"
    "for(var i=0;i<fs.length;i++){"
    "try{var r=_fv(fs[i].contentDocument);if(r)return r}catch(e){}"
    "}"
    "return null;"
    "}"
)

_VIDEO_FINDER_ALL = (
    "function _fvAll(d,recurse){"
    "if(recurse===undefined)recurse=true;"
    "var r=[];"
    "var vs=d.querySelectorAll('video,.vjs-tech');"
    "for(var i=0;i<vs.length;i++){"
    "var v=vs[i];"
    # Filter: exclude tiny/hidden videos (previews, thumbnails)
    "if(v.offsetWidth>100||v.offsetHeight>100)r.push(v);"
    "}"
    "if(!recurse)return r;"
    "var fs=d.querySelectorAll('iframe');"
    "for(var i=0;i<fs.length;i++){"
    "try{r=r.concat(_fvAll(fs[i].contentDocument,true));}catch(e){}"
    "}"
    "return r;"
    "}"
)

# ---------------------------------------------------------------------------
# Video detection
# ---------------------------------------------------------------------------

def video_detection_js() -> str:
    """Check if video elements exist and return count."""
    return (
        "(function(){"
        + _VIDEO_FINDER_ALL +
        "return _fvAll(document).length;"
        "})()"
    )


# ---------------------------------------------------------------------------
# Video control
# ---------------------------------------------------------------------------

def play_video_js() -> str:
    """Play video if paused."""
    return (
        "(function(){"
        + _VIDEO_FINDER +
        "var v=_fv(document);"
        "if(v&&v.paused){v.play();return true;}"
        "return false;"
        "})()"
    )


def mute_video_js() -> str:
    """Mute video."""
    return (
        "(function(){"
        + _VIDEO_FINDER +
        "var v=_fv(document);"
        "if(v){v.muted=true;return true;}"
        "return false;"
        "})()"
    )


def set_speed_js(speed: float = 2.0) -> str:
    """Set video playback speed."""
    return (
        "(function(){"
        + _VIDEO_FINDER +
        "var v=_fv(document);"
        f"if(v){{v.playbackRate={speed};setTimeout(function(){{v.play();}},300);return true;}}"
        "return false;"
        "})()"
    )


# ---------------------------------------------------------------------------
# Seek to end
# ---------------------------------------------------------------------------

def seek_to_end_js() -> str:
    """Seek video to last 2 seconds. Returns a Promise resolved by setTimeout.

    page.evaluate() will await the Promise and return True/False.
    """
    return (
        "new Promise(function(resolve){"
        + _VIDEO_FINDER +
        "var v=_fv(document);"
        "if(!v||v.duration<=10){resolve(false);return;}"
        "var target=Math.max(0,v.duration-2);"
        "v.currentTime=target;"
        "setTimeout(function(){"
        "resolve(v.currentTime>=target-1);"
        "},2000);"
        "})"
    )


# ---------------------------------------------------------------------------
# Auto-navigation (video ended → click next section)
# ---------------------------------------------------------------------------

def auto_nav_js(speed: float = 2.0) -> str:
    """Play ALL videos in the current frame at given speed and track completion.

    No seek, no watchdog — just mute + playbackRate + play.
    The global video_bypass_init_js() (registered via addInitScript) protects
    playbackRate from being reset by platform listeners.

    Each video's ended event increments window.__videosDone.
    Python monitors __videosTotal/__videosDone across ALL frames, AND checks
    task-point completion (.ans-job-icon aria-label).  When the task point is
    done it can seek-all-to-end early without waiting for natural ended.

    Args:
        speed: playbackRate to use (default 2.0, verified to work for task pts).
    """
    return (
        "(function(){"
        + _VIDEO_FINDER_ALL +
        "var videos=_fvAll(document,false);"
        "if(!videos||videos.length===0){"
        "window.__videosTotal=0;window.__videosDone=0;"
        "console.log('AUTO_NAV: no videos in this frame, done');return;"
        "}"
        f"var _speed={speed};"
        "console.log('AUTO_NAV: found '+videos.length+' video(s), speed='+_speed+'x');"
        "window.__videosTotal=videos.length;"
        "window.__videosDone=0;"
        "for(var i=0;i<videos.length;i++){"
        "(function(v,idx){"
        "if(v.__processed)return;"
        "v.__processed=true;"
        # Mute + set speed + play (no seek at all)
        "v.muted=true;"
        "v.__bypassRate=_speed;"
        "v.playbackRate=_speed;"
        "v.play().catch(function(e){"
        "console.log('AUTO_NAV: play() rejected: '+e.name);"
        "setTimeout(function(){v.muted=true;v.__bypassRate=_speed;v.playbackRate=_speed;v.play().catch(function(){});},500);"
        "});"
        "console.log('AUTO_NAV: playing video '+(idx+1)+' at '+_speed+'x');"
        # Ended → increment counter
        "v.addEventListener('ended',function(){"
        "if(v.__ended)return;"
        "v.__ended=true;"
        "window.__videosDone++;"
        "console.log('AUTO_NAV: video '+(idx+1)+' ended ('+window.__videosDone+'/'+window.__videosTotal+')');"
        "if(window.__videosDone>=window.__videosTotal){"
        "window.__autoNavDone=true;"
        "console.log('AUTO_NAV: ALL videos in this frame done');"
        "}"
        "},{once:true});"
        "console.log('AUTO_NAV: watcher installed for video '+(idx+1));"
        "})(videos[i],i);"
        "}"
        "})()"
    )


# ---------------------------------------------------------------------------
# Quiz handler (injected once, runs via setInterval)
# ---------------------------------------------------------------------------

def quiz_handler_js() -> str:
    """Inject quiz auto-answer handler (v3 — event-driven).

    Detection strategy (no hardcoded CSS class names or button text):
    1. PRIMARY: video 'pause' event → when a video pauses unexpectedly
       (not ended, not user-seeking), immediately scan for quiz inputs
    2. FALLBACK: MutationObserver watches for radio/checkbox being added
    3. FALLBACK: setInterval 1.5s periodic scan
    4. GLOBAL SCAN: finds any visible radio/checkbox, groups by common
       ancestor, finds submit button by DOM proximity (no text matching)
    5. DISMISS: finds popup-like elements by CSS computed style
       (position:fixed/absolute, high z-index) — not by class name

    Answer logic (unchanged from v2):
    - Single-choice: cycles options one by one
    - Multi-choice: tries all combos from most→least options selected
    - State resets when quiz disappears → retries video seek+speed
    """
    return (
        "(function(){"
        "if(window.__quizHandlerInstalled)return;"
        "window.__quizHandlerInstalled=true;"
        "console.log('QUIZ_HANDLER(v3): event-driven installed');"
        + _VIDEO_FINDER_ALL +

        # ===================================================================
        # 1. Quiz detection (no hardcoded selectors)
        # ===================================================================

        # Group visible inputs by common ancestor (inputs belonging to same quiz)
        "function _groupInputs(inputs){"
        "var groups=[],used={};"
        "for(var i=0;i<inputs.length;i++){"
        "if(used[i])continue;"
        "var group=[inputs[i]];used[i]=true;"
        # Walk up to find a container that holds this input
        "var anc=inputs[i].parentElement;"
        "for(var s=0;s<6&&anc&&anc!==document.body;s++)anc=anc.parentElement;"
        # Find other inputs under same ancestor
        "for(var j=i+1;j<inputs.length;j++){"
        "if(used[j])continue;"
        "if(anc&&anc.contains(inputs[j])){group.push(inputs[j]);used[j]=true;}"
        "}"
        "if(group.length>=2)groups.push(group);"
        "}"
        "return groups;"
        "}"

        # Find submit button: walk UP from inputs to find common container with a button
        # Returns the LAST visible button (usually submit is last in DOM order in forms)
        "function _findSubmit(inputs){"
        "if(!inputs||inputs.length===0)return null;"
        # Walk up from first input to find a container that has ALL inputs + a button
        "var c=inputs[0].parentElement;"
        "for(var s=0;s<8&&c&&c!==document.body;s++){"
        "var hasAll=true;"
        "for(var i=0;i<inputs.length;i++){if(!c.contains(inputs[i])){hasAll=false;break;}}"
        "if(!hasAll){c=c.parentElement;continue;}"
        # Found container with all inputs — look for submit button
        "var btns=c.querySelectorAll('button,a,input[type=button],input[type=submit],.jb_btn,.btnBlue,.ans-btn');"
        "var vis=[];"
        "for(var i=0;i<btns.length;i++){if(btns[i].offsetParent!==null)vis.push(btns[i]);}"
        "if(vis.length>0)return vis[vis.length-1];"  # last button = submit
        # Broader: any element with pointer cursor that's not an input/label
        "var all=c.querySelectorAll('*');"
        "for(var i=0;i<all.length;i++){"
        "var el=all[i];"
        "if(el.offsetParent===null)continue;"
        "var tag=el.tagName;"
        "if(tag==='INPUT'||tag==='LABEL')continue;"
        "try{var cs=window.getComputedStyle(el);"
        "if(cs&&cs.cursor==='pointer')return el;}catch(e){}"
        "}"
        "c=c.parentElement;"
        "}"
        "return null;"
        "}"

        # Global scan: find ANY visible radio/checkbox → group → find submit → return quiz
        "function _findQuiz(){"
        "var all=document.querySelectorAll('input[type=radio],input[type=checkbox]');"
        "var vis=[];"
        "for(var i=0;i<all.length;i++){if(all[i].offsetParent!==null)vis.push(all[i]);}"
        "if(vis.length<2)return null;"
        "var groups=_groupInputs(vis);"
        "for(var g=0;g<groups.length;g++){"
        "if(groups[g].length<2||groups[g].length>8)continue;"
        "var sub=_findSubmit(groups[g]);"
        "if(sub){return{inputs:groups[g],isMulti:groups[g][0].type==='checkbox',submit:sub};}"
        "}"
        "return null;"
        "}"

        # ===================================================================
        # 2. Feedback dismissal (CSS-based, no hardcoded class names)
        # ===================================================================

        "function _dismiss(){"
        "window.__dismissedFp=window.__dismissedFp||{};"
        "var now=Date.now();"
        # Find popup-like elements by computed style
        "var all=document.querySelectorAll('div,section,aside,form');"
        # Sort by z-index descending (handle highest popup first)
        "var candidates=[];"
        "for(var i=0;i<all.length;i++){"
        "var el=all[i];"
        "if(el.offsetParent===null)continue;"
        # Skip sidebar/tree/directory: has many <li> (navigation menus)
        "if(el.querySelectorAll('li').length>5)continue;"
        # Skip elements at viewport edges (sidebars, not popups)
        "var rect=el.getBoundingClientRect();"
        "if(rect.left<5||rect.right>window.innerWidth-5)continue;"
        # Text filter: only dismiss elements with popup-like text
        # (prevents clicking video player UI, sidebars, and other non-popup overlays)
        "var txt=(el.textContent||'').trim();"
        "var hasPopupTxt="
        "txt.indexOf('正确')!==-1||txt.indexOf('错误')!==-1||"
        "txt.indexOf('恭喜')!==-1||txt.indexOf('提示')!==-1||"
        "txt.indexOf('确认')!==-1||txt.indexOf('消息')!==-1||"
        "txt.indexOf('通知')!==-1||txt.indexOf('任务点未完')!==-1;"
        "if(!hasPopupTxt)continue;"
        # Skip if contains visible quiz inputs
        "var ri=el.querySelectorAll('input[type=radio],input[type=checkbox]');"
        "var hasQz=false;"
        "for(var j=0;j<ri.length;j++){if(ri[j].offsetParent!==null){hasQz=true;break;}}"
        "if(hasQz)continue;"
        # Dedup: fingerprint by tag+class+size (same element re-detected)
        "var fp=el.tagName+'_'+(el.className||'').substr(0,40)+'_'+el.offsetWidth+'x'+el.offsetHeight;"
        "if(window.__dismissedFp[fp]&&window.__dismissedFp[fp]>now-10000)continue;"
        # Check if it looks like a popup/modal
        "try{"
        "var cs=window.getComputedStyle(el);if(!cs)continue;"
        "var isPopup="
        "cs.position==='fixed'||cs.position==='absolute'||"
        "(cs.zIndex!=='auto'&&parseInt(cs.zIndex)>50)||"
        "(cs.boxShadow!=='none'&&cs.borderRadius!=='0px');"
        "if(!isPopup)continue;"
        "var zi=cs.zIndex==='auto'?0:parseInt(cs.zIndex);"
        "candidates.push({el:el,z:zi,fp:fp});"
        "}catch(e){}"
        "}"
        # Prune stale dedup entries (older than 10s)
        "var ks=Object.keys(window.__dismissedFp);"
        "for(var k=0;k<ks.length;k++){if(window.__dismissedFp[ks[k]]<now-10000)delete window.__dismissedFp[ks[k]];}"
        "candidates.sort(function(a,b){return b.z-a.z;});"  # highest z-index first
        # Try each candidate
        "for(var i=0;i<candidates.length;i++){"
        "var c=candidates[i];var el=c.el;var fp=c.fp;"
        "window.__dismissedFp[fp]=now;"
        # Skip navigation-related popups: if this popup has "下一节" or "去学习"
        # buttons, it's a navigation confirmation dialog — leave it to
        # navigate_next_js() which is specifically designed for this flow.
        # Clicking them from _dismiss just closes the popup without navigating.
        "var _btns=el.querySelectorAll('a,button');"
        "var _hasNavBtn=false;"
        "for(var _j=0;_j<_btns.length;_j++){"
        "var _t=(_btns[_j].textContent||'').trim();"
        "if(_t.indexOf('下一节')!==-1||_t.indexOf('去学习')!==-1){_hasNavBtn=true;break;}"
        "}"
        "if(_hasNavBtn){console.log('QUIZ_HANDLER: skipping nav popup');continue;}"
        # Normal dismiss: close buttons first
        "var closeBtn=el.querySelector('.popClose,.close,.btn-close,[class*=close]');"
        "if(closeBtn&&closeBtn.offsetParent!==null){closeBtn.click();console.log('QUIZ_HANDLER: dismissed via close');return true;}"
        # Fallback: any button/a (skip navigation buttons)
        "var btns=el.querySelectorAll('button,a');"
        "for(var j=0;j<btns.length;j++){"
        "if(btns[j].offsetParent!==null){"
        "var t=(btns[j].textContent||'').trim();"
        "if(t.indexOf('下一节')!==-1||t.indexOf('去学习')!==-1)continue;"
        "btns[j].click();console.log('QUIZ_HANDLER: dismissed via button');return true;"
        "}"
        "}"
        # Last resort: click the container itself
        "el.click();console.log('QUIZ_HANDLER: clicked popup container');return true;"
        "}"
        "return false;"
        "}"

        # ===================================================================
        # 3. Retry video seek after quiz
        # ===================================================================

        "function _retryVideoSeek(){"
        "var videos=_fvAll(document,false);"  # this frame only
        "if(!videos||videos.length===0)return;"
        "console.log('QUIZ_HANDLER: post-quiz seek+speed on '+videos.length+' video(s)');"
        "for(var i=0;i<videos.length;i++){"
        "(function(v,idx){"
        "if(!v.duration||v.duration<=10)return;"
        # Set flags for bypass + quiz false positive prevention
        "v.__quizSeeking=true;"
        "var target=Math.max(0,v.duration-2);"
        "v.__bypassTarget=target;"
        "v.__bypassRate=8.0;"
        "v.currentTime=target;"
        "v.playbackRate=8.0;"
        "v.muted=true;"
        "v.play().catch(function(){});"
        "console.log('QUIZ_HANDLER: video '+idx+' seek→'+target+' rate→2x');"
        # Clear flags after 3s
        "setTimeout(function(){v.__quizSeeking=false;},3000);"
        "})(videos[i],i);"
        "}"
        "}"

        # ===================================================================
        # 4. Video pause listener (primary quiz signal)
        # ===================================================================

        "function _watchVideo(v){"
        "if(v.__quizWatched)return;"
        "v.__quizWatched=true;"
        "v.addEventListener('pause',function(){"
        # Ignore: video ended, or our own seek triggered the pause
        "if(v.ended||v.__quizSeeking)return;"
        "console.log('QUIZ_HANDLER: video paused unexpectedly → scan for quiz');"
        "setTimeout(_scanAndAnswer,200);"
        "});"
        "console.log('QUIZ_HANDLER: pause listener attached to video');"
        "}"

        "function _watchAllVideos(){"
        "var videos=_fvAll(document,false);"  # this frame only
        "for(var i=0;i<videos.length;i++)_watchVideo(videos[i]);"
        "}"

        # ===================================================================
        # 5. Quiz state machine + answer logic
        # ===================================================================

        "var _st=null;"

        # Combination generator
        "function _gc(n){"
        "var r=[];"
        "for(var k=n;k>=1;k--){"
        "var idx=[];"
        "for(var i=0;i<k;i++)idx.push(i);"
        "r.push(idx.slice());"
        "while(true){"
        "var p;"
        "for(p=k-1;p>=0;p--){if(idx[p]<n-k+p)break;}"
        "if(p<0)break;"
        "idx[p]++;"
        "for(var j=p+1;j<k;j++)idx[j]=idx[j-1]+1;"
        "r.push(idx.slice());"
        "}"
        "}"
        "return r;"
        "}"

        "function _handleQuiz(q){"
        "if(_st&&(_st.isMulti!==q.isMulti||_st.nInputs!==q.inputs.length)){"
        "console.log('QUIZ_HANDLER: quiz changed, reset state');_st=null;"
        "}"
        "if(!_st){"
        "_st={isMulti:q.isMulti,nInputs:q.inputs.length,attempted:[],combos:q.isMulti?_gc(q.inputs.length):null,ci:0,done:false,waiting:false};"
        "}"
        "if(_st.done||_st.waiting)return;"
        "_st.waiting=true;"
        "var st=_st;"  # captured ref survives _st=null reset

        "if(st.isMulti){"
        "if(_st.ci<_st.combos.length){"
        "var combo=_st.combos[_st.ci];_st.ci++;"
        "console.log('QUIZ_HANDLER: multi combo',combo);"
        "for(var i=0;i<q.inputs.length;i++)q.inputs[i].checked=false;"
        "for(var i=0;i<combo.length;i++)q.inputs[combo[i]].checked=true;"
        "setTimeout(function(){q.submit.click();console.log('QUIZ_HANDLER: submitted multi');"
        "setTimeout(function(){_dismiss();st.waiting=false;},2000);},500);"
        "}else{_st.done=true;_st.waiting=false;console.log('QUIZ_HANDLER: multi exhausted');}"
        "}else{"
        "var found=false;"
        "for(var i=0;i<q.inputs.length;i++){"
        "if(_st.attempted.indexOf(i)===-1){"
        "q.inputs[i].checked=true;_st.attempted.push(i);found=true;"
        "console.log('QUIZ_HANDLER: single attempt '+i+'/'+q.inputs.length);"
        "setTimeout(function(){q.submit.click();console.log('QUIZ_HANDLER: submitted single');"
        "setTimeout(function(){_dismiss();st.waiting=false;},2000);},500);break;"
        "}"
        "}"
        "if(!found){_st.done=true;_st.waiting=false;console.log('QUIZ_HANDLER: single exhausted');}"
        "}"
        "}"

        # ===================================================================
        # 6. Scan + tick
        # ===================================================================

        "function _scanAndAnswer(){"
        "if(_st&&_st.waiting)return;"  # still processing previous quiz
        "var q=_findQuiz();"
        "if(!q)return;"
        "_hadQuiz=true;"
        "console.log('QUIZ_HANDLER: quiz detected — '+q.inputs.length+' inputs, multi='+q.isMulti);"
        "_handleQuiz(q);"
        "}"

        "var _hadQuiz=false;"
        "function _tick(){"
        "_watchAllVideos();"  # attach pause listeners to any new videos
        "_scanAndAnswer();"
        # If no active quiz processing, dismiss popups + retry seek
        "if(!_st||!_st.waiting){"
        "_dismiss();"
        "if(_hadQuiz){"
        "_hadQuiz=false;_st=null;"
        "console.log('QUIZ_HANDLER: quiz gone, retrying video seek');"
        "_retryVideoSeek();"
        "}"
        "}"
        "}"

        # ===================================================================
        # 7. Setup: observe + poll + attach
        # ===================================================================

        "_watchAllVideos();"
        "setInterval(_tick,1500);"

        # MutationObserver: new videos or new quiz inputs
        "var _obs=new MutationObserver(function(muts){"
        "for(var i=0;i<muts.length;i++){"
        "for(var j=0;j<muts[i].addedNodes.length;j++){"
        "var n=muts[i].addedNodes[j];"
        "if(n.nodeType!==1||!n.querySelectorAll)continue;"
        # New video elements → attach pause listeners
        "var newVids=n.querySelectorAll('video,.vjs-tech');"
        "if(newVids.length>0){console.log('QUIZ_HANDLER: new video detected');_watchAllVideos();}"
        # New radio/checkbox → may be quiz
        "var ri=n.querySelectorAll('input[type=radio],input[type=checkbox]');"
        "if(ri.length>=2){console.log('QUIZ_HANDLER: MutationObserver saw inputs');setTimeout(_scanAndAnswer,300);}"
        "}"
        "}"
        "});"
        "_obs.observe(document.body,{childList:true,subtree:true});"

        "setTimeout(_scanAndAnswer,500);"
        "console.log('QUIZ_HANDLER(v3): ready (event-driven: pause+observer+poll)');"
        "})()"
    )


# ---------------------------------------------------------------------------
# Section navigation (DOM-based, no video required)
# ---------------------------------------------------------------------------

def navigate_next_js() -> str:
    """Find and click the next-section button via DOM search.

    Fixes:
    - Only sets __autoNavDone when URL actually changes (no premature success).
    - Detects "任务点未完成" popup and reports __autoNavFailedReason so
      Python knows navigation was blocked instead of assuming success.
    - Retries popup 下一节 button click once if needed.
    - Scrolls page + iframe#panView to bottom so nav buttons are visible.
    """
    return (
        "(function(){"
        "window.__autoNavDone=false;"
        "window.__autoNavFailedReason=null;"
        "try{sessionStorage.removeItem('__autoNavDone');}catch(e){}"
        "var _urlBefore=location.href;"
        "var _clicked=false;"
        "var _popupClickCount=0;"
        "var _popupClickMax=6;"
        "var _startTime=Date.now();"
        # 滚动 PPT 内容到底部
        # 只在 panView frame 内滚动 documentElement
        # 在主 frame 中 documentElement 是主页面，不能滚动它！
        "function _scrollAll(){"
        # 判断是否在 panView frame（PPT 内容的真正所在 frame）
        "var _isPanView=location.href.indexOf('pan-yz.chaoxing.com')!==-1||location.href.indexOf('screen/v2/file')!==-1;"
        # 只在 panView frame 内滚动 documentElement
        "if(_isPanView){"
        "var _de=document.documentElement;"
        "if(_de){"
        "var _ms=_de.scrollHeight-_de.clientHeight;"
        "if(_ms>0){"
        "_de.scrollTop=_ms;"
        "console.log('JS_NAV_SCROLL: documentElement scrollTop → '+_de.scrollTop+'/'+_ms);"
        "if(_de.scrollTop<=0){"
        "try{window.scrollTo(0,_ms);"
        "console.log('JS_NAV_SCROLL: window.scrollTo → '+window.scrollY);"
        "}catch(e){}"
        "}"
        "}"
        "}"
        "}"
        # .fileBox 兜底（其他页面类型可能仍用 .fileBox）
        "var _fbs=document.querySelectorAll('.fileBox');"
        "for(var i=0;i<_fbs.length;i++){"
        "var _fb=_fbs[i];var _ms2=_fb.scrollHeight-_fb.clientHeight;"
        "if(_ms2<=0)continue;"
        "try{_fb.style.overflowY='auto';}catch(e){}"
        "_fb.scrollTop=_fb.scrollHeight;"
        "}"
        "}"
        "_scrollAll();"
        # Find the "task unfinished" popup and its 下一节 button
        "function _findPopupInfo(){"
        "var all=document.querySelectorAll('div,section,aside,form');"
        "var best=null,bestZ=0,hasTaskUnfinished=false;"
        "for(var i=0;i<all.length;i++){"
        "var el=all[i];"
        "if(el.offsetParent===null)continue;"
        "var rect=el.getBoundingClientRect();"
        "if(rect.left<5||rect.right>window.innerWidth-5)continue;"
        "var txt=(el.textContent||'');"
        # Only care about popups that mention unfinished tasks
        "if(txt.indexOf('任务点未完')===-1)continue;"
        "try{"
        "var cs=window.getComputedStyle(el);if(!cs)continue;"
        "var isPopup=cs.position==='fixed'||cs.position==='absolute'||"
        "(cs.zIndex!=='auto'&&parseInt(cs.zIndex)>50)||"
        "(cs.boxShadow!=='none'&&cs.borderRadius!=='0px');"
        "if(!isPopup)continue;"
        "var zi=cs.zIndex==='auto'?0:parseInt(cs.zIndex);"
        "}catch(e){continue;}"
        "hasTaskUnfinished=true;"
        "var nc=el.querySelector('.nextChapter');"
        "if(nc&&nc.offsetParent!==null&&zi>bestZ){best=nc;bestZ=zi;}"
        "var links=el.querySelectorAll('a,button');"
        "for(var j=0;j<links.length;j++){"
        "var t=(links[j].textContent||'').trim();"
        "if(t.indexOf('下一节')!==-1&&links[j].offsetParent!==null&&zi>bestZ){"
        "best=links[j];bestZ=zi;"
        "}"
        "}"
        "}"
        "return {btn:best,hasTaskUnfinished:hasTaskUnfinished,onclick:(best?best.getAttribute('onclick'):null)};"
        "}"
        # Normal nav button search
        "function _findNavBtn(){"
        "var b=document.getElementById('prevNextFocusNext');"
        "if(!b||b.offsetParent===null){b=document.querySelector('.nextChapter');}"
        "if(!b||b.offsetParent===null){"
        "var all=document.querySelectorAll('a,button,span,div,li');"
        "for(var i=0;i<all.length;i++){"
        "var t=(all[i].textContent||'').trim();"
        "if(all[i].offsetParent!==null&&(t.indexOf('下一节')!==-1||t.indexOf('下一个')!==-1||t==='继续')){"
        "b=all[i];break;"
        "}"
        "}"
        "}"
        "return b;"
        "}"
        # Poll loop
        "function _poll(){"
        "var elapsed=Date.now()-_startTime;"
        # Success: URL changed
        "if(location.href!==_urlBefore){"
        "window.__autoNavDone=true;try{sessionStorage.setItem('__autoNavDone','1');}catch(e){}"
        "console.log('JS_NAV: success (URL changed)');return;"
        "}"
        # Timeout
        "if(elapsed>45000){"
        "console.log('JS_NAV: timeout');return;"
        "}"
        # Check popup first
        "var popup=_findPopupInfo();"
        # If popup has a "下一节" button → multi-method click + eval full onclick
        "if(popup.btn&&_popupClickCount<_popupClickMax){"
        "_popupClickCount++;"
        "window.__autoNavFailedReason=null;"
        # Method 1: eval 完整 onclick（含 closeDeleteWindow + PCount.next）
        "try{"
        "if(popup.onclick&&popup.onclick.length>0){"
        "eval(popup.onclick);"
        "console.log('JS_NAV: eval full onclick → '+popup.onclick.substring(0,60));"
        "}"
        "}catch(e){console.log('JS_NAV: eval onclick failed: '+e);}"
        # Method 2: plain .click()
        "try{popup.btn.click();}catch(e){}"
        # Method 3: dispatch real MouseEvent (works where .click() doesn't on <a>)
        "try{popup.btn.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window}));}catch(e){}"
        "console.log('JS_NAV: clicked popup next (attempt '+_popupClickCount+'/'+_popupClickMax+')');"
        "setTimeout(_poll,800);return;"
        "}"
        # No clickable button but popup says task unfinished → report failure
        "if(popup.hasTaskUnfinished&&_popupClickCount>=_popupClickMax){"
        "window.__autoNavFailedReason='task_unfinished';"
        "console.log('JS_NAV: popup says task unfinished, exhausted retries');"
        "setTimeout(_poll,800);return;"
        "}"
        # Click main nav button
        "if(!_clicked){"
        "if(elapsed%3000<800)_scrollAll();"  # re-scroll every ~3s in case content loaded
        "var b=_findNavBtn();"
        "if(b&&b.offsetParent!==null){"
        "b.click();_clicked=true;"
        "console.log('JS_NAV: clicked main next');"
        "setTimeout(_poll,800);return;"
        "}"
        "}"
        "setTimeout(_poll,800);"
        "}"
        "_poll();"
        "})()"
    )


# ---------------------------------------------------------------------------
# Markers (clear / sync)
# ---------------------------------------------------------------------------

def clear_nav_marker_js() -> str:
    """Clear stale __autoNavDone from sessionStorage and window."""
    return (
        "(function(){"
        "try{sessionStorage.removeItem('__autoNavDone');}catch(e){}"
        "window.__autoNavDone=false;"
        "})()"
    )


# ---------------------------------------------------------------------------
# Video restriction bypass (addInitScript)
# ---------------------------------------------------------------------------

def video_bypass_init_js() -> str:
    """Comprehensive bypass of video restriction mechanisms.

    Two-layer defense:
    1. Property-setter level: intercepts currentTime/playbackRate setters on
       HTMLMediaElement.prototype. Uses __bypassTarget/__bypassRate flags to
       distinguish our changes from platform resets. Works against ALL reset
       methods (addEventListener, direct assignment, defineProperty).
    2. Event-listener level: blocks seeked/seeking/ratechange listeners that
       attempt to modify currentTime or playbackRate (backup defense).
    """
    return (
        "(function(){"
        # === Layer 1: Property setter interception ===
        "var _ctDesc=Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype,'currentTime');"
        "var _prDesc=Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype,'playbackRate');"
        # Hook currentTime setter
        "if(_ctDesc&&_ctDesc.set){"
        "var _origSetCT=_ctDesc.set;"
        "Object.defineProperty(HTMLMediaElement.prototype,'currentTime',{"
        "get:_ctDesc.get,"
        "set:function(value){"
        "if(this.__bypassTarget!==undefined){"
        # Our seek (value close to target) → allow
        "if(Math.abs(value-this.__bypassTarget)<5){_origSetCT.call(this,value);return;}"
        # Platform resetting backward → block
        "if(value<this.__bypassTarget-10){console.log('[BYPASS] blocked ct reset: '+value+' (target='+this.__bypassTarget+')');return;}"
        "}"
        "_origSetCT.call(this,value);"
        "},configurable:true});"
        "}"
        # Hook playbackRate setter
        "if(_prDesc&&_prDesc.set){"
        "var _origSetPR=_prDesc.set;"
        "Object.defineProperty(HTMLMediaElement.prototype,'playbackRate',{"
        "get:_prDesc.get,"
        "set:function(value){"
        "if(this.__bypassRate!==undefined){"
        # Our speed change → allow
        "if(value===this.__bypassRate||value>=2.0){_origSetPR.call(this,value);return;}"
        # Platform resetting to 1.0 → block
        "if(value<1.5){console.log('[BYPASS] blocked rate reset: '+value+' (keeping '+this.__bypassRate+')');return;}"
        "}"
        "_origSetPR.call(this,value);"
        "},configurable:true});"
        "}"
        # === Layer 2: Event listener blocking (backup) ===
        "var _origAddEL=HTMLMediaElement.prototype.addEventListener;"
        "HTMLMediaElement.prototype.addEventListener=function(type,fn,opts){"
        "if(type==='seeked'||type==='seeking'||type==='ratechange'){"
        "var s=fn.toString();"
        # Block handlers that RESET currentTime or playbackRate
        "if((s.indexOf('currentTime')!==-1||s.indexOf('playbackRate')!==-1)&&s.indexOf('_0x')!==-1){"
        "console.log('[BYPASS] blocked restriction listener: '+type);"
        "return;"
        "}"
        "}"
        "return _origAddEL.call(this,type,fn,opts);"
        "};"
        "console.log('[BYPASS] comprehensive bypass active');"
        "})()"
    )


def scroll_to_bottom_js() -> str:
    """滚动 PPT 内容到底部 — 针对 panView iframe 的 documentElement。

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
                                 └─ .fileBox (scrollH=clientH=4860，完全展开，无内部滚动)

    关键发现：
      - .fileBox 的 scrollHeight === clientHeight，完全没有可滚动空间
      - #content1 是主页面滚动容器，滚动它会移动整个页面而非 PPT 内容
      - PPT 内容的滚动在 panView iframe 的 document.documentElement 上
      - panView frame 使用原生滚动（body overflow=auto），无 nicescroll
      - panView 是跨域 iframe（pan-yz.chaoxing.com），JS 无法跨域访问
      - 必须由 Playwright 在正确的 frame 上执行 evaluate

    滚动策略（在 panView frame 内执行，绝不使用 wheel 事件避免冒泡到父 frame）：
    1. 判断当前是否在 panView frame（pan-yz.chaoxing.com 或 screen/v2/file）
    2. 仅在 panView frame 内滚动 documentElement
    3. 非 panView frame 只尝试 .fileBox 兜底
    4. 这样避免在主 frame 滚动 documentElement 导致主页面滚动

    返回值：滚动距离（>0 表示成功，0 表示失败）
    """
    return (
        "(function(){"
        # 判断是否在 panView frame（PPT 内容的真正所在 frame）
        "var _isPanView=location.href.indexOf('pan-yz.chaoxing.com')!==-1||location.href.indexOf('screen/v2/file')!==-1;"
        # 只在 panView frame 内滚动 documentElement
        # 在主 frame 中 documentElement 是主页面，不能滚动它！
        "if(_isPanView){"
        "var de=document.documentElement;"
        "if(de){"
        "var maxScroll=de.scrollHeight-de.clientHeight;"
        "if(maxScroll>0){"
        "de.scrollTop=maxScroll;"
        "if(de.scrollTop>0){"
        "console.log('SCROLL: documentElement scrollTop → '+de.scrollTop+'/'+maxScroll);"
        "return de.scrollTop;"
        "}"
        "try{window.scrollTo(0,maxScroll);"
        "if(window.scrollY>0){"
        "console.log('SCROLL: window.scrollTo → '+window.scrollY);"
        "return window.scrollY;"
        "}"
        "}catch(e){}"
        "try{var se=document.scrollingElement;if(se){"
        "se.scrollTop=se.scrollHeight;"
        "if(se.scrollTop>0){"
        "console.log('SCROLL: scrollingElement → '+se.scrollTop);"
        "return se.scrollTop;"
        "}"
        "}}catch(e){}"
        "}"
        "}"
        "}"
        # .fileBox 兜底（其他页面类型或非 panView frame 可能仍用 .fileBox）
        "var fbs=document.querySelectorAll('.fileBox');"
        "for(var i=0;i<fbs.length;i++){"
        "var fb=fbs[i];"
        "var maxScroll=fb.scrollHeight-fb.clientHeight;"
        "if(maxScroll<=0)continue;"
        "try{fb.style.overflowY='auto';}catch(e){}"
        "fb.scrollTop=fb.scrollHeight;"
        "if(fb.scrollTop>0){"
        "console.log('SCROLL: .fileBox scrollTop → '+fb.scrollTop);"
        "return fb.scrollTop;"
        "}"
        "}"
        "console.log('SCROLL: no scrollable container found');"
        "return 0;"
        "})()"
    )


def scroll_ppt_gradually_js() -> str:
    """逐步滚动 PPT 内容到底部，通过 scrollTop 逐步递增模拟真实滚动。

    真实 DOM 结构（通过逐层诊断确认）：
      顶层 frame → #content1 (主页面滚动容器，不要动！)
        → iframe → iframe → iframe#panView (pan-yz.chaoxing.com/screen/v2/...)
          → document.documentElement (scrollH=4860, clientH=546, 可滚动=4314)
            → .fileBox (完全展开，无内部滚动)

    PPT 内容的滚动在 panView iframe 的 document.documentElement 上，
    使用原生滚动（body overflow=auto），无 nicescroll。
    必须由 Playwright 在正确的 frame 上执行 evaluate。

    ⚠️ 绝不使用 WheelEvent，因为 wheel 事件会冒泡到父 frame 导致主页面滚动！
    改用逐步递增 scrollTop 的方式模拟滚动，每步 200px，间隔 80ms。
    返回 Promise，滚动完毕后 resolve。
    """
    return (
        "new Promise(function(resolve){"
        # 判断是否在 panView frame（只在 panView frame 内滚动 documentElement）
        "var _isPanView=location.href.indexOf('pan-yz.chaoxing.com')!==-1||location.href.indexOf('screen/v2/file')!==-1;"
        # 查找滚动目标：仅在 panView frame 内滚动 documentElement
        "function _find(doc){"
        "var targets=[];"
        "if(_isPanView){"
        "var de=doc.documentElement;"
        "if(de){"
        "var total=de.scrollHeight-de.clientHeight;"
        "if(total>0)targets.push({el:de,total:total,cur:0,id:'documentElement'});"
        "}"
        "}"
        "var fbs=doc.querySelectorAll('.fileBox');"
        "for(var i=0;i<fbs.length;i++){"
        "var fb=fbs[i];"
        "var total=fb.scrollHeight-fb.clientHeight;"
        "if(total>0)targets.push({el:fb,total:total,cur:0,id:'.fileBox'});"
        "}"
        "return targets;"
        "}"
        "var targets=_find(document);"
        "if(targets.length===0){resolve(0);return;}"
        # 逐步递增 scrollTop 模拟滚动（不用 wheel 事件，避免冒泡到父 frame）
        "var step=200,delay=80;"
        "function _tick(){"
        "var allDone=true;"
        "for(var i=0;i<targets.length;i++){"
        "var t=targets[i];"
        "if(t.cur>=t.total)continue;"
        "allDone=false;"
        "t.cur+=step;"
        "if(t.cur>t.total)t.cur=t.total;"
        "t.el.scrollTop=t.cur;"
        "}"
        "if(allDone){resolve(targets.length);return;}"
        "setTimeout(_tick,delay);"
        "}"
        "_tick();"
        "})"
    )


def detect_popup_js() -> str:
    """检测页面是否存在「任务点未完成」弹窗。

    真实弹窗文本（通过诊断确认）：
      "当前章节还有任务点未完" — 注意是"未完"不是"未完成"！
      弹窗在顶层 frame（studentstudy 页面），不在 iframe 内。
      .nextChapter 按钮的 onclick: closeDeleteWindow();PCount.next(...)

    诊断发现页面有 10 个 .popDiv，只有部分含 .nextChapter 按钮。
    不能在第一个匹配就 break，必须遍历所有找到含按钮的那个。

    返回 {found: bool, hasNextChapter: bool} 字典。
    """
    return (
        "(function(){"
        "var found=false,hasNextChapter=false;"
        "var all=document.querySelectorAll('.popDiv,div,section');"
        "for(var i=0;i<all.length;i++){"
        "var el=all[i];"
        "if(el.offsetParent===null)continue;"
        "var txt=(el.textContent||'');"
        # 匹配"任务点未完"（涵盖"未完"和"未完成"两种情况）
        "if(txt.indexOf('任务点未完')===-1)continue;"
        "try{"
        "var cs=window.getComputedStyle(el);if(!cs)continue;"
        "var isPopup=cs.position==='fixed'||cs.position==='absolute'||"
        "(cs.zIndex!=='auto'&&parseInt(cs.zIndex)>50);"
        "if(!isPopup)continue;"
        "found=true;"
        # 检查此弹窗是否含 .nextChapter 按钮
        "var nc=el.querySelector('.nextChapter');"
        "if(nc&&nc.offsetParent!==null)hasNextChapter=true;"
        "var links=el.querySelectorAll('a,button');"
        "for(var j=0;j<links.length;j++){"
        "var t=(links[j].textContent||'').trim();"
        "if(t.indexOf('下一节')!==-1&&links[j].offsetParent!==null)hasNextChapter=true;"
        "}"
        # 不 break，继续遍历其他弹窗（页面有多个 .popDiv）
        "}catch(e){}"
        "}"
        "return {found:found,hasNextChapter:hasNextChapter};"
        "})()"
    )


def check_nav_marker_js() -> str:
    """Check if auto-nav has completed or failed deterministically.

    Returns true when either:
    - Navigation succeeded (__autoNavDone === true)
    - Navigation was blocked by unfinished task (__autoNavFailedReason === 'task_unfinished')
    """
    return "!!window.__autoNavDone || window.__autoNavFailedReason === 'task_unfinished'"


def video_progress_js() -> str:
    """Return current video progress: {total, done} dict."""
    return (
        "({"
        "total:window.__videosTotal||0,"
        "done:window.__videosDone||0"
        "})"
    )


def task_point_status_js() -> str:
    """Check task-point completion by reading .ans-job-icon aria-label.

    Returns {total, unfinished} dict.
    """
    return (
        "(function(){"
        "var icons=document.querySelectorAll('.ans-job-icon');"
        "var unfinished=0,total=icons.length;"
        "for(var i=0;i<icons.length;i++){"
        "var label=icons[i].getAttribute('aria-label')||'';"
        "if(label.indexOf('任务点未完')!==-1)unfinished++;"
        "}"
        "return {total:total,unfinished:unfinished};"
        "})()"
    )


def retry_video_high_speed_js() -> str:
    """Replay ended videos from 0 at 16x to accumulate valid watch time.

    Only acts on videos that have already ended (__ended flag set) and
    have not yet been retried (__retrying flag).  The high playbackRate
    combined with continuous playback lets timeupdate / heartbeat APIs
    accumulate enough duration for the 90% task-point requirement.
    """
    return (
        "(function(){"
        + _VIDEO_FINDER_ALL +
        "var videos=_fvAll(document,false);"
        "if(!videos||videos.length===0)return 0;"
        "var count=0;"
        "for(var i=0;i<videos.length;i++){"
        "var v=videos[i];"
        "if(v.__ended&&!v.__retrying){"
        "v.__retrying=true;"
        "v.muted=true;"
        "v.currentTime=0;"
        "v.__bypassRate=16.0;"
        "v.playbackRate=16.0;"
        "v.play().catch(function(){});"
        "count++;"
        "console.log('RETRY_HS: video '+i+' replay at 16x from 0');"
        # Also add an ended listener so __videosDone keeps counting
        "v.addEventListener('ended',function(){"
        "window.__videosDone++;"
        "console.log('RETRY_HS: video '+i+' re-ended ('+window.__videosDone+'/'+window.__videosTotal+')');"
        "if(window.__videosDone>=window.__videosTotal){"
        "window.__autoNavDone=true;"
        "try{sessionStorage.setItem('__autoNavDone','1');}catch(e){}"
        "}"
        "},{once:true});"
        "}"
        "}"
        "return count;"
        "})()"
    )


def seek_all_videos_to_end_js() -> str:
    """Seek all video elements in this frame to their end.

    Used by Python when the task point is already completed, so we can
    terminate playback early instead of waiting for natural ended.
    """
    return (
        "(function(){"
        "var vs=document.querySelectorAll('video,.vjs-tech');"
        "var n=0;"
        "for(var i=0;i<vs.length;i++){"
        "if(vs[i].duration&&!isNaN(vs[i].duration)){"
        "vs[i].muted=true;"
        "vs[i].currentTime=vs[i].duration;"
        "n++;"
        "}"
        "}"
        "return n;"
        "})()"
    )