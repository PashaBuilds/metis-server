import * as RD from '@radix-ui/react-dialog';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { BookOpen, CornerDownLeft, FileText, MessagesSquare, Moon, Plus, Search, SlidersHorizontal } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Kbd } from '@/design/primitives';
import { pageKindLabel, tr } from '@/i18n/tr';
import { api } from '@/lib/api/client';
import { useDebounced } from '@/lib/hooks';
import { useSession } from './session';
import { useTheme } from './theme';
import s from './CommandPalette.module.css';

interface SearchHit {
  page_id: string;
  title: string;
  kind: string;
  snippet: string;
}

interface Item {
  id: string;
  group: string;
  label: ReactNode;
  hint?: string;
  icon: ReactNode;
  run: () => void;
}

export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === '/' && !isTyping(e.target)) {
        const field = document.querySelector<HTMLInputElement>('[data-search-field]');
        e.preventDefault();
        if (field) field.focus();
        else setOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  return { open, setOpen };
}

function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable || el.tagName === 'SELECT');
}

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [q, setQ] = useState('');
  const [cursor, setCursor] = useState(0);
  const navigate = useNavigate();
  const session = useSession();
  const theme = useTheme();
  const listRef = useRef<HTMLUListElement>(null);
  const debounced = useDebounced(q.trim(), 180);

  const search = useQuery({
    queryKey: ['palette-search', session.projectId, debounced],
    queryFn: () => api.get<{ hits: SearchHit[] }>(`/projects/${session.projectId}/search`, { q: debounced, limit: 6 }),
    enabled: open && !!session.projectId && debounced.length >= 2,
    staleTime: 30_000,
  });

  const close = () => {
    onOpenChange(false);
    setQ('');
    setCursor(0);
  };

  const items = useMemo<Item[]>(() => {
    const out: Item[] = [];
    for (const hit of search.data?.hits ?? []) {
      out.push({
        id: 'p' + hit.page_id,
        group: tr.palette.groupPages,
        label: hit.title,
        hint: pageKindLabel(hit.kind),
        icon: <FileText size={16} aria-hidden />,
        run: () => navigate({ to: '/bilgi/$pageId', params: { pageId: hit.page_id } }),
      });
    }
    if (q.trim().length >= 2) {
      out.push({
        id: 'ask',
        group: tr.palette.groupActions,
        label: tr.palette.askMentor(q.trim()),
        icon: <MessagesSquare size={16} aria-hidden />,
        run: () => navigate({ to: '/mentor', search: { q: q.trim() } }),
      });
    }
    const nav: [string, string, ReactNode][] = [
      ['/bilgi', tr.nav.library, <BookOpen size={16} aria-hidden key="b" />],
      ['/mentor', tr.nav.mentor, <MessagesSquare size={16} aria-hidden key="m" />],
      ['/kayitlar', tr.nav.records, <FileText size={16} aria-hidden key="k" />],
      ['/gorevler', tr.nav.tasks, <FileText size={16} aria-hidden key="g" />],
      ['/saglik', tr.nav.health, <FileText size={16} aria-hidden key="s" />],
      ['/harita', tr.nav.map, <FileText size={16} aria-hidden key="h" />],
      ['/ayarlar', tr.nav.settings, <FileText size={16} aria-hidden key="a" />],
    ];
    const needle = q.trim().toLocaleLowerCase('tr-TR');
    for (const [to, label, icon] of nav) {
      if (needle && !label.toLocaleLowerCase('tr-TR').includes(needle)) continue;
      out.push({ id: 'n' + to, group: tr.palette.groupNav, label, icon, run: () => navigate({ to }) });
    }
    const actions: Item[] = [];
    if (session.roles.has('contributor'))
      actions.push({ id: 'new', group: tr.palette.groupActions, label: tr.nav.newContribution, icon: <Plus size={16} aria-hidden />, run: () => navigate({ to: '/katki' }) });
    actions.push({
      id: 'scope',
      group: tr.palette.groupActions,
      label: tr.palette.changeScope,
      icon: <SlidersHorizontal size={16} aria-hidden />,
      run: () => window.dispatchEvent(new CustomEvent('metis:open-scope')),
    });
    actions.push({ id: 'theme', group: tr.palette.groupActions, label: tr.palette.toggleTheme, icon: <Moon size={16} aria-hidden />, run: () => theme.cycle() });
    for (const a of actions) if (!needle || String(a.label).toLocaleLowerCase('tr-TR').includes(needle)) out.push(a);
    return out;
  }, [search.data, q, navigate, session.roles, theme]);

  useEffect(() => setCursor(0), [debounced]);
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-index="${cursor}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [cursor]);

  const groups = items.reduce<Record<string, { item: Item; index: number }[]>>((acc, item, index) => {
    (acc[item.group] ??= []).push({ item, index });
    return acc;
  }, {});

  return (
    <RD.Root open={open} onOpenChange={(o) => (o ? onOpenChange(true) : close())}>
      <RD.Portal>
        <RD.Overlay className={s.overlay} />
        <RD.Content className={s.palette} aria-label={tr.palette.label}>
          <RD.Title className="sr-only">{tr.palette.label}</RD.Title>
          <RD.Description className="sr-only">{tr.palette.placeholder}</RD.Description>
          <div className={s.inputRow}>
            <Search size={18} aria-hidden className={s.searchIcon} />
            <input
              autoFocus
              className={s.input}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={tr.palette.placeholder}
              role="combobox"
              aria-expanded="true"
              aria-controls="palette-list"
              aria-activedescendant={items[cursor] ? `pal-${items[cursor]!.id}` : undefined}
              onKeyDown={(e) => {
                if (e.key === 'ArrowDown') {
                  e.preventDefault();
                  setCursor((c) => Math.min(items.length - 1, c + 1));
                } else if (e.key === 'ArrowUp') {
                  e.preventDefault();
                  setCursor((c) => Math.max(0, c - 1));
                } else if (e.key === 'Enter') {
                  e.preventDefault();
                  const item = items[cursor];
                  if (item) {
                    close();
                    item.run();
                  }
                }
              }}
            />
            <Kbd>Esc</Kbd>
          </div>
          <ul id="palette-list" ref={listRef} className={s.list} role="listbox" aria-label={tr.palette.label}>
            {items.length === 0 && <li className={s.empty}>{tr.palette.empty}</li>}
            {Object.entries(groups).map(([group, entries]) => (
              <li key={group} role="presentation">
                <div className={s.group} aria-hidden>
                  {group}
                </div>
                <ul role="group" aria-label={group} className={s.groupList}>
                  {entries.map(({ item, index }) => (
                    <li
                      key={item.id}
                      id={`pal-${item.id}`}
                      role="option"
                      aria-selected={index === cursor}
                      data-index={index}
                      className={s.item}
                      onMouseMove={() => setCursor(index)}
                      onClick={() => {
                        close();
                        item.run();
                      }}
                    >
                      <span className={s.itemIcon}>{item.icon}</span>
                      <span className={s.itemLabel}>{item.label}</span>
                      {item.hint && <span className={s.itemHint}>{item.hint}</span>}
                      {index === cursor && <CornerDownLeft size={14} aria-hidden className={s.enter} />}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </RD.Content>
      </RD.Portal>
    </RD.Root>
  );
}
