const KEY = 'comm-phd-shortlist-v1';
export type Entry = { id: string; added: string; note?: string };
export function load(): Entry[] { try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch { return []; } }
export function save(list: Entry[]) { try { localStorage.setItem(KEY, JSON.stringify(list)); } catch {} document.dispatchEvent(new CustomEvent('shortlistchange')); }
export function has(id: string) { return load().some((e) => e.id === id); }
export function toggle(id: string): boolean {
  const list = load();
  const i = list.findIndex((e) => e.id === id);
  if (i >= 0) { list.splice(i, 1); save(list); return false; }
  list.push({ id, added: new Date().toISOString().slice(0, 10) }); save(list); return true;
}
export function setNote(id: string, note: string) { const list = load(); const e = list.find((x) => x.id === id); if (e) { e.note = note; save(list); } }
export function remove(id: string) { save(load().filter((e) => e.id !== id)); }
export function clear() { save([]); }
export function count() { return load().length; }
