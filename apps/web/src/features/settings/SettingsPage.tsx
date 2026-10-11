import { getRouteApi, useNavigate } from '@tanstack/react-router';
import type { ReactNode } from 'react';
import { TabPanel, Tabs } from '@/design/primitives';
import { PageHeader } from '@/app/Shell';
import { useSession } from '@/app/session';
import { tr } from '@/i18n/tr';
import { AppearanceTab } from './AppearanceTab';
import { MembersTab } from './MembersTab';
import { ExportTab, ImportTab, ScheduleTab, SystemTab } from './OpsTabs';
import { PolicyTab } from './PolicyTab';
import { ScopesTab } from './ScopesTab';
import s from './Settings.module.css';

const route = getRouteApi('/app/ayarlar');

/** Sekmeler `?tab=` ile anahtarlanır; yeni sekme eklemek için bu listeye bir öğe eklemek yeterli. */
interface SettingsTab {
  key: string;
  label: string;
  render: () => ReactNode;
  adminOnly?: boolean;
}

const TABS: SettingsTab[] = [
  { key: 'uyeler', label: tr.settings.tabs.uyeler!, render: () => <MembersTab /> },
  { key: 'politika', label: tr.settings.tabs.politika!, render: () => <PolicyTab /> },
  { key: 'kapsam', label: tr.settings.tabs.kapsam!, render: () => <ScopesTab /> },
  { key: 'bakim', label: tr.settings.tabs.bakim!, render: () => <ScheduleTab /> },
  { key: 'sistem', label: tr.settings.tabs.sistem!, render: () => <SystemTab />, adminOnly: true },
  { key: 'disa-aktar', label: tr.settings.tabs['disa-aktar']!, render: () => <ExportTab /> },
  { key: 'aktarim', label: tr.settings.tabs.aktarim!, render: () => <ImportTab />, adminOnly: true },
  { key: 'gorunum', label: tr.settings.tabs.gorunum!, render: () => <AppearanceTab /> },
];

export function SettingsPage() {
  const { tab } = route.useSearch();
  const navigate = useNavigate({ from: '/ayarlar' });
  const { isAdmin } = useSession();
  const tabs = TABS.filter((t) => !t.adminOnly || isAdmin);
  const current = tabs.find((t) => t.key === tab) ?? tabs[0]!;
  return (
    <div className={s.page}>
      <PageHeader title={tr.settings.title} />
      <Tabs label={tr.settings.title} value={current.key} onValueChange={(v) => navigate({ search: { tab: v }, replace: true })} tabs={tabs.map((t) => ({ value: t.key, label: t.label }))}>
        {tabs.map((t) => (
          <TabPanel key={t.key} value={t.key}>
            {t.key === current.key && t.render()}
          </TabPanel>
        ))}
      </Tabs>
    </div>
  );
}
