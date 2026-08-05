import asyncio
import base64
import io
import time
from urllib.parse import urlsplit

_ANCHOR_IFRAME = "iframe[title='reCAPTCHA']"
_BFRAME_IFRAME = "iframe[title*='recaptcha challenge']"


def _route_glob(url: str) -> str:
    parts = urlsplit(url)
    if parts.path in ("", "/"):
        return f"{parts.scheme}://{parts.netloc}/**"
    return url


def _build_checkbox_page(sitekey: str, enterprise: bool = False) -> str:
    lib = "enterprise.js" if enterprise else "api.js"
    return """<!DOCTYPE html><html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>reCAPTCHA Solver</title>
<style>*{margin:0;padding:0;box-sizing:border-box}
body{background:#1a1a1a;display:flex;justify-content:center;align-items:center;min-height:100vh}</style>
</head><body>
<div class="g-recaptcha" data-sitekey="__SK__"></div>
<script src="https://www.google.com/recaptcha/__LIB__" async defer></script>
</body></html>""".replace("__SK__", sitekey).replace("__LIB__", lib)


def _build_execute_page(sitekey: str, action: str, enterprise: bool = False) -> str:
    lib = "enterprise.js" if enterprise else "api.js"
    ns = "grecaptcha.enterprise" if enterprise else "grecaptcha"
    return """<!DOCTYPE html><html><head>
<script src="https://www.google.com/recaptcha/__LIB__?render=__SK__"></script>
</head><body><div id="out">waiting</div>
<script>
  window.__token = ""; window.__err = "";
  var gre = __NS__;
  gre.ready(function () {
    gre.execute("__SK__", {action: "__ACTION__"})
      .then(function (t) { window.__token = t; })
      .catch(function (e) { window.__err = String(e); });
  });
</script></body></html>""".replace("__LIB__", lib).replace("__NS__", ns).replace(
        "__SK__", sitekey).replace("__ACTION__", action or "submit")


async def _get_token(page) -> str:
    try:
        return await page.evaluate(
            "() => document.querySelector('#g-recaptcha-response')?.value || ''")
    except Exception:
        return ""


async def _find_bframe(page):
    for fr in page.frames:
        if "/bframe" in (fr.url or ""):
            return fr
    return None


async def _challenge_meta(bf) -> dict:
    try:
        return await bf.evaluate("""() => {
            const t = document.querySelector('table');
            const desc = document.querySelector(
                '.rc-imageselect-desc-no-canonical, .rc-imageselect-desc');
            const strong = desc?.querySelector('strong')?.innerText;
            return {
                target: strong || (desc ? desc.innerText.split('\\n')[0] : ''),
                rows: t ? t.rows.length : 0,
                has_table: !!t,
            };
        }""")
    except Exception:
        return {"target": "", "rows": 0, "has_table": False}


def _classify_tile(clf, tile_bytes, target) -> bool:
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(tile_bytes)).convert("RGB")
    except Exception:
        return False
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return clf.classify(base64.b64encode(buf.getvalue()).decode(), target)


async def _classify_and_submit(page, clf) -> bool:
    bf = await _find_bframe(page)
    if not bf or not clf:
        return False
    meta = await _challenge_meta(bf)
    target = meta.get("target", "")
    if not meta.get("has_table") or not target:
        return False
    try:
        tiles = await bf.query_selector_all("table td[role=button], .rc-imageselect-tile")
        if not tiles:
            tiles = await bf.query_selector_all("td")
    except Exception:
        return False

    positives = []
    for idx, tile in enumerate(tiles):
        try:
            png = await asyncio.wait_for(tile.screenshot(), timeout=6)
        except Exception:
            continue
        if await asyncio.to_thread(_classify_tile, clf, png, target):
            positives.append(idx)
    for idx in positives:
        if idx < len(tiles):
            try:
                await tiles[idx].click(timeout=3000)
            except Exception:
                pass
    await asyncio.sleep(2)
    try:
        await page.frame_locator(_BFRAME_IFRAME).locator(
            "#recaptcha-verify-button").click(timeout=4000, force=True)
    except Exception:
        pass
    await asyncio.sleep(3)
    return True


async def _solve_invisible(page, url, sitekey, action, enterprise) -> dict:
    t0 = time.monotonic()
    body = _build_execute_page(sitekey, action, enterprise)
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
    return {"error": "execute() timed out", "elapsed": round(time.monotonic() - t0, 1)}


async def solve_recaptcha_v2(page, url, sitekey, enterprise=False,
                             version="checkbox", action="submit",
                             classifier="auto", max_rounds=3) -> dict:
    t0 = time.monotonic()
    if version == "invisible":
        return await _solve_invisible(page, url, sitekey, action, enterprise)

        import recaptcha_classifier
    clf = recaptcha_classifier.get_classifier() if classifier in ("auto", "onnx", "yolo") else None
    body = _build_checkbox_page(sitekey, enterprise)
    try:
        await page.unroute_all()
    except Exception:
        pass
    await page.route(_route_glob(url), lambda r: r.fulfill(body=body, status=200))
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    for attempt in range(1, max_rounds + 1):
        try:
            for _ in range(3):
                try:
                    await page.frame_locator(_ANCHOR_IFRAME).locator(
                        "#recaptcha-anchor").click(timeout=8000)
                    break
                except Exception:
                    await asyncio.sleep(1)
        except Exception:
            pass

        challenge = False
        for _ in range(15):
            await asyncio.sleep(1)
            token = await _get_token(page)
            if token:
                return {"token": token, "attempts": attempt,
                        "elapsed": round(time.monotonic() - t0, 1),
                        "method": "checkbox"}
            bf = await _find_bframe(page)
            if bf:
                meta = await _challenge_meta(bf)
                if meta.get("has_table"):
                    challenge = True
                    break

        if challenge:
            await _classify_and_submit(page, clf)
            token = ""
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                token = await _get_token(page)
                if token:
                    break
                bf = await _find_bframe(page)
                if bf:
                    meta = await _challenge_meta(bf)
                    if meta.get("has_table"):
                        await _classify_and_submit(page, clf)
                    else:
                        await asyncio.sleep(1)
                else:
                    await asyncio.sleep(1)
            if token:
                return {"token": token, "attempts": attempt,
                        "elapsed": round(time.monotonic() - t0, 1),
                        "method": "image"}

        if attempt < max_rounds:
            await asyncio.sleep(3 * attempt)

    return {"error": f"failed after {max_rounds} attempts",
            "elapsed": round(time.monotonic() - t0, 1)}
