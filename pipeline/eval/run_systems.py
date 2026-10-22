#!/usr/bin/env python
"""Compute ranked runs for evaluation systems and store them in data/cache/eval/runs.json.
python pipeline/eval/run_systems.py [system ...]   (default: the judging pool)"""
import json, sys, traceback
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import harness as H

RUNS = H.CACHE / "runs.json"
runs = json.load(open(RUNS)) if RUNS.exists() else {}

def save():
    json.dump(runs, open(RUNS, "w"))

def rerank(base, ce_name, k=30, text_fn=H.view_published):
    from sentence_transformers import CrossEncoder
    import torch
    H._loaded.clear(); torch.cuda.empty_cache()
    ce = CrossEncoder(ce_name, device="cuda", trust_remote_code=True, max_length=512)
    out = []
    for q, ranked in zip(H.Q, runs[base]):
        cand = ranked[:k]
        sc = ce.predict([(q["text"], text_fn(H.F[H.IDX[d]])) for d in cand], batch_size=16, show_progress_bar=False)
        out.append([cand[i] for i in np.argsort(-np.asarray(sc), kind="stable")] + ranked[k:])
    return out

def bm25_run():
    lex = H.Lexical(H.view_published)
    return [H.rank(lex.bm25(q["text"])) for q in H.Q]

POOL = ["prod", "bm25", "dense:bge-small", "dense:arctic-m15", "dense:e5-base-ml", "dense:bge-m3", "dense:gemma-300m",
        "dense:qwen3-0.6b", "rr:dense:qwen3-0.6b>BAAI/bge-reranker-v2-m3"]

def compute(name):
    if name == "prod": return H.system_prod()
    if name == "bm25": return bm25_run()
    if name.startswith("rr:"):
        base, ce = name[3:].split(">")
        if base not in runs: runs[base] = compute(base)
        return rerank(base, ce)
    if name.startswith("dense:"):
        spec = name[6:]
        m, _, views = spec.partition("@")
        views = tuple(views.split("+")) if views else ("summary", "bio")
        return H.system_dense(m, views)
    raise ValueError(name)

for name in (sys.argv[1:] or POOL):
    if name in runs: print("cached", name); continue
    try:
        runs[name] = compute(name); save(); print("done", name, flush=True)
    except Exception as e:
        print("FAILED", name, str(e)[:300], flush=True); traceback.print_exc(limit=1)
