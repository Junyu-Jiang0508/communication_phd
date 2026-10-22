export const DIMS = ['topic', 'approach', 'data', 'setting', 'region'] as const;
export type Dim = (typeof DIMS)[number];
export type LabelRef = { c: string; p: boolean };
export type Faculty = {
  id: string; name: string; u: string; dept: string; rank: string; title: string;
  profile: string | null; site: string | null; scholar: string | null; photo: string | null;
  areas: string[]; summary: string; summary_zh: string; conf: string;
  labels: Record<Dim, LabelRef[]>; kw: string[]; src: string[]; scraped: string | null; v: number;
};
export type Unit = { name: string; school: string | null; url: string | null; phd: string | null; phd_url: string | null; directory: string | null };
export type Program = {
  slug: string; name: string; short: string; city: string; state: string; lat: number; lng: number;
  domain: string | null; logo: string | null; shanghai: string | null; nca: string[]; units: Unit[];
  n: number; ranks: Record<string, number>; notes: string;
};
export type Taxonomy = { dimensions: Record<Dim, { label: string; label_zh: string; description: string; description_zh: string; labels: Record<string, string>; labels_zh: Record<string, string>; labels_short: Record<string, string>; labels_short_zh: Record<string, string> }> };

export const BASE = (import.meta.env.BASE_URL as string).replace(/\/+$/, '') + '/';
export const withBase = (p: string) => BASE + p.replace(/^\/+/, '');
export const initials = (name: string) => name.split(/\s+/).filter(Boolean).filter((w) => !/^\(.*\)$/.test(w)).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
export const lastName = (name: string) => { const parts = name.replace(/,.*$/, '').trim().split(/\s+/); return parts[parts.length - 1] || name; };
export function labelText(tax: Taxonomy, dim: Dim, code: string, lang: string) {
  const d = tax.dimensions[dim];
  return (lang === 'zh' ? d.labels_short_zh?.[code] : d.labels_short?.[code]) || d.labels[code] || code;
}
export function labelFull(tax: Taxonomy, dim: Dim, code: string, lang: string) {
  const d = tax.dimensions[dim];
  return (lang === 'zh' ? d.labels_zh[code] : d.labels[code]) || code;
}
export function dimLabel(tax: Taxonomy, dim: Dim, lang: string) {
  const d = tax.dimensions[dim];
  return lang === 'zh' ? d.label_zh : d.label;
}
export const RANK_ORDER: Record<string, number> = { 'Professor': 0, 'Associate Professor': 1, 'Assistant Professor': 2 };
export const esc = (s: string) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
