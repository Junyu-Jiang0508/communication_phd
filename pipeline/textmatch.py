"""Text side of matching, shared by build.py and the evaluation harness. Mirrors src/lib/match.ts exactly:
the same tokenizer, the same "published" document text and the same BM25 (k1=1.2, b=0.75)."""
import math, re

STOP = set('a an the and or of in on for to with from by at as is are be been being this that these those i my me we our you your it its their they them he she his her how what which who whom where when why while about into over under between among through during also both such than then there here very more most much many some any each other same so too not no nor only own just can could would should will shall may might must do does did doing have has had having using use used uses study studies studying research interested interest interests work works working want wants focus focused focusing especially particularly including include includes like well across within without via towards toward against around'.split())

def stem(w):
    if len(w) <= 4: return w
    o = w
    w = re.sub(r"(ization|isation)$", "ize", w)
    w = re.sub(r"(ational|ically)$", "al", w)
    w = re.sub(r"(ies)$", "y", w)
    w = re.sub(r"(ness|ment|ings?|ers?|ed|es|s)$", lambda m: "s" if (m.group(0) == "s" and o.endswith("ss")) else "", w)
    w = re.sub(r"(ic|al|ive|ous)$", "", w)
    return w

def tokenize(text):
    t = re.sub(r"[’']", "", text.lower())
    return [w for w in (stem(x) for x in re.split(r"[^\w-]+|_", t)) if len(w) > 2 and w not in STOP]

def published_text(f, tax):
    """Everything about a person that the site publishes and the browser can read (no profile text)."""
    parts = [f["summary"]]
    if f["kw"]: parts.append("Keywords: " + ", ".join(f["kw"]) + ".")
    if f["areas"]: parts.append("Research areas: " + "; ".join(f["areas"]) + ".")
    labs = [tax["dimensions"][d]["labels_short"][l["c"]] for d in ("topic", "approach", "data", "setting", "region") for l in f["labels"].get(d, [])]
    if labs: parts.append("Labels: " + ", ".join(labs) + ".")
    return " ".join(parts)

class BM25:
    def __init__(self, texts, k1=1.2, b=0.75):
        self.k1, self.b = k1, b
        self.tf, self.len, self.df = [], [], {}
        for text in texts:
            toks = tokenize(text); tf = {}
            for t in toks: tf[t] = tf.get(t, 0) + 1
            for t in tf: self.df[t] = self.df.get(t, 0) + 1
            self.tf.append(tf); self.len.append(len(toks))
        self.N = len(texts); self.avg = sum(self.len) / max(1, self.N)

    def idf(self, t):
        d = self.df.get(t, 0); return math.log(1 + (self.N - d + 0.5) / (d + 0.5))

    def scores(self, query):
        q = list(dict.fromkeys(tokenize(query))); out = [0.0] * self.N
        for t in q:
            if t not in self.df: continue
            w = self.idf(t)
            for i, tf in enumerate(self.tf):
                c = tf.get(t, 0)
                if c: out[i] += w * (c * (self.k1 + 1)) / (c + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
        return out
