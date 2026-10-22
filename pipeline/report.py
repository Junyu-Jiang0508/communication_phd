#!/usr/bin/env python
"""Summarize pipeline coverage: python pipeline/report.py [journal_scrape.jsonl] [journal_label.jsonl] -> prints a Markdown table and writes docs/DATA_REPORT.md"""
import json, sys
from pathlib import Path
from collections import Counter
ROOT = Path(__file__).resolve().parents[1]

def journal(path):
    out = {}
    if not path or not Path(path).exists(): return out
    for line in open(path, encoding="utf-8"):
        d = json.loads(line)
        if d.get("type") == "result" and d.get("result"):
            r = d["result"]; slug = (r.get("scrape") or r.get("label") or r).get("slug") if isinstance(r, dict) else None
            if slug: out[slug] = r
    return out

def main():
    programs = json.load(open(ROOT / "data" / "programs.json", encoding="utf-8"))
    sj = journal(sys.argv[1] if len(sys.argv) > 1 else None)
    lj = journal(sys.argv[2] if len(sys.argv) > 2 else None)
    rows, tot = [], Counter()
    for p in programs:
        slug = p["slug"]
        rawp = ROOT / "data" / "raw" / f"{slug}.json"; labp = ROOT / "data" / "labels" / f"{slug}.json"
        n = nb = nph = nl = 0
        if rawp.exists():
            raw = json.load(open(rawp, encoding="utf-8"))
            n = len(raw["faculty"]); nb = sum(1 for f in raw["faculty"] if len(f.get("bio") or "") >= 80); nph = sum(1 for f in raw["faculty"] if f.get("photo_url"))
        if labp.exists():
            nl = len(json.load(open(labp, encoding="utf-8"))["faculty"])
        s = sj.get(slug, {}); a = (s.get("audit") or {}) if isinstance(s, dict) else {}
        l = lj.get(slug, {}); la = (l.get("audit") or {}) if isinstance(l, dict) else {}
        rows.append((p["university"], n, nb, nph, nl, a.get("verdict", "-"), len(a.get("missing_faculty") or []), la.get("verdict", "-")))
        tot["faculty"] += n; tot["bio"] += nb; tot["photo"] += nph; tot["labels"] += nl; tot["programs"] += bool(n)
    md = ["# Data coverage report", "", f"Programs with data: {tot['programs']}/{len(programs)} · faculty {tot['faculty']} · with bio {tot['bio']} · with photo {tot['photo']} · labeled {tot['labels']}", "",
          "| University | Faculty | Bio | Photo | Labeled | Roster audit | Missing | Label audit |", "|---|---:|---:|---:|---:|---|---:|---|"]
    for r in rows: md.append("| " + " | ".join(str(x) for x in r) + " |")
    text = "\n".join(md) + "\n"
    (ROOT / "docs" / "DATA_REPORT.md").write_text(text, encoding="utf-8")
    print(text)

if __name__ == "__main__":
    main()
