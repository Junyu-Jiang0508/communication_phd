#!/usr/bin/env python
"""Merge judged packets (data/cache/eval/judged/*.json) into pipeline/eval/judgments.json, checking them
against the packets they answer. Existing judgments are kept; a pair is never overwritten."""
import json, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import harness as H

jp = H.ROOT / "pipeline/eval/judgments.json"
J = json.load(open(jp, encoding="utf-8")) if jp.exists() else {}
added = 0
for pk in sorted((H.CACHE / "packets").glob("packet_*.json")):
    out = H.CACHE / "judged" / pk.name
    if not out.exists(): print("missing", out.name); continue
    want = {(it["qid"], c["id"]) for it in json.load(open(pk, encoding="utf-8")) for c in it["candidates"]}
    got = json.load(open(out, encoding="utf-8"))
    have = {(q, d) for q, m in got.items() for d in m}
    if want - have or have - want:
        print(f"{pk.name}: {len(want - have)} ungraded, {len(have - want)} unexpected")
    for q, m in got.items():
        for d, g in m.items():
            if (q, d) in want and d not in J.setdefault(q, {}) and int(g) in (0, 1, 2, 3):
                J[q][d] = int(g); added += 1
json.dump({q: dict(sorted(m.items())) for q, m in sorted(J.items())}, open(jp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(f"added {added}; total {sum(len(m) for m in J.values())} judgments over {len(J)} queries")
