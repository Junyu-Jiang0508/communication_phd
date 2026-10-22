#!/usr/bin/env python
"""Offline evaluation harness for the matcher.

Loads the built faculty records (src/data/faculty.json), the local-only profile text (data/raw, via build.py's ids),
the evaluation queries (pipeline/eval/queries.json) and graded judgments (pipeline/eval/judgments.json), and scores
retrieval systems with nDCG@10 / P@10 / MRR. Document embeddings are cached under data/cache/eval/.
"""
import json, math, re, sys, hashlib
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
import build  # noqa: E402  (slugify / short_name for ids)

CACHE = ROOT / "data" / "cache" / "eval"; CACHE.mkdir(parents=True, exist_ok=True)
F = json.load(open(ROOT / "src/data/faculty.json", encoding="utf-8"))
P = {p["slug"]: p for p in json.load(open(ROOT / "src/data/programs.json", encoding="utf-8"))}
T = json.load(open(ROOT / "src/data/taxonomy.json", encoding="utf-8"))
IDX = {f["id"]: i for i, f in enumerate(F)}
Q = json.load(open(ROOT / "pipeline/eval/queries.json", encoding="utf-8"))["queries"]
DIMS = ["topic", "approach", "data", "setting", "region"]

def _bios():
    out = {}
    for p in json.load(open(ROOT / "data/programs.json", encoding="utf-8")):
        rp = ROOT / "data/raw" / f"{p['slug']}.json"
        if not rp.exists(): continue
        sn = build.short_name(p["university"])
        for f in json.load(open(rp, encoding="utf-8"))["faculty"]:
            out[build.slugify(f"{sn}-{f['name']}")] = (f.get("bio") or "").strip()
    return out
BIO = _bios()

# ---------- document views ----------
def label_names(f, short=True, dims=DIMS):
    key = "labels_short" if short else "labels"
    return [T["dimensions"][d][key][l["c"]] for d in dims for l in f["labels"].get(d, [])]

def view_summary(f):  # LLM summary + keywords (published)
    return " ".join(x for x in [f["summary"], ("Keywords: " + ", ".join(f["kw"]) + ".") if f["kw"] else ""] if x).strip()

def view_bio(f):  # local profile text (never published)
    b = BIO.get(f["id"], "")
    if len(b) < 200:
        b = " ".join(x for x in [f["title"], f["dept"], ("Research areas: " + "; ".join(f["areas"]) + ".") if f["areas"] else "", b] if x)
    return b[:1500] or view_summary(f)

def view_published(f):  # everything that is (or may be) shown on the site
    parts = [f["summary"]]
    if f["kw"]: parts.append("Keywords: " + ", ".join(f["kw"]) + ".")
    if f["areas"]: parts.append("Research areas: " + "; ".join(f["areas"]) + ".")
    ln = label_names(f)
    if ln: parts.append("Labels: " + ", ".join(ln) + ".")
    return " ".join(parts)

VIEWS = {"summary": view_summary, "bio": view_bio, "published": view_published}

# ---------- embedding models ----------
MODELS = {
    # name: (hf id, query prefix, doc prefix, kwargs)
    "bge-small": ("BAAI/bge-small-en-v1.5", "Represent this sentence for searching relevant passages: ", "", {}),
    "bge-base": ("BAAI/bge-base-en-v1.5", "Represent this sentence for searching relevant passages: ", "", {}),
    "arctic-s": ("Snowflake/snowflake-arctic-embed-s", "Represent this sentence for searching relevant passages: ", "", {}),
    "arctic-m15": ("Snowflake/snowflake-arctic-embed-m-v1.5", "Represent this sentence for searching relevant passages: ", "", {}),
    "arctic-m2": ("Snowflake/snowflake-arctic-embed-m-v2.0", "query: ", "", {"trust_remote_code": True}),
    "e5-small-ml": ("intfloat/multilingual-e5-small", "query: ", "passage: ", {}),
    "e5-base-ml": ("intfloat/multilingual-e5-base", "query: ", "passage: ", {}),
    "gte-ml-base": ("Alibaba-NLP/gte-multilingual-base", "", "", {"trust_remote_code": True}),
    "nomic-15": ("nomic-ai/nomic-embed-text-v1.5", "search_query: ", "search_document: ", {"trust_remote_code": True}),
    "mxbai-xs": ("mixedbread-ai/mxbai-embed-xsmall-v1", "Represent this sentence for searching relevant passages: ", "", {}),
    "granite-s-r2": ("ibm-granite/granite-embedding-small-english-r2", "", "", {}),
    "granite-ml-278": ("ibm-granite/granite-embedding-278m-multilingual", "", "", {}),
    "bge-m3": ("BAAI/bge-m3", "", "", {}),
    "gemma-300m": ("google/embeddinggemma-300m", "task: search result | query: ", "title: none | text: ", {}),
    "qwen3-0.6b": ("Qwen/Qwen3-Embedding-0.6B", "Instruct: Given a prospective PhD student's description of their research interests, retrieve faculty research profiles that match\nQuery: ", "", {}),
}
_loaded = {}
def model(name):
    if name not in _loaded:
        from sentence_transformers import SentenceTransformer
        mid, _, _, kw = MODELS[name]
        _loaded.clear()  # keep one model in GPU memory at a time
        import torch; torch.cuda.empty_cache()
        _loaded[name] = SentenceTransformer(mid, device="cuda", **kw)
    return _loaded[name]

def doc_emb(name, view):
    key = hashlib.sha1(f"{name}|{view}|{len(F)}|v3".encode()).hexdigest()[:16]
    cp = CACHE / f"doc_{name}_{view}_{key}.npy"
    if cp.exists(): return np.load(cp)
    m = model(name); dp = MODELS[name][2]
    texts = [dp + VIEWS[view](f) for f in F]
    e = m.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False, convert_to_numpy=True).astype(np.float32)
    np.save(cp, e); return e

def query_emb(name, texts):
    key = hashlib.sha1(("|".join(texts) + name).encode()).hexdigest()[:16]
    cp = CACHE / f"q_{name}_{key}.npy"
    if cp.exists(): return np.load(cp)
    m = model(name); qp = MODELS[name][1]
    e = m.encode([qp + t for t in texts], batch_size=16, normalize_embeddings=True, show_progress_bar=False, convert_to_numpy=True).astype(np.float32)
    np.save(cp, e); return e

def combine(name, views=("summary", "bio")):
    e = sum(doc_emb(name, v) for v in views)
    return e / np.linalg.norm(e, axis=1, keepdims=True)

def dense_scores(name, views=("summary", "bio"), texts=None):
    texts = texts or [q["text"] for q in Q]
    return query_emb(name, texts) @ combine(name, views).T  # (nq, nf)

# ---------- lexical ----------
from textmatch import tokenize  # noqa: E402  (shared with build.py; mirrors src/lib/match.ts)

class Lexical:
    def __init__(self, text_fn):
        self.tf, self.len, self.df = [], [], {}
        for f in F:
            toks = tokenize(text_fn(f)); tf = {}
            for t in toks: tf[t] = tf.get(t, 0) + 1
            for t in tf: self.df[t] = self.df.get(t, 0) + 1
            self.tf.append(tf); self.len.append(len(toks))
        self.N = len(F); self.avg = sum(self.len) / self.N
    def idf(self, t):
        d = self.df.get(t, 0); return math.log(1 + (self.N - d + 0.5) / (d + 0.5))
    def prod(self, query, i):  # exact port of lexical() incl. saturation
        q = list(dict.fromkeys(tokenize(query)))
        if not q: return 0.0
        s = mx = 0.0; tf = self.tf[i]; L = self.len[i]
        for t in q:
            w = self.idf(t); mx += w; c = tf.get(t, 0)
            if c: s += w * ((c * 2.2) / (c + 1.2 * (0.25 + 0.75 * L / self.avg)))
        ql = query.lower()
        for k in F[i]["kw"]:
            if len(k) > 3 and k in ql: s += 1.2
        return min(1.0, s / max(4, mx * 0.45))
    def bm25(self, query):  # plain BM25 over all docs (no saturation), k1=1.2 b=0.75
        q = list(dict.fromkeys(tokenize(query))); out = np.zeros(self.N, dtype=np.float32)
        for t in q:
            w = self.idf(t)
            for i, tf in enumerate(self.tf):
                c = tf.get(t, 0)
                if c: out[i] += w * (c * 2.2) / (c + 1.2 * (0.25 + 0.75 * self.len[i] / self.avg))
        return out

def prod_lex_text(f):
    parts = [f["summary"], " ".join(f["areas"]), " ".join(f["kw"])]
    for d in DIMS:
        for l in f["labels"].get(d, []): parts.append(T["dimensions"][d]["labels"].get(l["c"], ""))
    return " ".join(parts).lower()

# hints (port of DETECT in match.ts)
DETECT = [
 ("region", "R_CHINA", r"\b(china|chinese|prc|hong kong|weibo|wechat|douyin|bilibili|xiaohongshu|sinophone)\b"),
 ("region", "R_EAST_ASIA", r"\b(japan|japanese|korea|korean|taiwan|taiwanese|east asia)\b"),
 ("region", "R_SOUTH_SE_ASIA", r"\b(india|indian|south asia|southeast asia|indonesia|philippines|vietnam|thailand|malaysia|singapore)\b"),
 ("region", "R_MIDDLE_EAST", r"\b(middle east|arab|iran|turkey|israel|egypt|north africa|mena)\b"),
 ("region", "R_AFRICA", r"\b(africa|african|nigeria|kenya|ghana|south africa)\b"),
 ("region", "R_LATIN_AMERICA", r"\b(latin america|brazil|mexico|argentina|chile|colombia|caribbean)\b"),
 ("region", "R_EUROPE", r"\b(europe|european|germany|france|uk|britain|british|russia|ukraine|post-soviet|eastern europe)\b"),
 ("region", "R_US", r"\b(united states|u\.s\.|american politics|american public)\b"),
 ("region", "R_GLOBAL_CROSS_NATIONAL", r"\b(cross-national|comparative|global south|transnational|multi-country|cross-cultural)\b"),
 ("approach", "A_COMPUTATIONAL", r"\b(computational|text-as-data|text analysis|nlp|natural language processing|machine learning|large language models?|llms?|topic model|word embeddings?|digital trace|big data)\b"),
 ("approach", "A_EXPERIMENT", r"\b(experiments?|experimental|causal|randomized|rct|field experiment)\b"),
 ("approach", "A_SURVEY", r"\b(surveys?|panel data|questionnaire|measurement|scale development)\b"),
 ("approach", "A_NETWORK", r"\b(network analysis|social networks?|diffusion|network science)\b"),
 ("approach", "A_QUALITATIVE", r"\b(qualitative|interviews?|ethnograph\w*|focus groups?|fieldwork)\b"),
 ("approach", "A_CRITICAL_INTERPRETIVE", r"\b(critical (theory|cultural|discourse|race|studies|analysis|approach\w*)|interpretive|rhetorical criticism|discourse analysis|cultural studies|feminist|postcolonial|queer theory)\b"),
 ("approach", "A_HISTORICAL_ARCHIVAL", r"\b(historical|archiv\w*|history of)\b"),
 ("approach", "A_PHYSIO_NEURO", r"\b(psychophysiolog\w*|eye[- ]tracking|neuro\w*|fmri|eeg|biometric)\b"),
 ("topic", "T_POLITICAL", r"\b(political communication|public opinion|elections?|electoral|(political|election|presidential|electoral) campaigns?|polarization|partisan\w*|democrac\w*|propaganda|populis\w*|voters?|voting)\b"),
 ("topic", "T_MISINFO_TRUST", r"\b(misinformation|disinformation|rumou?rs?|fake news|fact-?check\w*|conspiracy|trust in (news|media|journalism|science))\b"),
 ("topic", "T_JOURNALISM", r"\b(journalis\w*|news(room|rooms| media| production| audiences?)|press freedom|reporters?)\b"),
 ("topic", "T_PLATFORMS_AI", r"\b(platforms?|algorithm\w*|artificial intelligence|generative ai|chatbots?|recommender|content moderation|platform governance|datafication)\b"),
 ("topic", "T_HEALTH", r"\b(health|vaccin\w*|patients?|public health|risk communication|crisis communication|mental health)\b"),
 ("topic", "T_SCIENCE_ENV", r"\b(science communication|climate|environment\w*|sustainability)\b"),
 ("topic", "T_INTERPERSONAL", r"\b(interpersonal|relationships?|family communication|romantic|friendship|dating)\b"),
 ("topic", "T_ORGANIZATIONAL", r"\b(organizational communication|organizational|workplaces?|leadership|employees?|teams at work)\b"),
 ("topic", "T_STRATEGIC_PR_AD", r"\b(public relations|advertising|strategic communication|branding|marketing|corporate communication)\b"),
 ("topic", "T_CRITICAL_CULTURAL", r"\b(race|racial|gender|feminis\w*|queer|lgbtq?\+?|identity|intersectional\w*|decolonial|whiteness)\b"),
 ("topic", "T_MEDIA_EFFECTS_PSYCH", r"\b(media effects|media psychology|persuasion|emotion\w*|attention|cognitive|narrative persuasion|parasocial)\b"),
 ("topic", "T_GLOBAL_INTERCULTURAL", r"\b(intercultural|international communication|global media|diaspora|migrants?|migration|nationalis\w*)\b"),
 ("topic", "T_ENTERTAINMENT_GAMES", r"\b(entertainment|video ?games?|gaming|fandom|fans|esports|popular culture|television|streaming)\b"),
 ("topic", "T_HCI_CMC", r"\b(human-computer interaction|hci|computer-mediated|virtual reality|augmented reality|social robots?|chatbots?|avatars?)\b"),
 ("topic", "T_RHETORIC", r"\b(rhetoric\w*|public address|argumentation|oratory)\b"),
 ("topic", "T_MEDIA_INDUSTRIES_POLICY", r"\b(media industr\w*|media policy|regulation|media law|political economy of|telecommunications)\b"),
 ("topic", "T_CHILDREN_FAMILY_MEDIA", r"\b(children|adolescents?|youth|teens?|media literacy|parent\w*)\b"),
 ("topic", "T_LANGUAGE_INTERACTION", r"\b(conversation analysis|nonverbal|language and social interaction|discourse)\b"),
]
def hints(text):
    out = []
    for d, c, rx in DETECT:
        if re.search(rx, text, re.I) and c not in [x[1] for x in out]: out.append((d, c))
    return out[:8]

def has_label(f, d, c): return any(l["c"] == c for l in f["labels"].get(d, []))

# ---------- systems ----------
def rank(scores, k=50):
    order = np.argsort(-scores, kind="stable")[:k]
    return [F[i]["id"] for i in order]

def system_prod(texts=None):
    """Current production ranking: calibrated bge-small two-view cosine (int8 vectors as deployed) + saturated
    keyword score (25%) + 3-point label boosts (max 9), clipped at 100, stable sort."""
    texts = texts or [q["text"] for q in Q]
    M = json.load(open(ROOT / "public/search/manifest.json")); C = M["calibration"]
    ids = json.load(open(ROOT / "public/search/index.json"))
    V = np.frombuffer(open(ROOT / "public/search/vectors.i8.bin", "rb").read(), dtype=np.int8).reshape(-1, M["dimensions"]).astype(np.float32) / 127
    order = np.array([IDX[i] for i in ids])
    qe = query_emb("bge-small", texts)
    lex = Lexical(prod_lex_text)
    out = []
    for qi, text in enumerate(texts):
        cos = np.zeros(len(F), dtype=np.float32); cos[order] = V @ qe[qi]
        z = (cos - C["lo"]) / (C["hi"] - C["lo"]); k = C.get("scaleAtHi", 0.85)
        sem = np.where(z <= 0, 0, np.where(z <= 1, k * z, k + (1 - k) * (1 - np.exp(-2 * (z - 1)))))
        hs = hints(text); s = np.zeros(len(F), dtype=np.float32)
        for i, f in enumerate(F):
            b = sum(0.03 for d, c in hs if has_label(f, d, c))
            s[i] = min(1.0, 0.75 * sem[i] + 0.25 * lex.prod(text, i) + min(0.09, b))
        # JS iterates in vector order and sorts stably
        idx = order[np.argsort(-s[order], kind="stable")][:50]
        out.append([F[i]["id"] for i in idx])
    return out

def system_dense(name, views=("summary", "bio"), texts=None):
    S = dense_scores(name, views, texts)
    return [rank(S[i]) for i in range(S.shape[0])]

# ---------- metrics ----------
def load_judgments():
    jp = ROOT / "pipeline/eval/judgments.json"
    return json.load(open(jp, encoding="utf-8")) if jp.exists() else {}

def ndcg(ranked, rel, k=10):
    dcg = sum((2 ** rel.get(d, 0) - 1) / math.log2(i + 2) for i, d in enumerate(ranked[:k]))
    ideal = sorted(rel.values(), reverse=True)[:k]
    idcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(ideal))
    return dcg / idcg if idcg else 0.0

def evaluate(runs, J, qids=None, k=10):
    """runs: list (aligned with Q) of ranked id lists. Returns dict of mean metrics and unjudged rate."""
    res = {"ndcg": [], "p": [], "mrr": [], "unj": []}
    for q, ranked in zip(Q, runs):
        if qids and q["id"] not in qids: continue
        rel = J.get(q["id"], {})
        if not rel: continue
        res["ndcg"].append(ndcg(ranked, rel, k))
        res["p"].append(sum(1 for d in ranked[:k] if rel.get(d, 0) >= 2) / k)
        rr = next((1 / (i + 1) for i, d in enumerate(ranked[:k]) if rel.get(d, 0) >= 2), 0.0); res["mrr"].append(rr)
        res["unj"].append(sum(1 for d in ranked[:k] if d not in rel) / k)
    return {m: float(np.mean(v)) if v else float("nan") for m, v in res.items()}
