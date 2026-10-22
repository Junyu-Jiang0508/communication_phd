#!/usr/bin/env python
"""Method experiments on top of harness.py. Each function returns runs aligned with harness.Q.
python pipeline/eval/experiments.py   -> prints a metrics table for all configured systems."""
import hashlib, json, re, sys
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import harness as H

RUNS = json.load(open(H.CACHE / "runs.json"))
J = H.load_judgments()
LEX_PUB = None

def zs(x):
    return (x - x.mean()) / (x.std() + 1e-9)

def bm25_matrix():
    global LEX_PUB
    LEX_PUB = LEX_PUB or H.Lexical(H.view_published)
    cp = H.CACHE / "bm25_pub.npy"
    if cp.exists(): return np.load(cp)
    M = np.stack([LEX_PUB.bm25(q["text"]) for q in H.Q]); np.save(cp, M); return M

def hint_matrix(weights):
    """per query x faculty bonus from detected hints; weights: dict dim -> bonus"""
    out = np.zeros((len(H.Q), len(H.F)), dtype=np.float32)
    for qi, q in enumerate(H.Q):
        for d, c in H.hints(q["text"]):
            w = weights.get(d, 0)
            if not w: continue
            for i, f in enumerate(H.F):
                if H.has_label(f, d, c): out[qi, i] += w
    return out

def hint_matrix_text(text, weights={"region": 0.25, "approach": 0.1, "topic": 0.05}):
    """hint bonus vector for one (possibly translated) query text"""
    out = np.zeros(len(H.F), dtype=np.float32)
    for d, c in H.hints(text):
        w = weights.get(d, 0)
        if w:
            for i, f in enumerate(H.F):
                if H.has_label(f, d, c): out[i] += w
    return out

def split_query(text):
    parts = [p.strip() for p in re.split(r"(?<=[.!?;。！？；])\s*", text) if len(p.strip()) > 15]
    return parts if len(parts) > 1 else [text]

def dense_split(name, views=("summary", "bio"), agg="mean_with_full"):
    D = H.combine(name, views)
    out = []
    full = H.query_emb(name, [q["text"] for q in H.Q]) @ D.T
    for qi, q in enumerate(H.Q):
        parts = split_query(q["text"])
        if len(parts) == 1: out.append(full[qi]); continue
        S = H.query_emb(name, parts) @ D.T
        out.append(0.5 * full[qi] + 0.5 * S.mean(0) if agg == "mean_with_full" else S.max(0))
    return np.stack(out)

def fuse(dense, alpha=0.75, bm=None, bonus=None):
    out = []
    for qi in range(dense.shape[0]):
        s = alpha * zs(dense[qi])
        if bm is not None and alpha < 1: s = s + (1 - alpha) * zs(bm[qi])
        if bonus is not None: s = s + bonus[qi]
        out.append(H.rank(s))
    return out

def rerank_scores(base_runs, ce_name, k=30, text_fn=H.view_published):
    key = hashlib.sha1(json.dumps([r[:k] for r in base_runs]).encode()).hexdigest()[:12]
    cp = H.CACHE / f"ce_{re.sub(r'[^a-z0-9]+', '_', ce_name.lower())}_{k}_{key}.json"
    if cp.exists(): return json.load(open(cp))
    from sentence_transformers import CrossEncoder
    import torch
    H._loaded.clear(); torch.cuda.empty_cache()
    ce = CrossEncoder(ce_name, device="cuda", trust_remote_code=True, max_length=512)
    out = []
    for q, ranked in zip(H.Q, base_runs):
        cand = ranked[:k]
        sc = ce.predict([(q["text"], text_fn(H.F[H.IDX[d]])) for d in cand], batch_size=16, show_progress_bar=False)
        out.append({d: float(s) for d, s in zip(cand, np.asarray(sc).ravel())})
    json.dump(out, open(cp, "w")); return out

def rerank_scores_texts(base_runs, ce_name, k, qtexts, text_fn=H.view_published):
    """Like rerank_scores but with explicit query texts (e.g. translated queries)."""
    key = hashlib.sha1(json.dumps([[r[:k] for r in base_runs], qtexts]).encode()).hexdigest()[:12]
    cp = H.CACHE / f"cet_{re.sub(r'[^a-z0-9]+', '_', ce_name.lower())}_{k}_{key}.json"
    if cp.exists(): return json.load(open(cp))
    from sentence_transformers import CrossEncoder
    import torch
    H._loaded.clear(); torch.cuda.empty_cache()
    ce = CrossEncoder(ce_name, device="cuda", max_length=512)
    out = []
    for qt, ranked in zip(qtexts, base_runs):
        cand = ranked[:k]
        sc = ce.predict([(qt, text_fn(H.F[H.IDX[d]])) for d in cand], batch_size=16, show_progress_bar=False)
        out.append({d: float(s) for d, s in zip(cand, np.asarray(sc).ravel())})
    json.dump(out, open(cp, "w")); return out

def apply_rerank(base_runs, scores, mix=1.0, k=30):
    """mix=1: pure cross-encoder order on top-k; mix<1: blend z(ce) with reciprocal-rank prior of the base."""
    out = []
    for ranked, sc in zip(base_runs, scores):
        cand = ranked[:k]
        ce = np.array([sc[d] for d in cand]); prior = -np.log1p(np.arange(len(cand)))
        s = mix * zs(ce) + (1 - mix) * zs(prior)
        out.append([cand[i] for i in np.argsort(-s, kind="stable")] + ranked[k:])
    return out

def table(rows, qsets):
    hdr = f"{'system':58s}" + "".join(f"{n:>16s}" for n in qsets)
    print(hdr); print("-" * len(hdr))
    for name, runs in rows:
        cells = []
        for qn, qids in qsets.items():
            m = H.evaluate(runs, J, qids)
            cells.append(f"{m['ndcg']:.3f}/{m['p']:.2f}/{m['unj']:.2f}")
        print(f"{name:58s}" + "".join(f"{c:>16s}" for c in cells))

QSETS = {
    "all(ndcg/p/unj)": None,
    "sop": {q["id"] for q in H.Q if q["kind"] == "sop"},
    "short": {q["id"] for q in H.Q if q["kind"] == "short"},
    "zh": {q["id"] for q in H.Q if q["kind"] == "zh"},
}

if __name__ == "__main__":
    rows = [(n, r) for n, r in RUNS.items()]
    table(rows, QSETS)
