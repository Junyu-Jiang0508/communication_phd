// Browser-side matching: bge-small embeddings (transformers.js) + keyword score + label boosts.
import type { Faculty, Program, Taxonomy, Dim } from './data';
import { DIMS, labelText } from './data';

export type Hint = { dim: Dim; code: string; label: string; mode: 'off' | 'boost' | 'require' };
export type Scored = { f: Faculty; sem: number; lex: number; boost: number; score: number; terms: string[]; labels: { dim: Dim; code: string }[] };

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

type Doc = { tf: Map<string, number>; len: number; text: string };
let docs: Doc[] = [], df = new Map<string, number>(), N = 0, avgLen = 1;
export function indexFaculty(list: Faculty[], tax: Taxonomy) {
  docs = []; df = new Map(); N = list.length; let total = 0;
  for (const f of list) {
    const parts = [f.summary, f.areas.join(' '), f.kw.join(' ')];
    for (const d of DIMS) for (const l of f.labels[d] ?? []) parts.push(tax.dimensions[d].labels[l.c] || '');
    const text = parts.join(' ').toLowerCase();
    const toks = tokenize(text);
    const tf = new Map<string, number>();
    for (const t of toks) tf.set(t, (tf.get(t) || 0) + 1);
    for (const t of tf.keys()) df.set(t, (df.get(t) || 0) + 1);
    docs.push({ tf, len: toks.length, text }); total += toks.length;
  }
  avgLen = total / Math.max(1, N);
}
const idf = (t: string) => Math.log(1 + (N - (df.get(t) || 0) + 0.5) / ((df.get(t) || 0) + 0.5));
export function lexical(query: string, i: number, f: Faculty): { score: number; terms: string[] } {
  const d = docs[i]; if (!d) return { score: 0, terms: [] };
  const q = Array.from(new Set(tokenize(query)));
  if (!q.length) return { score: 0, terms: [] };
  let s = 0, max = 0; const hits: string[] = [];
  for (const t of q) {
    const w = idf(t); max += w;
    const tf = d.tf.get(t) || 0;
    if (tf) { s += w * ((tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * d.len / avgLen))); hits.push(t); }
  }
  // exact keyword phrases from the label stage count extra
  const ql = query.toLowerCase();
  for (const k of f.kw) if (k.length > 3 && ql.includes(k)) { s += 1.2; hits.push(k); }
  const norm = Math.max(4, max * 0.45);
  return { score: Math.min(1, s / norm), terms: Array.from(new Set(hits)) };
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
  { dim: 'topic', code: 'T_MISINFO_TRUST', re: /\b(misinformation|disinformation|fake news|fact-?check\w*|conspiracy|trust in (news|media|journalism|science))\b/i },
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

// ---- model ----
type Pipe = (text: string, opts: any) => Promise<{ data: Float32Array }>;
let pipePromise: Promise<Pipe> | null = null;
let manifestPromise: Promise<{ manifest: any; ids: string[]; vec: Int8Array }> | null = null;
export type Progress = (p: { phase: 'download' | 'ready'; pct: number; file?: string }) => void;

export function loadIndex(base: string) {
  return (manifestPromise ||= Promise.all([
    fetch(base + 'search/manifest.json').then((r) => { if (!r.ok) throw new Error('manifest'); return r.json(); }),
    fetch(base + 'search/index.json').then((r) => { if (!r.ok) throw new Error('index'); return r.json(); }),
    fetch(base + 'search/vectors.i8.bin').then((r) => { if (!r.ok) throw new Error('vectors'); return r.arrayBuffer(); }),
  ]).then(([manifest, ids, buf]) => ({ manifest, ids, vec: new Int8Array(buf) })));
}
export function loadModel(modelId: string, onProgress: Progress): Promise<Pipe> {
  return (pipePromise ||= (async () => {
    const mod: any = await import(/* @vite-ignore */ CDN);
    const { pipeline, env } = mod;
    env.allowLocalModels = false;
    const files = new Map<string, { loaded: number; total: number }>();
    const cb = (info: any) => {
      if (info.status === 'progress' && info.file) {
        files.set(info.file, { loaded: info.loaded || 0, total: info.total || 0 });
        let l = 0, t = 0; for (const v of files.values()) { l += v.loaded; t += v.total; }
        onProgress({ phase: 'download', pct: t ? Math.round((100 * l) / t) : 0, file: info.file });
      } else if (info.status === 'ready') onProgress({ phase: 'ready', pct: 100 });
    };
    const make = () => pipeline('feature-extraction', modelId, { dtype: 'q8', progress_callback: cb });
    try {
      return await make();
    } catch (e) {
      // retry via mirror (huggingface.co may be unreachable in some regions)
      env.remoteHost = MIRROR; files.clear();
      return await make();
    }
  })().catch((e) => { pipePromise = null; throw e; }));
}
export async function embed(pipe: Pipe, manifest: any, text: string): Promise<Float32Array> {
  const out = await pipe(`${manifest.queryPrefix || ''}${text}`, { pooling: manifest.pooling || 'cls', normalize: true });
  const v = out.data as Float32Array;
  if (v.length !== manifest.dimensions) throw new Error(`unexpected vector size ${v.length}`);
  return v;
}

export function semanticScores(q: Float32Array, vec: Int8Array, dims: number, scale: number): Float32Array {
  const n = vec.length / dims; const out = new Float32Array(n);
  for (let i = 0; i < n; i++) { let s = 0; const off = i * dims; for (let j = 0; j < dims; j++) s += vec[off + j] * q[j]; out[i] = s / scale; }
  return out;
}
export type Calibration = { lo: number; hi: number; scaleAtHi?: number };
// Map raw cosine to 0..1 using build-time calibration: the median person for a typical query -> 0, the top ~0.5% -> 0.85.
export function rescale(cos: number, c: Calibration) {
  const z = (cos - c.lo) / Math.max(1e-6, c.hi - c.lo);
  const k = c.scaleAtHi ?? 0.85;
  if (z <= 0) return 0;
  if (z <= 1) return k * z;
  return k + (1 - k) * (1 - Math.exp(-2 * (z - 1))); // flattens above the anchor instead of clipping at 100
}

export function score(list: Faculty[], ids: string[], cos: Float32Array, query: string, hints: Hint[], opts: { lexWeight: number; threshold: number; ranks: Set<string>; calib: Calibration }): Scored[] {
  const byId = new Map(list.map((f, i) => [f.id, i]));
  const out: Scored[] = [];
  for (let r = 0; r < ids.length; r++) {
    const i = byId.get(ids[r]); if (i == null) continue;
    const f = list[i];
    if (opts.ranks.size && !opts.ranks.has(f.rank)) continue;
    const sem = rescale(cos[r], opts.calib);
    const { score: lex, terms } = lexical(query, i, f);
    let boost = 0, ok = true; const labels: { dim: Dim; code: string }[] = [];
    for (const h of hints) {
      if (h.mode === 'off') continue;
      const hasIt = (f.labels[h.dim] ?? []).some((l) => l.c === h.code);
      if (hasIt) { boost += 0.03; labels.push({ dim: h.dim, code: h.code }); }
      else if (h.mode === 'require') ok = false;
    }
    if (!ok) continue;
    const s = (1 - opts.lexWeight) * sem + opts.lexWeight * lex + Math.min(0.09, boost);
    if (s < opts.threshold) continue;
    out.push({ f, sem, lex, boost, score: Math.min(1, s), terms, labels });
  }
  out.sort((a, b) => b.score - a.score);
  return out;
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
