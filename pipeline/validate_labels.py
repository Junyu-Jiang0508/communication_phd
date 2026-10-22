#!/usr/bin/env python
"""Validate labels: python pipeline/validate_labels.py data/labels/<slug>.json  (checks against data/raw/<slug>.json and taxonomy)"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
TAX = json.load(open(ROOT / "pipeline" / "taxonomy.json", encoding="utf-8"))
DIMS = {k: set(v["labels"].keys()) for k, v in TAX["dimensions"].items()}
norm = lambda s: re.sub(r"[^a-z]", "", (s or "").lower())

def validate(path):
    d = json.load(open(path, encoding="utf-8"))
    errs, warns = [], []
    slug = d.get("slug")
    rawp = ROOT / "data" / "raw" / f"{slug}.json"
    raw_names = set()
    if rawp.exists():
        raw_names = {norm(f["name"]) for f in json.load(open(rawp, encoding="utf-8"))["faculty"]}
    else:
        warns.append(f"no raw file for slug {slug!r}")
    seen = set()
    for i, f in enumerate(d.get("faculty", [])):
        tag = f"faculty[{i}] {f.get('name')!r}"
        if raw_names and norm(f.get("name")) not in raw_names: errs.append(f"{tag}: name not in raw file")
        if norm(f.get("name")) in seen: errs.append(f"{tag}: duplicate")
        seen.add(norm(f.get("name")))
        s = f.get("summary") or ""
        if not (20 <= len(s) <= 220): errs.append(f"{tag}: summary length {len(s)} (need 20-220)")
        if f.get("confidence") not in ("high", "medium", "low"): errs.append(f"{tag}: bad confidence")
        labs = f.get("labels") or {}
        for dim, allowed in DIMS.items():
            items = labs.get(dim)
            if items is None: errs.append(f"{tag}: missing dimension {dim}"); continue
            if len(items) > 4: errs.append(f"{tag}: {dim} has {len(items)} labels (max 4)")
            for it in items:
                if it.get("code") not in allowed: errs.append(f"{tag}: unknown code {it.get('code')!r} in {dim}")
                if not it.get("sources"): warns.append(f"{tag}: {dim}/{it.get('code')} has no sources")
        if labs.get("topic") and not any(x.get("primary") for x in labs["topic"]): warns.append(f"{tag}: no primary topic")
        if not labs.get("topic"): errs.append(f"{tag}: no topic labels")
        if len(f.get("keywords") or []) < 3: warns.append(f"{tag}: fewer than 3 keywords")
    if raw_names:
        missing = raw_names - seen
        if missing: errs.append(f"{len(missing)} raw faculty have no labels (e.g. {sorted(missing)[:3]})")
    return errs, warns

if __name__ == "__main__":
    bad = 0
    for p in sys.argv[1:]:
        errs, warns = validate(p)
        print(f"== {p}: {len(errs)} errors, {len(warns)} warnings")
        for e in errs[:60]: print("  ERROR:", e)
        for w in warns[:30]: print("  warn:", w)
        bad += bool(errs)
    sys.exit(1 if bad else 0)
