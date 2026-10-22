#!/usr/bin/env python
"""End-to-end check of the Match page in headless Chromium against a running preview (default http://localhost:4321/communication_phd/).
Downloads the real bge-small model from the CDN/HF hub, runs a query, prints the top results and any console errors."""
import sys, time, json, os, tempfile
from playwright.sync_api import sync_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4321/communication_phd/"
QUERY = sys.argv[2] if len(sys.argv) > 2 else ("I study how misinformation about vaccines spreads in Chinese-language WeChat groups, combining computational text analysis "
         "of posts with survey experiments on corrections. I am also interested in trust in journalism and platform governance.")
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)))
    pg.on("console", lambda m: errs.append("CONSOLE " + m.text) if m.type == "error" else None)
    pg.goto(BASE, wait_until="networkidle", timeout=60000)
    pg.fill("#q", QUERY)
    pg.wait_for_timeout(300)
    print("hints:", [c.inner_text() for c in pg.query_selector_all("#hint-chips button")])
    t0 = time.time()
    pg.click("#go")
    try:
        pg.wait_for_selector(".results-head", timeout=240000)
    except Exception as e:
        print("TIMEOUT waiting for results; status:", pg.inner_text("#status"), "err:", pg.inner_text("#err"))
        print("\n".join(errs)); b.close(); sys.exit(1)
    print(f"results in {time.time()-t0:.1f}s ::", pg.inner_text(".results-head"))
    rows = pg.query_selector_all("#results .row")
    for r in rows[:8]:
        name = r.query_selector(".name").inner_text(); meta = r.query_selector(".meta").inner_text(); sc = r.query_selector(".score b").inner_text()
        why = r.query_selector(".why").inner_text() if r.query_selector(".why") else ""
        print(f"  {sc:>3}  {name} — {why}")
    pg.click('[data-view="programs"]'); pg.wait_for_timeout(200)
    print("programs view:", pg.inner_text(".results-head").replace("\n", " | "))
    for r in pg.query_selector_all("#results .prog")[:5]:
        print("  ", r.query_selector(".prog-title").inner_text(), "fit", r.query_selector(".score b").inner_text(), "|", r.query_selector(".side .small").inner_text())
    shot = os.path.join(tempfile.gettempdir(), "shot-match-results.png")
    pg.screenshot(path=shot, full_page=False); print("screenshot:", shot)
    print("errors:", errs[:5] if errs else "none")
    b.close()
