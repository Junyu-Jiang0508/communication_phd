#!/usr/bin/env python
"""Validate a raw faculty file: python pipeline/validate_raw.py data/raw/<slug>.json"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
RANKS = {"Professor", "Associate Professor", "Assistant Professor"}

def validate(path):
    d = json.load(open(path, encoding="utf-8"))
    errs, warns = [], []
    for k in ["university", "slug", "departments", "scraped_at", "faculty"]:
        if k not in d: errs.append(f"missing top-level key: {k}")
    if errs: return errs, warns
    if not re.fullmatch(r"[a-z0-9-]+", d["slug"]): errs.append("slug must be lowercase-kebab")
    if not d["departments"]: errs.append("departments empty")
    for dep in d["departments"]:
        if not dep.get("name") or not str(dep.get("directory_url","")).startswith("http"):
            errs.append(f"bad department entry: {dep}")
    seen = set()
    for i, f in enumerate(d["faculty"]):
        tag = f"faculty[{i}] {f.get('name')!r}"
        for k in ["name", "title", "rank", "department", "profile_url"]:
            if not f.get(k): errs.append(f"{tag}: missing {k}")
        if f.get("rank") not in RANKS: errs.append(f"{tag}: rank must be one of {sorted(RANKS)}, got {f.get('rank')!r}")
        if f.get("profile_url") and not str(f["profile_url"]).startswith("http"): errs.append(f"{tag}: profile_url not absolute")
        key = re.sub(r"[^a-z]", "", (f.get("name") or "").lower())
        if key in seen: errs.append(f"{tag}: duplicate name")
        seen.add(key)
        if len(f.get("bio") or "") < 80: warns.append(f"{tag}: bio shorter than 80 chars")
        if not f.get("research_areas"): warns.append(f"{tag}: no research_areas")
        if not f.get("photo_url"): warns.append(f"{tag}: no photo_url")
        t = (f.get("title") or "").lower()
        for bad in ["emerit", "lecturer", "instructor", "adjunct", "visiting", "clinical", "of practice", "teaching professor", "research professor", "postdoc", "graduate student", "fellow"]:
            if bad in t: warns.append(f"{tag}: title looks non-tenure-line ({f.get('title')!r}) — double-check inclusion")
    return errs, warns

if __name__ == "__main__":
    bad = 0
    for p in sys.argv[1:]:
        errs, warns = validate(p)
        print(f"== {p}: {len(errs)} errors, {len(warns)} warnings")
        for e in errs: print("  ERROR:", e)
        for w in warns[:40]: print("  warn:", w)
        if len(warns) > 40: print(f"  ... {len(warns)-40} more warnings")
        bad += bool(errs)
    sys.exit(1 if bad else 0)
