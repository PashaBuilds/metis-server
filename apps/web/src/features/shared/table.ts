/** Notta tablo: GFM boru tablosu (ilk satır başlık). Confluence aktarımıyla aynı biçim; hücre içi `|` → `\|`, satır sonu → boşluk. */

export type Grid = string[][];

const SEPARATOR = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;

export function normalize(rows: Grid): Grid {
  const width = Math.max(1, ...rows.map((r) => r.length));
  return rows.map((r) => [...r, ...Array<string>(width - r.length).fill('')]);
}

function splitRow(line: string): string[] {
  let t = line.trim();
  if (t.startsWith('|')) t = t.slice(1);
  if (t.endsWith('|') && !t.endsWith('\\|')) t = t.slice(0, -1);
  const cells: string[] = [];
  let cur = '';
  for (let i = 0; i < t.length; i++) {
    if (t[i] === '\\' && t[i + 1] === '|') {
      cur += '|';
      i++;
    } else if (t[i] === '|') {
      cells.push(cur.trim());
      cur = '';
    } else cur += t[i];
  }
  cells.push(cur.trim());
  return cells;
}

/** Boru tablosu metni → hücreler; tablo değilse null. */
export function parseTable(md: string): Grid | null {
  const lines = md.split('\n').filter((l) => l.trim());
  if (lines.length < 2 || !lines[0]!.includes('|') || !SEPARATOR.test(lines[1]!)) return null;
  return normalize([lines[0]!, ...lines.slice(2)].map(splitRow));
}

const cell = (t: string) => t.replace(/\r?\n/g, ' ').replace(/\|/g, '\\|').trim();

export function tableMarkdown(rows: Grid): string {
  const g = normalize(rows.length ? rows : [['']]);
  const line = (r: string[]) => `| ${r.map(cell).join(' | ')} |`;
  return [line(g[0]!), `| ${g[0]!.map(() => '---').join(' | ')} |`, ...g.slice(1).map(line)].join('\n');
}

/** Excel / tablolama programından kopyalanan hücreler (sekmeyle ayrılmış, tırnaklı çok satırlı hücre olabilir). */
export function parseTsv(text: string): Grid | null {
  const t = text.replace(/\r\n?/g, '\n').replace(/\n+$/, '');
  if (!t.includes('\t')) return null;
  const rows: Grid = [];
  let row: string[] = [];
  let cur = '';
  let quoted = false;
  for (let i = 0; i < t.length; i++) {
    const ch = t[i]!;
    if (quoted) {
      if (ch === '"' && t[i + 1] === '"') {
        cur += '"';
        i++;
      } else if (ch === '"') quoted = false;
      else cur += ch;
    } else if (ch === '"' && cur === '') quoted = true;
    else if (ch === '\t') {
      row.push(cur);
      cur = '';
    } else if (ch === '\n') {
      row.push(cur);
      rows.push(row);
      row = [];
      cur = '';
    } else cur += ch;
  }
  row.push(cur);
  rows.push(row);
  return normalize(rows.map((r) => r.map((c) => c.trim())));
}

/** İmlecin bulunduğu boru tablosu (ardışık `|` satırları); yoksa null. */
export function tableAt(text: string, pos: number): { start: number; end: number; grid: Grid } | null {
  const lines = text.split('\n');
  const starts: number[] = [];
  let off = 0;
  let idx = -1;
  lines.forEach((l, i) => {
    starts.push(off);
    if (idx < 0 && pos <= off + l.length) idx = i;
    off += l.length + 1;
  });
  const isRow = (i: number) => i >= 0 && i < lines.length && lines[i]!.trimStart().startsWith('|');
  if (idx < 0 || !isRow(idx)) return null;
  let a = idx;
  let b = idx;
  while (isRow(a - 1)) a--;
  while (isRow(b + 1)) b++;
  const start = starts[a]!;
  const end = starts[b]! + lines[b]!.length;
  const grid = parseTable(text.slice(start, end));
  return grid ? { start, end, grid } : null;
}

/** Bloğu çevresindeki metinden boş satırla ayırır (not blokları boş satırla bölünür). */
export function asBlock(before: string, after: string, block: string): string {
  const pre = !before.trim() || /\n[ \t]*\n[ \t]*$/.test(before) ? '' : before.endsWith('\n') ? '\n' : '\n\n';
  // Sonda da boş satır: imleç bloğun altında yeni paragrafa geçer (yazılan metin tabloya eklenmez).
  const post = /^[ \t]*\n[ \t]*\n/.test(after) ? '' : after.startsWith('\n') ? '\n' : '\n\n';
  return pre + block + post;
}
