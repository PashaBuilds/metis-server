import { getRouteApi, useNavigate } from '@tanstack/react-router';
import type { ReactNode } from 'react';
import { TabPanel, Tabs } from '@/design/primitives';
import { PageHeader } from '@/app/Shell';
import { useSession } from '@/app/session';
import { tr } from '@/i18n/tr';
import { AppearanceTab } from './AppearanceTab';
import { DirectoryTab } from './DirectoryTab';
import { ExternalTab } from './ExternalTab';
import { KeysTab } from './KeysTab';
import { MembersTab } from './MembersTab';
import { ExportTab, ScheduleTab, SystemTab } from './OpsTabs';
import { PolicyTab } from './PolicyTab';
import { ScopesTab } from './ScopesTab';
import s from './Settings.module.css';

const route = getRouteApi('/app/ayarlar');

/** Sekmeler `?tab=` ile anahtarlanır; yeni sekme eklemek için bu listeye bir öğe eklemek yeterli. */
interface SettingsTab {
  key: string;
  label: string;
  render: () => ReactNode;
  /** Sekme yalnız düzenleyebilecek ya da görebilecek kişiye gösterilir. */
  visible?: (s: { isAdmin: boolean; roles: Set<string> }) => boolean;
}

const admin = ({ isAdmin }: { isAdmin: boolean }) => isAdmin;

const TABS: SettingsTab[] = [
  { key: 'uyeler', label: tr.settings.tabs.uyeler!, render: () => <MembersTab />, visible: (s) => s.isAdmin || s.roles.has('steward') },
  { key: 'politika', label: tr.settings.tabs.politika!, render: () => <PolicyTab />, visible: admin },
  { key: 'giris', label: tr.settings.tabs.giris!, render: () => <DirectoryTab />, visible: admin },
  { key: 'dis-kaynaklar', label: tr.settings.tabs['dis-kaynaklar']!, render: () => <ExternalTab />, visible: admin },
  { key: 'kapsam', label: tr.settings.tabs.kapsam!, render: () => <ScopesTab />, visible: (s) => s.roles.has('contributor') || s.roles.has('steward') },
  { key: 'bakim', label: tr.settings.tabs.bakim!, render: () => <ScheduleTab />, visible: (s) => s.roles.has('steward') },
  { key: 'sistem', label: tr.settings.tabs.sistem!, render: () => <SystemTab />, visible: admin },
  { key: 'anahtarim', label: tr.settings.tabs.anahtarim!, render: () => <KeysTab /> },
  { key: 'disa-aktar', label: tr.settings.tabs['disa-aktar']!, render: () => <ExportTab /> },
  { key: 'gorunum', label: tr.settings.tabs.gorunum!, render: () => <AppearanceTab /> },
];

export function SettingsPage() {
  const { tab } = route.useSearch();
  const navigate = useNavigate({ from: '/ayarlar' });
  const { isAdmin, roles } = useSession();
  const tabs = TABS.filter((t) => !t.visible || t.visible({ isAdmin, roles }));
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
