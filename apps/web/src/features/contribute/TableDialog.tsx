import { Plus, X } from 'lucide-react';
import { useEffect, useState, type ClipboardEvent } from 'react';
import { Button, Dialog, IconButton } from '@/design/primitives';
import { tr } from '@/i18n/tr';
import { normalize, parseTsv, type Grid } from '@/features/shared/table';
import s from './Contribute.module.css';

const EMPTY: Grid = [
  ['', '', ''],
  ['', '', ''],
  ['', '', ''],
];

interface Props {
  open: boolean;
  /** Düzenlenen tablo; yeni tabloda null. */
  initial: Grid | null;
  onOpenChange: (open: boolean) => void;
  /** Düzenlenen tablonun tüm hücreleri boşaltılınca null: tablo nottan kalkar. */
  onSave: (grid: Grid | null) => void;
}

/** Notta tablo: hücre kutuları; ilk satır başlık. Excel'den kopyalanan hücreler bir kutuya yapıştırılınca oradan yayılır. */
export function TableDialog({ open, initial, onOpenChange, onSave }: Props) {
  const [grid, setGrid] = useState<Grid>(EMPTY);
  useEffect(() => {
    if (open) setGrid(initial ? normalize(initial) : EMPTY);
  }, [open, initial]);
  const cols = grid[0]?.length ?? 0;

  const set = (r: number, c: number, value: string) => setGrid((g) => g.map((row, i) => (i === r ? row.map((x, k) => (k === c ? value : x)) : row)));
  const addRow = () => setGrid((g) => [...g, Array<string>(cols).fill('')]);
  const addCol = () => setGrid((g) => g.map((row) => [...row, '']));
  const removeRow = (r: number) => setGrid((g) => (g.length > 1 ? g.filter((_, i) => i !== r) : g));
  const removeCol = (c: number) => setGrid((g) => (cols > 1 ? g.map((row) => row.filter((_, k) => k !== c)) : g));

  const onPaste = (r: number, c: number) => (e: ClipboardEvent<HTMLInputElement>) => {
    const pasted = parseTsv(e.clipboardData.getData('text/plain'));
    if (!pasted || (pasted.length < 2 && (pasted[0]?.length ?? 0) < 2)) return;
    e.preventDefault();
    setGrid((g) => {
      const height = Math.max(g.length, r + pasted.length);
      const width = Math.max(cols, c + (pasted[0]?.length ?? 0));
      const out = normalize([...g, ...Array.from({ length: height - g.length }, () => [] as string[])].map((row) => [...row, ...Array<string>(Math.max(0, width - row.length)).fill('')]));
      pasted.forEach((prow, i) => prow.forEach((v, k) => (out[r + i]![c + k] = v)));
      return out;
    });
  };

  const hasContent = grid.some((row) => row.some((x) => x.trim()));
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={initial ? tr.table.editTitle : tr.table.newTitle}
      description={tr.table.lead}
      width={960}
      footer={
        <>
          <Button onClick={() => onOpenChange(false)}>{tr.table.cancel}</Button>
          <Button variant="primary" disabled={!hasContent && !initial} onClick={() => onSave(hasContent ? grid : null)}>
            {!initial ? tr.table.insert : hasContent ? tr.table.update : tr.table.remove}
          </Button>
        </>
      }
    >
      <div className={s.tableScroll}>
        <table className={s.tableGrid}>
          <thead>
            <tr>
              {grid[0]!.map((_, c) => (
                <th key={c} scope="col" className={s.tableColHead}>
                  <IconButton size="sm" label={tr.table.removeCol(c + 1)} disabled={cols <= 1} onClick={() => removeCol(c)}>
                    <X size={14} aria-hidden />
                  </IconButton>
                </th>
              ))}
              <th aria-hidden />
            </tr>
          </thead>
          <tbody>
            {grid.map((row, r) => (
              <tr key={r} className={r === 0 ? s.tableHeadRow : undefined}>
                {row.map((value, c) => (
                  <td key={c}>
                    <input
                      className={s.tableCell}
                      value={value}
                      aria-label={r === 0 ? tr.table.headerCell(c + 1) : tr.table.cell(r, c + 1)}
                      onChange={(e) => set(r, c, e.target.value)}
                      onPaste={onPaste(r, c)}
                    />
                  </td>
                ))}
                <td>
                  <IconButton size="sm" label={r === 0 ? tr.table.removeHeader : tr.table.removeRow(r)} disabled={grid.length <= 1} onClick={() => removeRow(r)}>
                    <X size={14} aria-hidden />
                  </IconButton>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={s.tableActions}>
        <Button size="sm" icon={<Plus size={15} aria-hidden />} onClick={addRow}>
          {tr.table.addRow}
        </Button>
        <Button size="sm" icon={<Plus size={15} aria-hidden />} onClick={addCol}>
          {tr.table.addCol}
        </Button>
      </div>
    </Dialog>
  );
}
