#!/usr/bin/env python
"""Offline replica of the browser scoring (semantic calibrated + BM25-lite + label boosts) for sanity checks.
python pipeline/eval_queries.py  -> prints top matches and program fit for a set of test queries."""
import json, math, re, sys
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer
ROOT = Path(__file__).resolve().parents[1]
F = json.load(open(ROOT / "src/data/faculty.json")); P = {p["slug"]: p for p in json.load(open(ROOT / "src/data/programs.json"))}
T = json.load(open(ROOT / "src/data/taxonomy.json"))
M = json.load(open(ROOT / "public/search/manifest.json")); C = M["calibration"]
ids = json.load(open(ROOT / "public/search/index.json"))
V = np.frombuffer(open(ROOT / "public/search/vectors.i8.bin", "rb").read(), dtype=np.int8).reshape(-1, M["dimensions"]).astype(np.float32) / 127
model = SentenceTransformer("BAAI/bge-small-en-v1.5")

def rescale(c):
    z = (c - C["lo"]) / (C["hi"] - C["lo"]); k = C.get("scaleAtHi", 0.85)
    return 0 if z <= 0 else (k * z if z <= 1 else k + (1 - k) * (1 - math.exp(-2 * (z - 1))))

QUERIES = sys.argv[1:] or [
    "I study how misinformation about vaccines spreads in Chinese-language WeChat groups, combining computational text analysis of posts with survey experiments on corrections.",
    "My research examines how adolescents use social media and how it affects their mental health and friendships, using longitudinal surveys and experience sampling.",
    "I want to study how newsrooms adopt generative AI tools and what it means for journalistic norms, through interviews and newsroom ethnography.",
    "I study the rhetoric of social movements and public memory through critical and historical methods.",
    "I study nationalism and online discourse in China, using computational text analysis of Weibo posts.",
]
for q in QUERIES:
    qv = model.encode([M["queryPrefix"] + q], normalize_embeddings=True)[0]
    cos = V @ qv
    sem = np.array([rescale(c) for c in cos])
    order = np.argsort(-sem)
    n_pass = int((0.75 * sem >= 0.35).sum())
    print(f"\nQ: {q[:110]}\n   raw cos max={cos.max():.3f} p50={np.median(cos):.3f}  | semantic-only >=35 after weighting: ~{n_pass} faculty")
    for i in order[:8]:
        f = F[i]; print(f"   {round(sem[i]*100):3d}  {f['name']:28s} {P[f['u']]['short']:18s} {f['summary'][:90]}")
    by = {}
    for i in order[:200]:
        by.setdefault(F[i]["u"], []).append(sem[i])
    fit = sorted(((0.5 * (v + [0, 0, 0])[0] + 0.3 * (v + [0, 0, 0])[1] + 0.2 * (v + [0, 0, 0])[2], u, len(v)) for u, v in by.items()), reverse=True)[:5]
    print("   programs: " + " | ".join(f"{P[u]['short']} {round(s*100)}" for s, u, n in fit))
