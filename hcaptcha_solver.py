import asyncio
import time
from urllib.parse import urlsplit

_GRID = 4
_SKIP_SEL = ".button-submit"


def _route_glob(url: str) -> str:
    parts = urlsplit(url)
    if parts.path in ("", "/"):
        return f"{parts.scheme}://{parts.netloc}/**"
    return url


def _build_checkbox_page(sitekey: str) -> str:
    return """<!DOCTYPE html><html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>hCaptcha Solver</title>
<style>*{margin:0;padding:0;box-sizing:border-box}
body{background:#1a1a1a;display:flex;justify-content:center;align-items:center;min-height:100vh}</style>
</head><body>
<div class="h-captcha" data-sitekey="__SK__"></div>
<script src="https://js.hcaptcha.com/1/api.js" async defer></script>
</body></html>""".replace("__SK__", sitekey)


def _build_invisible_page(sitekey: str) -> str:
    return """<!DOCTYPE html><html><head>
<script src="https://js.hcaptcha.com/1/api.js?onload=onloadHCaptcha&render=explicit" async defer></script>
</head><body>
<script>
  window.__token = ""; window.__err = "";
  function onloadHCaptcha() {
    try {
      var wid = hcaptcha.render('hcaptcha-container', {
        sitekey: '__SK__',
        size: 'invisible',
        callback: function(t) { window.__token = t; },
        'error-callback': function(e) { window.__err = String(e); },
        'expired-callback': function() { window.__err = 'expired'; },
      });
      setTimeout(function() { hcaptcha.execute(wid); }, 300);
    } catch(e) { window.__err = String(e); }
  }
</script>
<div id="hcaptcha-container"></div>
</body></html>""".replace("__SK__", sitekey)


def _find_challenge_frame(page):
    for fr in page.frames:
        u = fr.url or ""
        if "#frame=challenge" in u and "hcaptcha" in u:
            return fr
    return None


async def _get_token(page) -> str:
    try:
        t = await page.evaluate(
            "() => (document.querySelector('[name=h-captcha-response]') || {}).value || ''")
        if t:
            return t
    except Exception:
        pass
    try:
        t = await page.evaluate(
            "() => { try { return hcaptcha.getResponse() || ''; } catch(e) { return ''; } }")
        return t or ""
    except Exception:
        return ""


async def _click_checkbox(page, attempts: int = 20) -> bool:
    for _ in range(attempts):
        for fr in page.frames:
            if "#frame=checkbox" in (fr.url or ""):
                for sel in ("#checkbox", "div[role=checkbox]", "label", "body"):
                    try:
                        await fr.click(sel, timeout=2000)
                        return True
                    except Exception:
                        continue
        await asyncio.sleep(1)
    return False


async def _close_challenge(page) -> None:
    fr = _find_challenge_frame(page)
    if not fr:
        return
    try:
        btn = await fr.query_selector(_SKIP_SEL)
        if btn:
            text = (await btn.inner_text()).lower()
            if text in ("skip", "跳过", "huppel", "ohita", "überspringen"):
                await btn.click(timeout=3000)
                await asyncio.sleep(2)
                return
        close = await fr.query_selector(".close.button")
        if close:
            await close.click(timeout=3000)
            await asyncio.sleep(1)
    except Exception:
        pass


async def _solve_invisible(page, url, sitekey) -> dict:
    t0 = time.monotonic()
    body = _build_invisible_page(sitekey)
    try:
        await page.unroute_all()
    except Exception:
        pass
    await page.route(_route_glob(url), lambda r: r.fulfill(body=body, status=200))
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        await asyncio.sleep(1)
        try:
            tok = await page.evaluate("() => window.__token || ''")
            if tok:
                return {"token": tok, "method": "invisible",
                        "elapsed": round(time.monotonic() - t0, 1)}
            err = await page.evaluate("() => window.__err || ''")
            if err:
                return {"error": err, "elapsed": round(time.monotonic() - t0, 1)}
        except Exception:
            pass
    return {"error": "hcaptcha.execute() timed out",
            "elapsed": round(time.monotonic() - t0, 1)}


async def solve_hcaptcha(page, url, sitekey, version="checkbox",
                         max_attempts=3) -> dict:
    t0 = time.monotonic()
    if version == "invisible":
        return await _solve_invisible(page, url, sitekey)

    body = _build_checkbox_page(sitekey)
    try:
        await page.unroute_all()
    except Exception:
        pass
    await page.route(_route_glob(url), lambda r: r.fulfill(body=body, status=200))
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    for attempt in range(1, max_attempts + 1):
        token = await _get_token(page)
        if token:
            return {"token": token, "method": "auto",
                    "elapsed": round(time.monotonic() - t0, 1)}
        await _close_challenge(page)
        clicked = await _click_checkbox(page)
        await asyncio.sleep(3)
        fr = _find_challenge_frame(page)
        if fr:
            try:
                await fr.locator("canvas").count()
            except Exception:
                pass
        token = await _get_token(page)
        if token:
            return {"token": token, "method": "checkbox",
                    "elapsed": round(time.monotonic() - t0, 1)}
        await asyncio.sleep(3 * attempt)

    return {"error": "no hcaptcha token obtained",
            "elapsed": round(time.monotonic() - t0, 1)}
