import { DIMS, esc, initials, labelText, labelFull, withBase, type Faculty, type Program, type Taxonomy, type Dim } from './data';
import { t, getLang } from './i18n';
import * as shortlist from './shortlist';

export function sig(score: number) {
  const n = Math.max(0, Math.min(5, Math.round(score * 5)));
  return `<span class="sig" data-n="${n}" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></span>`;
}
export function scoreHtml(score: number) {
  return `<span class="score" title="${t('fit')}">${sig(score)}<b class="num">${Math.round(score * 100)}</b></span>`;
}
export function avatar(f: Faculty, lg = false) {
  const cls = `avatar${lg ? ' lg' : ''}`;
  if (f.photo) return `<span class="${cls}"><img src="${withBase(f.photo)}" alt="" loading="lazy" width="${lg ? 96 : 44}" height="${lg ? 96 : 44}" onerror="this.replaceWith(document.createTextNode('${esc(initials(f.name))}'))"></span>`;
  return `<span class="${cls}" aria-hidden="true">${esc(initials(f.name))}</span>`;
}
export function chip(tax: Taxonomy, dim: Dim, c: string, primary = false, extra = '') {
  const lang = getLang();
  return `<span class="chip${primary ? ' primary' : ''}" data-dim="${dim}" title="${esc(labelFull(tax, dim, c, lang))}" ${extra}>${esc(labelText(tax, dim, c, lang))}${primary ? ' ★' : ''}</span>`;
}
export function saveBtn(id: string, small = true) {
  const on = shortlist.has(id);
  return `<button type="button" class="btn ${small ? 'sm' : ''} save-btn" data-save="${esc(id)}" aria-pressed="${on}">${on ? t('saved') : t('save')}</button>`;
}
export function bindSaveButtons(root: ParentNode) {
  root.querySelectorAll<HTMLButtonElement>('.save-btn').forEach((b) => {
    if (b.dataset.bound) return;
    b.dataset.bound = '1';
    b.addEventListener('click', () => {
      const on = shortlist.toggle(b.dataset.save!);
      document.querySelectorAll<HTMLButtonElement>(`.save-btn[data-save="${CSS.escape(b.dataset.save!)}"]`).forEach((x) => { x.setAttribute('aria-pressed', String(on)); x.textContent = on ? t('saved') : t('save'); });
    });
  });
}
export function personRow(f: Faculty, p: Program | undefined, tax: Taxonomy, opts: { score?: number; why?: string; chips?: Dim[]; summaryHtml?: string; maxChips?: number } = {}) {
  const lang = getLang();
  const dims = opts.chips ?? ['topic', 'approach'];
  const prim: string[] = [], rest: string[] = [];
  for (const d of dims) for (const l of f.labels[d] ?? []) (l.p ? prim : rest).push(chip(tax, d, l.c, l.p));
  const chips = [...prim, ...rest].slice(0, opts.maxChips ?? 3);
  const summary = opts.summaryHtml ?? esc(lang === 'zh' && f.summary_zh ? f.summary_zh : f.summary);
  return `<article class="row" data-id="${esc(f.id)}">
    ${avatar(f)}
    <div class="who">
      <div class="name"><button type="button" class="open-person" data-id="${esc(f.id)}">${esc(f.name)}</button></div>
      <div class="meta">${p ? `<a href="${withBase('programs/' + p.slug + '/')}">${esc(p.name)}</a> · ` : ''}${esc(f.dept)} · ${esc(f.rank)}</div>
      ${summary ? `<p class="sum">${summary}</p>` : ''}
      ${chips.length ? `<div class="chips">${chips.join('')}</div>` : ''}
      ${opts.why ? `<div class="why">${opts.why}</div>` : ''}
    </div>
    <div class="side">
      ${opts.score != null ? scoreHtml(opts.score) : ''}
      <div class="actions">${saveBtn(f.id)}<a class="btn sm" href="${withBase('faculty/' + f.id + '/')}">${t('details')}</a></div>
    </div>
  </article>`;
}
export function drawerHtml(f: Faculty, p: Program | undefined, tax: Taxonomy) {
  const lang = getLang();
  const groups = DIMS.map((d) => {
    const items = f.labels[d] ?? [];
    if (!items.length) return '';
    return `<div class="section"><h3>${esc(lang === 'zh' ? tax.dimensions[d].label_zh : tax.dimensions[d].label)}</h3><div class="chips">${items.map((l) => chip(tax, d, l.c, l.p)).join('')}</div></div>`;
  }).join('');
  const links = [
    f.profile ? `<a class="btn sm" href="${esc(f.profile)}" target="_blank" rel="noreferrer">${t('profile')}</a>` : '',
    f.site ? `<a class="btn sm" href="${esc(f.site)}" target="_blank" rel="noreferrer">${t('personal_site')}</a>` : '',
    f.scholar ? `<a class="btn sm" href="${esc(f.scholar)}" target="_blank" rel="noreferrer">${t('scholar')}</a>` : '',
  ].join('');
  return `<button type="button" class="icon-btn close" aria-label="${t('close')}" data-close><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg></button>
  <div class="identity">${avatar(f, true)}<div><div class="small muted">${esc(f.title)}</div><h2>${esc(f.name)}</h2><div class="muted" style="margin-top:4px">${p ? `<a href="${withBase('programs/' + p.slug + '/')}">${esc(p.name)}</a> · ` : ''}${esc(f.dept)}</div></div></div>
  ${f.summary ? `<p class="sum" style="margin-top:16px;color:var(--ink-2)">${esc(lang === 'zh' && f.summary_zh ? f.summary_zh : f.summary)}</p>` : ''}
  ${f.areas.length ? `<div class="section"><h3>${t('research_areas')}</h3><div class="chips">${f.areas.map((a) => `<span class="chip">${esc(a)}</span>`).join('')}</div></div>` : ''}
  ${groups}
  <p class="small muted" style="margin-top:14px">${t('labels_note')}</p>
  <div class="section"><div class="links">${saveBtn(f.id)}${links}<a class="btn sm" href="${withBase('faculty/' + f.id + '/')}">${t('open_page')}</a></div></div>
  <div class="section small muted">${t('sources')}: ${esc(f.src.join(', '))}${f.scraped ? ` · ${t('scraped')} ${esc(f.scraped)}` : ''} · ${t('confidence')}: ${esc(f.conf)}</div>`;
}
export function setupDrawer(getPerson: (id: string) => { f: Faculty; p?: Program } | undefined, tax: Taxonomy) {
  let backdrop = document.querySelector<HTMLElement>('.drawer-backdrop');
  let drawer = document.querySelector<HTMLElement>('.drawer');
  if (!backdrop) { backdrop = document.createElement('div'); backdrop.className = 'drawer-backdrop'; document.body.appendChild(backdrop); }
  if (!drawer) { drawer = document.createElement('aside'); drawer.className = 'drawer'; drawer.setAttribute('role', 'dialog'); drawer.setAttribute('aria-modal', 'true'); document.body.appendChild(drawer); }
  let lastFocus: HTMLElement | null = null;
  const isOpen = () => drawer!.dataset.open === 'true';
  const close = () => {
    if (!isOpen()) return;
    drawer!.dataset.open = 'false'; backdrop!.dataset.open = 'false'; document.body.style.overflow = '';
    lastFocus?.focus?.();
  };
  const open = (id: string) => {
    const x = getPerson(id); if (!x) return;
    lastFocus = document.activeElement as HTMLElement;
    drawer!.setAttribute('aria-label', x.f.name);
    drawer!.innerHTML = drawerHtml(x.f, x.p, tax);
    drawer!.dataset.open = 'true'; backdrop!.dataset.open = 'true'; document.body.style.overflow = 'hidden';
    bindSaveButtons(drawer!);
    drawer!.querySelector<HTMLElement>('[data-close]')?.focus();
  };
  backdrop.addEventListener('click', close);
  drawer.addEventListener('click', (e) => { if ((e.target as HTMLElement).closest('[data-close]')) close(); });
  document.addEventListener('keydown', (e) => {
    if (!isOpen()) return;
    if (e.key === 'Escape') { close(); return; }
    if (e.key === 'Tab') {
      const f = Array.from(drawer!.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), textarea, input, select')).filter((el) => el.offsetParent !== null);
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
  document.addEventListener('click', (e) => { const b = (e.target as HTMLElement).closest<HTMLElement>('.open-person'); if (b) open(b.dataset.id!); });
  return { open, close };
}
export function mark(text: string, terms: string[]) {
  let out = esc(text);
  const ts = terms.filter((x) => x.length > 2).sort((a, b) => b.length - a.length).slice(0, 12);
  for (const term of ts) {
    const re = new RegExp(`(^|[^\\p{L}\\p{N}])(${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\p{L}*)`, 'giu');
    out = out.replace(re, '$1<mark>$2</mark>');
  }
  return out;
}
