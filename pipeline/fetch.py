#!/usr/bin/env python
"""Polite page fetcher for the Communication PhD Explorer pipeline.

Usage:
  python pipeline/fetch.py URL                # print readable text (HTML -> text)
  python pipeline/fetch.py URL --html         # print raw HTML
  python pipeline/fetch.py URL --render       # force headless-Chromium rendering (JS sites)
  python pipeline/fetch.py URL --links        # print all links (text | href) found in the page
  python pipeline/fetch.py URL --out path     # also save raw HTML to a file

Behaviour:
  * Caches every fetched page under data/cache/<sha1>.html (re-runs are free).
  * Browser-like User-Agent, 30 s timeout, 1 s politeness delay between live requests.
  * Falls back to Playwright (Chromium) automatically when the static HTML looks like a JS shell.
"""
import argparse, hashlib, os, re, sys, time, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 CommPhDExplorer/0.1 (academic directory research)")

def cache_path(url, render):
    key = hashlib.sha1((("R:" if render else "S:") + url).encode()).hexdigest()
    return CACHE / f"{key}.html"

def fetch_static(url):
    import requests
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}, timeout=30)
    r.raise_for_status()
    if "text/html" not in r.headers.get("content-type", "") and "<html" not in r.text[:2000].lower():
        raise RuntimeError(f"not html: {r.headers.get('content-type')}")
    return r.text

def fetch_render(url, wait_ms=2500):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(user_agent=UA, viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(wait_ms)
        # scroll to trigger lazy content
        for _ in range(6):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(300)
        html = page.content()
        b.close()
    return html

def looks_like_js_shell(html):
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return len(text) < 600 or "enable javascript" in text.lower()

def get(url, render=False):
    # a static request that fell back to rendering is cached under the render key
    for cp in [cache_path(url, render)] + ([] if render else [cache_path(url, True)]):
        if cp.exists():
            return cp.read_text(encoding="utf-8", errors="ignore")
    cp = cache_path(url, render)
    html = None
    if not render:
        try:
            html = fetch_static(url)
            if looks_like_js_shell(html):
                html = None
        except Exception as e:
            sys.stderr.write(f"[static failed: {e}] -> rendering\n")
            html = None
    if html is None:
        html = fetch_render(url)
        cp = cache_path(url, True)
    cp.write_text(html, encoding="utf-8")
    time.sleep(1.0)
    return html

def to_text(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "svg", "iframe"]):
        t.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()

def links(html, base):
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.find_all("a", href=True):
        t = re.sub(r"\s+", " ", a.get_text(" ")).strip()
        out.append(f"{t} | {urljoin(base, a['href'])}")
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--html", action="store_true")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--links", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--max", type=int, default=60000, help="max characters to print")
    a = ap.parse_args()
    html = get(a.url, render=a.render)
    if a.out:
        Path(a.out).write_text(html, encoding="utf-8")
    if a.html:
        sys.stdout.write(html[: a.max])
    elif a.links:
        sys.stdout.write("\n".join(links(html, a.url))[: a.max])
    else:
        sys.stdout.write(to_text(html)[: a.max])
    sys.stdout.write("\n")
