#!/usr/bin/env python
"""Warm the photo cache used by build.py: python pipeline/prefetch_photos.py [--workers 8]
Downloads every photo_url in data/raw/*.json into data/cache/photos/<sha1>.bin (skips cached).
At most 2 concurrent requests per host; browser-like UA; failures are listed at the end."""
import argparse, hashlib, json, sys, threading, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse
import requests, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache" / "photos"; CACHE.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 CommPhDExplorer/0.1"
host_sem = defaultdict(lambda: threading.Semaphore(2))

def fetch(url):
    cp = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".bin")
    if cp.exists() and cp.stat().st_size > 200: return "cached", url
    with host_sem[urlparse(url).netloc]:
        for attempt in range(3):
            try:
                hdr = {"User-Agent": UA, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
                try:
                    r = requests.get(url, headers=hdr, timeout=25)
                except requests.exceptions.SSLError:
                    # some department sites serve an incomplete certificate chain; these are public images
                    r = requests.get(url, headers=hdr, timeout=25, verify=False)
                r.raise_for_status()
                if len(r.content) < 200 or "image" not in r.headers.get("content-type", "image"): raise RuntimeError(f"not an image ({r.headers.get('content-type')}, {len(r.content)} B)")
                cp.write_bytes(r.content); time.sleep(0.2)
                return "ok", url
            except Exception as e:
                err = str(e)[:120]; time.sleep(1.5 * (attempt + 1))
        return "fail: " + err, url

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=8); a = ap.parse_args()
    urls, profile = [], {}
    for p in sorted((ROOT / "data" / "raw").glob("*.json")):
        for f in json.load(open(p, encoding="utf-8"))["faculty"]:
            if f.get("photo_url"): urls.append(f["photo_url"]); profile.setdefault(f["photo_url"], f.get("profile_url"))
    urls = list(dict.fromkeys(urls))
    stats = defaultdict(int); fails = []
    with ThreadPoolExecutor(a.workers) as ex:
        for fut in as_completed([ex.submit(fetch, u) for u in urls]):
            st, u = fut.result(); stats[st.split(":")[0]] += 1
            if st.startswith("fail"): fails.append((u, st))
    print(dict(stats), "of", len(urls))
    # Fallback: hosts that refuse plain HTTP clients usually serve images to a real browser.
    # Open the profile page first (bot challenges set cookies there) and capture the image as the page loads it;
    # if the page did not request it, fetch it directly with the page's cookies.
    retry = [u for u, st in fails if "not an image (image/png, 91 B)" not in st]
    if retry:
        from playwright.sync_api import sync_playwright
        rescued = 0
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True); ctx = b.new_context(user_agent=UA, ignore_https_errors=True)
            pg = ctx.new_page()
            for u in retry:
                got = {}
                def on_resp(r, u=u):
                    if r.url.split("?")[0] == u.split("?")[0] and "image" in (r.headers.get("content-type") or ""):
                        try: got["body"] = r.body()
                        except Exception: pass
                pg.on("response", on_resp)
                try:
                    if profile.get(u):
                        pg.goto(profile[u], wait_until="domcontentloaded", timeout=45000)
                        try: pg.wait_for_load_state("networkidle", timeout=12000)
                        except Exception: pass
                    if "body" not in got:
                        resp = pg.goto(u, timeout=30000)
                        if resp and resp.ok and "image" in (resp.headers.get("content-type") or ""): got["body"] = resp.body()
                except Exception:
                    pass
                pg.remove_listener("response", on_resp)
                if len(got.get("body") or b"") > 200:
                    (CACHE / (hashlib.sha1(u.encode()).hexdigest() + ".bin")).write_bytes(got["body"]); rescued += 1
                    fails = [(x, st) for x, st in fails if x != u]
            b.close()
        print(f"browser fallback rescued {rescued}/{len(retry)}")
    for u, st in fails[:40]: print("  ", st, u)
