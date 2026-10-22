#!/usr/bin/env python
"""Pool the top-k of the given runs per query, drop pairs already judged, and write blind judging packets.
python pipeline/eval/make_packets.py K N_PACKETS system [system ...]
Packets go to data/cache/eval/packets/packet_XX.json (local only: they include profile excerpts)."""
import json, random, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import harness as H

k, n_packets, systems = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3:]
runs = json.load(open(H.CACHE / "runs.json"))
J = H.load_judgments()
out_dir = H.CACHE / "packets"; out_dir.mkdir(exist_ok=True)
for old in out_dir.glob("packet_*.json"): old.unlink()

def card(fid):
    f = H.F[H.IDX[fid]]
    labs = {d: [H.T["dimensions"][d]["labels"][l["c"]] for l in f["labels"].get(d, [])] for d in H.DIMS}
    return {"id": fid, "name": f["name"], "university": H.P[f["u"]]["name"], "rank": f["rank"], "department": f["dept"],
            "summary": f["summary"], "keywords": f["kw"], "research_areas": f["areas"],
            "labels": {d: v for d, v in labs.items() if v}, "profile_excerpt": H.BIO.get(fid, "")[:700]}

items, total = [], 0
for qi, q in enumerate(H.Q):
    pool = []
    for s in systems:
        for d in runs[s][qi][:k]:
            if d not in pool and d not in J.get(q["id"], {}): pool.append(d)
    random.Random(q["id"]).shuffle(pool)
    if pool: items.append({"qid": q["id"], "query": q["text"], "candidates": [card(d) for d in pool]}); total += len(pool)

# balance packets by number of candidates
packets = [[] for _ in range(n_packets)]
for it in sorted(items, key=lambda x: -len(x["candidates"])):
    min(packets, key=lambda p: sum(len(x["candidates"]) for x in p)).append(it)
for i, p in enumerate(packets):
    if p: json.dump(p, open(out_dir / f"packet_{i:02d}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{total} pairs to judge across {len(items)} queries, {sum(1 for p in packets if p)} packets:",
      [sum(len(x["candidates"]) for x in p) for p in packets])
