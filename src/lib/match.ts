// Browser-side matching, set up from the judged evaluation in pipeline/eval:
// arctic-embed-m embeddings + BM25 over the published text, fused as per-query z-scores, small label hints,
// a cross-encoder that re-reads the top matches, and on-device translation of Chinese queries.
import type { Faculty, Program, Taxonomy, Dim } from './data';
import { DIMS, labelText } from './data';

export type Hint = { dim: Dim; code: string; label: string; mode: 'off' | 'boost' | 'require' };
export type Scored = { f: Faculty; sem: number; lex: number; boost: number; base: number; score: number; terms: string[]; labels: { dim: Dim; code: string }[]; moved?: number };
export type Calibration = { lo: number; hi: number; scaleAtHi?: number };
export type Manifest = {
  model: string; dimensions: number; quantizationScale: number; queryPrefix?: string; pooling?: string;
  fusion: { dense: number; lex: number }; hints: Partial<Record<Dim, number>>;
  rerank: { model: string; k: number; mix: number }; translate: { model: string; glossary?: Record<string, string> };
  semCalibration: Calibration; calibration: Calibration;
};

const CDN = 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.3.1';
const MIRROR = 'https://hf-mirror.com';
const STOP = new Set('a an the and or of in on for to with from by at as is are be been being this that these those i my me we our you your it its their they them he she his her how what which who whom where when why while about into over under between among through during also both such than then there here very more most much many some any each other same so too not no nor only own just can could would should will shall may might must do does did doing have has had having using use used uses study studies studying research interested interest interests work works working want wants focus focused focusing especially particularly including include includes like well across within without via towards toward against around'.split(' '));

export function tokenize(text: string): string[] {
  return text.toLowerCase().replace(/[’']/g, '').split(/[^\p{L}\p{N}-]+/u).map(stem).filter((w) => w.length > 2 && !STOP.has(w));
}
function stem(w: string) {
  if (w.length <= 4) return w;
  return w.replace(/(ization|isation)$/, 'ize').replace(/(ational|ically)$/, 'al').replace(/(ies)$/, 'y').replace(/(ness|ment|ings?|ers?|ed|es|s)$/, (m) => (m === 's' && /ss$/.test(w) ? 's' : '')).replace(/(ic|al|ive|ous)$/, '');
}

// ---- BM25 over the published text (same text and formula as pipeline/textmatch.py) ----
export function publishedText(f: Faculty, tax: Taxonomy) {
  const parts = [f.summary];
  if (f.kw.length) parts.push('Keywords: ' + f.kw.join(', ') + '.');
  if (f.areas.length) parts.push('Research areas: ' + f.areas.join('; ') + '.');
  const labs: string[] = [];
  for (const d of DIMS) for (const l of f.labels[d] ?? []) labs.push(tax.dimensions[d].labels_short[l.c]);
  if (labs.length) parts.push('Labels: ' + labs.join(', ') + '.');
  return parts.join(' ');
}
type Doc = { tf: Map<string, number>; len: number };
let docs: Doc[] = [], df = new Map<string, number>(), N = 0, avgLen = 1;
export function indexFaculty(list: Faculty[], tax: Taxonomy) {
  docs = []; df = new Map(); N = list.length; let total = 0;
  for (const f of list) {
    const toks = tokenize(publishedText(f, tax));
    const tf = new Map<string, number>();
    for (const t of toks) tf.set(t, (tf.get(t) || 0) + 1);
    for (const t of tf.keys()) df.set(t, (df.get(t) || 0) + 1);
    docs.push({ tf, len: toks.length }); total += toks.length;
  }
  avgLen = total / Math.max(1, N);
}
export function bm25(query: string): { scores: Float32Array; q: string[] } {
  const q = Array.from(new Set(tokenize(query)));
  const out = new Float32Array(N);
  for (const t of q) {
    const d = df.get(t); if (!d) continue;
    const w = Math.log(1 + (N - d + 0.5) / (d + 0.5));
    for (let i = 0; i < N; i++) {
      const c = docs[i].tf.get(t);
      if (c) out[i] += (w * (c * 2.2)) / (c + 1.2 * (0.25 + (0.75 * docs[i].len) / avgLen));
    }
  }
  return { scores: out, q };
}

// Hints: regex detectors over the query that map to taxonomy codes (used as boosts, or requirements when the user asks)
const DETECT: { dim: Dim; code: string; re: RegExp }[] = [
  { dim: 'region', code: 'R_CHINA', re: /\b(china|chinese|prc|hong kong|weibo|wechat|douyin|bilibili|xiaohongshu|sinophone)\b/i },
  { dim: 'region', code: 'R_EAST_ASIA', re: /\b(japan|japanese|korea|korean|taiwan|taiwanese|east asia)\b/i },
  { dim: 'region', code: 'R_SOUTH_SE_ASIA', re: /\b(india|indian|south asia|southeast asia|indonesia|philippines|vietnam|thailand|malaysia|singapore)\b/i },
  { dim: 'region', code: 'R_MIDDLE_EAST', re: /\b(middle east|arab|iran|turkey|israel|egypt|north africa|mena)\b/i },
  { dim: 'region', code: 'R_AFRICA', re: /\b(africa|african|nigeria|kenya|ghana|south africa)\b/i },
  { dim: 'region', code: 'R_LATIN_AMERICA', re: /\b(latin america|brazil|mexico|argentina|chile|colombia|caribbean)\b/i },
  { dim: 'region', code: 'R_EUROPE', re: /\b(europe|european|germany|france|uk|britain|british|russia|ukraine|post-soviet|eastern europe)\b/i },
  { dim: 'region', code: 'R_US', re: /\b(united states|u\.s\.|american politics|american public)\b/i },
  { dim: 'region', code: 'R_GLOBAL_CROSS_NATIONAL', re: /\b(cross-national|comparative|global south|transnational|multi-country|cross-cultural)\b/i },
  { dim: 'approach', code: 'A_COMPUTATIONAL', re: /\b(computational|text-as-data|text analysis|nlp|natural language processing|machine learning|large language models?|llms?|topic model|word embeddings?|digital trace|big data)\b/i },
  { dim: 'approach', code: 'A_EXPERIMENT', re: /\b(experiments?|experimental|causal|randomized|rct|field experiment)\b/i },
  { dim: 'approach', code: 'A_SURVEY', re: /\b(surveys?|panel data|questionnaire|measurement|scale development)\b/i },
  { dim: 'approach', code: 'A_NETWORK', re: /\b(network analysis|social networks?|diffusion|network science)\b/i },
  { dim: 'approach', code: 'A_QUALITATIVE', re: /\b(qualitative|interviews?|ethnograph\w*|focus groups?|fieldwork)\b/i },
  { dim: 'approach', code: 'A_CRITICAL_INTERPRETIVE', re: /\b(critical (theory|cultural|discourse|race|studies|analysis|approach\w*)|interpretive|rhetorical criticism|discourse analysis|cultural studies|feminist|postcolonial|queer theory)\b/i },
  { dim: 'approach', code: 'A_HISTORICAL_ARCHIVAL', re: /\b(historical|archiv\w*|history of)\b/i },
  { dim: 'approach', code: 'A_PHYSIO_NEURO', re: /\b(psychophysiolog\w*|eye[- ]tracking|neuro\w*|fmri|eeg|biometric)\b/i },
  { dim: 'topic', code: 'T_POLITICAL', re: /\b(political communication|public opinion|elections?|electoral|(political|election|presidential|electoral) campaigns?|polarization|partisan\w*|democrac\w*|propaganda|populis\w*|voters?|voting)\b/i },
  { dim: 'topic', code: 'T_MISINFO_TRUST', re: /\b(misinformation|disinformation|rumou?rs?|fake news|fact-?check\w*|conspiracy|trust in (news|media|journalism|science))\b/i },
  { dim: 'topic', code: 'T_JOURNALISM', re: /\b(journalis\w*|news(room|rooms| media| production| audiences?)|press freedom|reporters?)\b/i },
  { dim: 'topic', code: 'T_PLATFORMS_AI', re: /\b(platforms?|algorithm\w*|artificial intelligence|generative ai|chatbots?|recommender|content moderation|platform governance|datafication)\b/i },
  { dim: 'topic', code: 'T_HEALTH', re: /\b(health|vaccin\w*|patients?|public health|risk communication|crisis communication|mental health)\b/i },
  { dim: 'topic', code: 'T_SCIENCE_ENV', re: /\b(science communication|climate|environment\w*|sustainability)\b/i },
  { dim: 'topic', code: 'T_INTERPERSONAL', re: /\b(interpersonal|relationships?|family communication|romantic|friendship|dating)\b/i },
  { dim: 'topic', code: 'T_ORGANIZATIONAL', re: /\b(organizational communication|organizational|workplaces?|leadership|employees?|teams at work)\b/i },
  { dim: 'topic', code: 'T_STRATEGIC_PR_AD', re: /\b(public relations|advertising|strategic communication|branding|marketing|corporate communication)\b/i },
  { dim: 'topic', code: 'T_CRITICAL_CULTURAL', re: /\b(race|racial|gender|feminis\w*|queer|lgbtq?\+?|identity|intersectional\w*|decolonial|whiteness)\b/i },
  { dim: 'topic', code: 'T_MEDIA_EFFECTS_PSYCH', re: /\b(media effects|media psychology|persuasion|emotion\w*|attention|cognitive|narrative persuasion|parasocial)\b/i },
  { dim: 'topic', code: 'T_GLOBAL_INTERCULTURAL', re: /\b(intercultural|international communication|global media|diaspora|migrants?|migration|nationalis\w*)\b/i },
  { dim: 'topic', code: 'T_ENTERTAINMENT_GAMES', re: /\b(entertainment|video ?games?|gaming|fandom|fans|esports|popular culture|television|streaming)\b/i },
  { dim: 'topic', code: 'T_HCI_CMC', re: /\b(human-computer interaction|hci|computer-mediated|virtual reality|augmented reality|social robots?|chatbots?|avatars?)\b/i },
  { dim: 'topic', code: 'T_RHETORIC', re: /\b(rhetoric\w*|public address|argumentation|oratory)\b/i },
  { dim: 'topic', code: 'T_MEDIA_INDUSTRIES_POLICY', re: /\b(media industr\w*|media policy|regulation|media law|political economy of|telecommunications)\b/i },
  { dim: 'topic', code: 'T_CHILDREN_FAMILY_MEDIA', re: /\b(children|adolescents?|youth|teens?|media literacy|parent\w*)\b/i },
  { dim: 'topic', code: 'T_LANGUAGE_INTERACTION', re: /\b(conversation analysis|nonverbal|language and social interaction|discourse)\b/i },
];
export function detectHints(text: string, tax: Taxonomy, lang: string): Hint[] {
  const out: Hint[] = [];
  for (const d of DETECT) if (d.re.test(text) && !out.some((h) => h.code === d.code)) {
    out.push({ dim: d.dim, code: d.code, label: labelText(tax, d.dim, d.code, lang), mode: 'boost' });
  }
  return out.slice(0, 8);
}

// ---- models (Transformers.js from the CDN; Hugging Face, then hf-mirror.com) ----
export type Progress = (p: { phase: 'download' | 'ready'; pct: number; file?: string }) => void;
let libPromise: Promise<any> | null = null;
const lib = () => (libPromise ||= import(/* @vite-ignore */ CDN).then((m: any) => { m.env.allowLocalModels = false; return m; }));
const loaded = new Map<string, Promise<any>>();
function once<T>(key: string, make: () => Promise<T>): Promise<T> {
  let p = loaded.get(key);
  if (!p) { p = make().catch((e) => { loaded.delete(key); throw e; }); loaded.set(key, p); }
  return p as Promise<T>;
}
function progressCb(onProgress?: Progress) {
  const files = new Map<string, { loaded: number; total: number }>();
  return (info: any) => {
    if (!onProgress) return;
    if (info.status === 'progress' && info.file) {
      files.set(info.file, { loaded: info.loaded || 0, total: info.total || 0 });
      let l = 0, t = 0; for (const v of files.values()) { l += v.loaded; t += v.total; }
      onProgress({ phase: 'download', pct: t ? Math.round((100 * l) / t) : 0, file: info.file });
    } else if (info.status === 'ready') onProgress({ phase: 'ready', pct: 100 });
  };
}
// huggingface.co may be unreachable in some regions: retry once through the mirror
async function withMirror<T>(make: () => Promise<T>): Promise<T> {
  try { return await make(); } catch (e) {
    const { env } = await lib();
    if (env.remoteHost === MIRROR) throw e;
    env.remoteHost = MIRROR; return await make();
  }
}

type Pipe = (text: string, opts: any) => Promise<{ data: Float32Array }>;
let manifestPromise: Promise<{ manifest: Manifest; ids: string[]; vec: Int8Array }> | null = null;
export function loadIndex(base: string) {
  return (manifestPromise ||= Promise.all([
    fetch(base + 'search/manifest.json').then((r) => { if (!r.ok) throw new Error('manifest'); return r.json(); }),
    fetch(base + 'search/index.json').then((r) => { if (!r.ok) throw new Error('index'); return r.json(); }),
    fetch(base + 'search/vectors.i8.bin').then((r) => { if (!r.ok) throw new Error('vectors'); return r.arrayBuffer(); }),
  ]).then(([manifest, ids, buf]) => ({ manifest, ids, vec: new Int8Array(buf) })).catch((e) => { manifestPromise = null; throw e; }));
}
export function loadModel(modelId: string, onProgress: Progress): Promise<Pipe> {
  return once('embed:' + modelId, async () => {
    const { pipeline } = await lib();
    return withMirror(() => pipeline('feature-extraction', modelId, { dtype: 'q8', progress_callback: progressCb(onProgress) }));
  });
}
export async function embed(pipe: Pipe, manifest: Manifest, text: string, extra?: string): Promise<Float32Array> {
  const one = async (t: string) => {
    const out = await pipe(`${manifest.queryPrefix || ''}${t}`, { pooling: manifest.pooling || 'cls', normalize: true });
    const v = out.data as Float32Array;
    if (v.length !== manifest.dimensions) throw new Error(`unexpected vector size ${v.length}`);
    return v;
  };
  const v = await one(text);
  if (!extra) return v;
  // translated queries: the sentence and its glossary keyword line are embedded separately and averaged,
  // so a garbled machine translation cannot drown the terms the user actually wrote
  const w = await one(extra);
  const sum = v.map((x, i) => x + w[i]); let n = 0; for (const x of sum) n += x * x; n = Math.sqrt(n) || 1;
  return sum.map((x) => x / n);
}
export function semanticScores(q: Float32Array, vec: Int8Array, dims: number, scale: number): Float32Array {
  const n = vec.length / dims; const out = new Float32Array(n);
  for (let i = 0; i < n; i++) { let s = 0; const off = i * dims; for (let j = 0; j < dims; j++) s += vec[off + j] * q[j]; out[i] = s / scale; }
  return out;
}

type Reranker = { tok: any; model: any };
export function loadReranker(modelId: string, onProgress?: Progress): Promise<Reranker> {
  return once('rerank:' + modelId, async () => {
    const { AutoTokenizer, AutoModelForSequenceClassification } = await lib();
    const cb = progressCb(onProgress);
    return withMirror(async () => ({
      tok: await AutoTokenizer.from_pretrained(modelId, { progress_callback: cb }),
      model: await AutoModelForSequenceClassification.from_pretrained(modelId, { dtype: 'q8', progress_callback: cb }),
    }));
  });
}

// ---- Chinese queries: the browser's built-in translator when present, else a small translation model ----
export const hasCJK = (s: string) => /[\u3400-\u9fff\uf900-\ufaff]/.test(s);
export async function translateToEnglish(text: string, cfg: Manifest['translate'], onProgress?: Progress): Promise<{ text: string; via: 'browser' | 'model'; keywords: string }> {
  // Platform names and method terms that a small translation model garbles (抖音 -> "twitching") are looked up in a
  // glossary and appended as an English keyword line, longest first so 数字民族志 wins over 民族志.
  const g = cfg.glossary || {}; const found: string[] = []; let rest = text;
  for (const k of Object.keys(g).sort((a, b) => b.length - a.length)) if (rest.includes(k)) { found.push(g[k]); rest = rest.split(k).join(' '); }
  const keywords = found.length ? `Keywords: ${Array.from(new Set(found)).join(', ')}.` : '';
  const withKeywords = (en: string) => (keywords ? `${en} ${keywords}` : en);
  const BT = (globalThis as any).Translator;
  if (BT?.availability) {
    // A ready translator answers at once; one that still has to download its language pack gets a short wait,
    // because the download can stall (or never start) and the model below is a known quantity.
    const timeout = <T,>(ms: number, p: Promise<T>) => Promise.race([p, new Promise<never>((_, rej) => setTimeout(() => rej(new Error('timeout')), ms))]);
    try {
      const a = await timeout(3000, BT.availability({ sourceLanguage: 'zh', targetLanguage: 'en' }));
      if (a && a !== 'unavailable') {
        const run = (async () => { const tr = await BT.create({ sourceLanguage: 'zh', targetLanguage: 'en' }); return String(await tr.translate(text)).trim(); })();
        const out = await timeout(a === 'available' ? 15000 : 20000, run);
        if (out) return { text: withKeywords(out), via: 'browser', keywords };
      }
    } catch { /* fall through to the model */ }
  }
  const mt = await once('mt:' + cfg.model, async () => {
    const { pipeline } = await lib();
    return withMirror(() => pipeline('translation', cfg.model, { dtype: 'q8', progress_callback: progressCb(onProgress) }));
  });
  // sentence by sentence, which the model handles best
  const parts = text.replace(/([。！？；!?;\n])/g, '$1\u0000').split('\u0000').map((x) => x.trim()).filter(Boolean);
  const out: string[] = [];
  for (const part of parts) { const r = await mt(part, { max_new_tokens: 200 }); out.push(String(r[0]?.translation_text || '').trim()); }
  return { text: withKeywords(out.join(' ')), via: 'model', keywords };
}

// ---- scoring ----
// Map a value to 0..1 with build-time calibration: the median person for a typical query -> 0, the top ~0.5% -> 0.85.
export function rescale(x: number, c: Calibration) {
  const z = (x - c.lo) / Math.max(1e-6, c.hi - c.lo);
  const k = c.scaleAtHi ?? 0.85;
  if (z <= 0) return 0;
  if (z <= 1) return k * z;
  return k + (1 - k) * (1 - Math.exp(-2 * (z - 1))); // flattens above the anchor instead of clipping at 100
}
function zscores(a: Float32Array) {
  let m = 0; for (const v of a) m += v; m /= Math.max(1, a.length);
  let s = 0; for (const v of a) s += (v - m) ** 2;
  const sd = Math.sqrt(s / Math.max(1, a.length)) || 1;
  return a.map((v) => (v - m) / sd);
}
export type ScoreOpts = { lexWeight: number; threshold: number; ranks: Set<string>; manifest: Manifest };
export function score(list: Faculty[], ids: string[], cos: Float32Array, query: string, hints: Hint[], opts: ScoreOpts): Scored[] {
  const byId = new Map(list.map((f, i) => [f.id, i]));
  const dense = new Float32Array(list.length);
  for (let r = 0; r < ids.length; r++) { const i = byId.get(ids[r]); if (i != null) dense[i] = cos[r]; }
  const { scores: lexRaw, q } = bm25(query);
  const zd = zscores(dense), zl = zscores(lexRaw);
  let maxLex = 1e-6; for (const v of lexRaw) if (v > maxLex) maxLex = v;
  const wl = opts.lexWeight, wd = 1 - wl, hw = opts.manifest.hints || {};
  const out: Scored[] = [];
  for (let i = 0; i < list.length; i++) {
    const f = list[i];
    if (opts.ranks.size && !opts.ranks.has(f.rank)) continue;
    let boost = 0, ok = true; const labels: { dim: Dim; code: string }[] = [];
    for (const h of hints) {
      if (h.mode === 'off') continue;
      if ((f.labels[h.dim] ?? []).some((l) => l.c === h.code)) { boost += hw[h.dim] ?? 0; labels.push({ dim: h.dim, code: h.code }); }
      else if (h.mode === 'require') ok = false;
    }
    if (!ok) continue;
    const base = wd * zd[i] + wl * zl[i] + boost;
    const fit = rescale(base, opts.manifest.calibration);
    if (fit < opts.threshold) continue;
    out.push({ f, sem: rescale(dense[i], opts.manifest.semCalibration), lex: lexRaw[i] / maxLex, boost, base, score: fit, terms: q.filter((t) => docs[i].tf.has(t)), labels });
  }
  out.sort((a, b) => b.base - a.base);
  return out;
}
const ceCache = new Map<string, number>(); // query + id -> cross-encoder logit (option changes reuse it)
// Re-read the top k with the cross-encoder and blend its judgement with the first-pass order.
// Fit values stay attached to positions (sorted), so the list stays monotonic.
export async function rerank(rr: Reranker, query: string, scored: Scored[], rk: Manifest['rerank'], tax: Taxonomy): Promise<Scored[]> {
  const top = scored.slice(0, rk.k);
  if (top.length < 2) return scored;
  const key = (s: Scored) => query + '\u0001' + s.f.id;
  const todo = top.filter((s) => !ceCache.has(key(s)));
  if (todo.length) {
    const inputs = rr.tok(new Array(todo.length).fill(query), { text_pair: todo.map((s) => publishedText(s.f, tax)), padding: true, truncation: true, max_length: 512 });
    const { logits } = await rr.model(inputs);
    const data = logits.data as Float32Array;
    todo.forEach((s, i) => ceCache.set(key(s), data[i]));
  }
  const zc = zscores(Float32Array.from(top, (s) => ceCache.get(key(s))!));
  const prior = zscores(Float32Array.from(top, (_, i) => -Math.log1p(i)));
  const order = top.map((s, i) => ({ s, i, v: rk.mix * zc[i] + (1 - rk.mix) * prior[i] })).sort((a, b) => b.v - a.v);
  const fits = top.map((s) => s.score);
  return order.map((o, j) => ({ ...o.s, score: fits[j], moved: o.i - j })).concat(scored.slice(rk.k));
}
export function programFit(scored: Scored[], programs: Program[]) {
  const by = new Map<string, Scored[]>();
  for (const s of scored) { const arr = by.get(s.f.u) || []; arr.push(s); by.set(s.f.u, arr); }
  const rows = programs.filter((p) => by.has(p.slug)).map((p) => {
    const arr = by.get(p.slug)!; const top = arr.slice(0, 3);
    const fit = (top[0]?.score || 0) * 0.5 + (top[1]?.score || 0) * 0.3 + (top[2]?.score || 0) * 0.2;
    return { p, fit, n: arr.length, top };
  });
  rows.sort((a, b) => b.fit - a.fit);
  return rows;
}
