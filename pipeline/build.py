#!/usr/bin/env python
"""Build site data from pipeline outputs.

  python pipeline/build.py [--skip-logos] [--skip-embed]

Inputs : data/programs.json, data/raw/*.json, data/labels/*.json, pipeline/taxonomy.json
Outputs: src/data/{programs,faculty,taxonomy,meta}.json
         public/search/{manifest.json,index.json,vectors.i8.bin}
         public/schools/<slug>.png (favicons)

Profile text (raw "bio") is read only to compute the embeddings; it is never written to the site.
No faculty photos are downloaded or published.
"""
import argparse, io, json, re, sys, unicodedata
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36 CommPhDExplorer/0.1")
MODEL = "BAAI/bge-small-en-v1.5"
BROWSER_MODEL = "Xenova/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s

def norm_name(s):
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower())

def short_name(u):
    m = {"University of California, Santa Barbara": "UC Santa Barbara", "University of California, Davis": "UC Davis",
         "University of California, Los Angeles": "UCLA", "University of California, San Diego": "UC San Diego",
         "University of Texas at Austin": "UT Austin", "University of Illinois Urbana-Champaign": "Illinois",
         "University of Illinois Chicago": "UIC", "University of Minnesota, Twin Cities": "Minnesota",
         "University of Wisconsin–Madison": "Wisconsin", "University of Wisconsin–Milwaukee": "UW–Milwaukee",
         "Pennsylvania State University": "Penn State", "University of Pennsylvania": "Penn",
         "University of Southern California": "USC", "University of Michigan": "Michigan",
         "University of North Carolina at Chapel Hill": "UNC Chapel Hill", "University of Maryland, College Park": "Maryland",
         "University of Massachusetts Amherst": "UMass Amherst", "University at Buffalo, SUNY": "Buffalo",
         "Rutgers University–New Brunswick": "Rutgers", "Massachusetts Institute of Technology": "MIT",
         "University of Tennessee, Knoxville": "Tennessee", "Texas A&M University": "Texas A&M",
         "North Carolina State University": "NC State", "University of Colorado Boulder": "CU Boulder",
         "Louisiana State University": "LSU", "Georgia State University": "Georgia State",
         "University of Hawaii at Manoa": "Hawaiʻi", "University of Nebraska–Lincoln": "Nebraska"}
    if u in m: return m[u]
    u2 = re.sub(r"^(The )?University of ", "", u)
    u2 = re.sub(r"^(.*?) University$", r"\1", u2)
    return u2

def load_json(p):
    return json.load(open(p, encoding="utf-8"))

def fetch_bytes(url, timeout=25):
    import requests
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    return r.content


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-logos", action="store_true")
    ap.add_argument("--skip-embed", action="store_true")
    ap.add_argument("--only", help="comma-separated slugs (pilot builds)")
    a = ap.parse_args()

    tax = load_json(ROOT / "pipeline" / "taxonomy.json")
    programs = load_json(ROOT / "data" / "programs.json")
    if a.only:
        keep = set(a.only.split(","))
        programs = [p for p in programs if p["slug"] in keep]
    out_dir = ROOT / "src" / "data"; out_dir.mkdir(parents=True, exist_ok=True)
    (ROOT / "public" / "search").mkdir(parents=True, exist_ok=True)
    (ROOT / "public" / "schools").mkdir(parents=True, exist_ok=True)

    label_text = {dim: d["labels"] for dim, d in tax["dimensions"].items()}
    faculty, bios, programs_out = [], {}, []
    stats = {"programs": 0, "faculty": 0, "with_labels": 0}

    for p in programs:
        slug = p["slug"]
        rawp = ROOT / "data" / "raw" / f"{slug}.json"
        if not rawp.exists():
            print(f"!! no raw data for {slug}, skipping"); continue
        raw = load_json(rawp)
        labp = ROOT / "data" / "labels" / f"{slug}.json"
        labels = {norm_name(f["name"]): f for f in load_json(labp)["faculty"]} if labp.exists() else {}
        if not labp.exists(): print(f"!! no labels for {slug}")
        seen, count, ranks = set(), 0, {"Professor": 0, "Associate Professor": 0, "Assistant Professor": 0}
        sn = short_name(p["university"])
        for f in raw["faculty"]:
            key = norm_name(f["name"])
            if key in seen or f.get("rank") not in ranks: continue
            seen.add(key)
            fid = slugify(f"{sn}-{f['name']}")
            lab = labels.get(key)
            if lab: stats["with_labels"] += 1
            lab_out = {}
            for dim in tax["dimensions"]:
                items = (lab or {}).get("labels", {}).get(dim, []) if lab else []
                lab_out[dim] = [{"c": it["code"], "p": bool(it.get("primary"))} for it in items if it.get("code") in label_text[dim]]
            rec = {
                "id": fid, "name": f["name"], "u": slug, "dept": f.get("department") or "",
                "rank": f["rank"], "title": f.get("title") or f["rank"],
                "profile": f.get("profile_url"), "site": f.get("personal_url") or None,
                "scholar": f.get("google_scholar_url") or None,
                "areas": [x for x in (f.get("research_areas") or []) if x][:8],
                "summary": (lab or {}).get("summary") or "", "summary_zh": (lab or {}).get("summary_zh") or "",
                "conf": (lab or {}).get("confidence") or "low", "labels": lab_out,
                "kw": [k.lower() for k in ((lab or {}).get("keywords") or [])][:12],
                "src": sorted(set(f.get("sources") or ["department_profile"])),
                "scraped": raw.get("scraped_at"),
            }
            bios[fid] = (f.get("bio") or "")[:4000]
            faculty.append(rec); count += 1; ranks[f["rank"]] += 1
        # logo
        logo = None
        if not a.skip_logos and p.get("domain"):
            lp = ROOT / "public" / "schools" / f"{slug}.png"
            if lp.exists():
                logo = f"schools/{slug}.png"
            else:
                for url in (f"https://www.google.com/s2/favicons?domain={p['domain']}&sz=64",
                            f"https://{p['domain']}/favicon.ico"):
                    try:
                        data = fetch_bytes(url, timeout=15)
                        from PIL import Image
                        im = Image.open(io.BytesIO(data)).convert("RGBA")
                        if im.size[0] < 16: continue
                        im = im.resize((64, 64), Image.LANCZOS)
                        im.save(lp, "PNG"); logo = f"schools/{slug}.png"; break
                    except Exception as e:
                        sys.stderr.write(f"logo failed {slug} {url}: {str(e)[:60]}\n")
        programs_out.append({
            "slug": slug, "name": p["university"], "short": sn, "city": p["city"], "state": p["state"],
            "lat": p["latitude"], "lng": p["longitude"], "domain": p.get("domain"), "logo": logo,
            "nca": p.get("nca_guide_units") or [],
            "units": [{"name": u["name"], "school": u.get("school"), "url": u.get("unit_url"),
                       "phd": u.get("phd_program_name"), "phd_url": u.get("phd_program_url"),
                       "directory": u.get("directory_url")} for u in p["units"] if u.get("include")],
            "n": count, "ranks": ranks, "notes": p.get("notes") or "",
        })
        stats["programs"] += 1; stats["faculty"] += count
        print(f"{slug:45s} faculty={count:3d} labels={sum(1 for f in raw['faculty'] if norm_name(f['name']) in labels):3d}")

    # embeddings
    index, vec_rows = [], []
    if not a.skip_embed:
        from sentence_transformers import SentenceTransformer
        import numpy as np
        model = SentenceTransformer(MODEL)
        # Two views per person, averaged: (A) concise LLM summary + keywords, (B) profile text.
        # Chosen over a single concatenated text after comparing top-vs-median gaps on probe queries (docs/PLAN.md).
        view_a, view_b = [], []
        for r in faculty:
            a_txt = " ".join(x for x in [r["summary"], ("Keywords: " + ", ".join(r["kw"]) + ".") if r["kw"] else ""] if x).strip()
            b_txt = (bios.get(r["id"], "") or "").strip()
            if len(b_txt) < 200:
                b_txt = " ".join(x for x in [r["title"], r["dept"], ("Research areas: " + "; ".join(r["areas"]) + ".") if r["areas"] else "", b_txt] if x)
            view_a.append(a_txt or b_txt); view_b.append(b_txt[:1500] or a_txt)
        ea = model.encode(view_a, batch_size=64, normalize_embeddings=True, show_progress_bar=True)
        eb = model.encode(view_b, batch_size=64, normalize_embeddings=True, show_progress_bar=True)
        emb = ea + eb
        emb = emb / np.linalg.norm(emb, axis=1, keepdims=True)
        # calibration from realistic probe queries
        probes = load_json(ROOT / "pipeline" / "probes.json")["probes"]
        qv = model.encode([QUERY_PREFIX + q for q in probes], normalize_embeddings=True)
        deq = np.clip(np.round(emb * 127), -127, 127) / 127.0
        cos = qv @ deq.T
        hi_pct = 99.5 if len(faculty) >= 400 else 97.5
        lo = float(np.median(np.percentile(cos, 75, axis=1)))
        hi = float(np.median(np.percentile(cos, hi_pct, axis=1)))
        print(f"calibration: lo(p75)={lo:.4f} hi(p{hi_pct})={hi:.4f} over {len(probes)} probes")
        q = np.clip(np.round(emb * 127), -127, 127).astype(np.int8)
        (ROOT / "public" / "search" / "vectors.i8.bin").write_bytes(q.tobytes())
        for i, r in enumerate(faculty):
            r["v"] = i
        json.dump({"model": BROWSER_MODEL, "dimensions": int(emb.shape[1]), "vectorCount": len(faculty),
                   "quantizationScale": 127, "queryPrefix": QUERY_PREFIX, "pooling": "cls", "normalize": True,
                   "calibration": {"lo": round(lo, 4), "hi": round(hi, 4), "hiPercentile": hi_pct, "probes": len(probes), "scaleAtHi": 0.85},
                   "built": date.today().isoformat()},
                  open(ROOT / "public" / "search" / "manifest.json", "w"), indent=1)
        json.dump([r["id"] for r in faculty], open(ROOT / "public" / "search" / "index.json", "w"))
    else:
        for i, r in enumerate(faculty): r["v"] = i

    json.dump(programs_out, open(out_dir / "programs.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump(faculty, open(out_dir / "faculty.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump(tax, open(out_dir / "taxonomy.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    stats["built"] = date.today().isoformat()
    json.dump(stats, open(out_dir / "meta.json", "w"), indent=1)
    print(json.dumps(stats, indent=1))

if __name__ == "__main__":
    main()
