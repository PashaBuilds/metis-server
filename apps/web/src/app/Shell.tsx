import * as DM from '@radix-ui/react-dropdown-menu';
import { useQuery } from '@tanstack/react-query';
import { Link, Outlet, useNavigate, useRouterState } from '@tanstack/react-router';
import {
  Activity,
  BookOpen,
  Check,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  ClipboardList,
  FlaskConical,
  Home,
  LogOut,
  Menu,
  MessagesSquare,
  Network,
  Plus,
  Search,
  Settings,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Button, Drawer, IconButton, Kbd, Tooltip } from '@/design/primitives';
import { IzPanel, IzTrace, Logo, useIz } from '@/design/iz';
import { tr } from '@/i18n/tr';
import { api } from '@/lib/api/client';
import { useMediaQuery } from '@/lib/hooks';
import { useQueryClient } from '@tanstack/react-query';
import { CommandPalette, useCommandPalette } from './CommandPalette';
import { ScopeDialog } from './ScopeBar';
import { useSession } from './session';
import s from './Shell.module.css';

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  badge?: number;
  adminOnly?: boolean;
}

interface InboxCounts {
  reviews_waiting: number;
  questions_waiting: number;
  open_findings: number;
}

function useInbox(projectId: string | null) {
  return useQuery({
    queryKey: ['inbox', projectId],
    queryFn: () => api.get<InboxCounts>(`/projects/${projectId}/inbox`),
    enabled: !!projectId,
    refetchInterval: 30_000,
  });
}

export function Shell() {
  const session = useSession();
  const iz = useIz();
  const wide = useMediaQuery('(min-width: 1280px)');
  const mobile = useMediaQuery('(max-width: 759px)');
  const collapsed = session.pref<boolean>('rail_collapsed', false) && !mobile;
  const [drawer, setDrawer] = useState(false);
  const palette = useCommandPalette();
  const inbox = useInbox(session.projectId);
  const version = useAppVersion();

  const groups: NavItem[][] = [
    [
      { to: '/', label: tr.nav.home, icon: Home },
      { to: '/bilgi', label: tr.nav.library, icon: BookOpen },
      { to: '/mentor', label: tr.nav.mentor, icon: MessagesSquare },
      { to: '/harita', label: tr.nav.map, icon: Network },
    ],
    [
      { to: '/kayitlar', label: tr.nav.records, icon: ClipboardList, badge: inbox.data?.reviews_waiting },
      { to: '/gorevler', label: tr.nav.tasks, icon: Sparkles, badge: inbox.data?.questions_waiting },
      { to: '/saglik', label: tr.nav.health, icon: Activity },
    ],
    session.isAdmin ? [{ to: '/lab', label: tr.nav.lab, icon: FlaskConical, adminOnly: true }] : [],
  ];

  const rail = (inDrawer: boolean) => (
    <nav className={s.railNav} aria-label={tr.nav.mainNav}>
      {groups
        .filter((g) => g.length)
        .map((g, i) => (
          <ul key={i} className={s.navGroup}>
            {g.map((item) => (
              <li key={item.to}>
                <RailLink item={item} collapsed={collapsed && !inDrawer} onNavigate={() => setDrawer(false)} />
              </li>
            ))}
          </ul>
        ))}
    </nav>
  );

  return (
    <div className={[s.shell, collapsed ? s.collapsed : '', iz.active && wide ? s.withPanel : ''].join(' ')}>
      <a href="#main" className={s.skip}>
        {tr.nav.skip}
      </a>
      {!mobile && (
        <aside className={s.rail}>
          <div className={s.railHead}>
            <Link to="/" className={s.brand} aria-label="METIS ana sayfa">
              <Logo tone="rail" size={28} />
              {!collapsed && (
                <span className={s.brandText}>
                  <span className={s.wordmark}>METIS</span>
                  {version && <span className={s.version}>{tr.nav.version(version)}</span>}
                </span>
              )}
            </Link>
          </div>
          {rail(false)}
          <div className={s.railFoot}>
            <RailLink item={{ to: '/ayarlar', label: tr.nav.settings, icon: Settings }} collapsed={collapsed} />
            <AccountMenu collapsed={collapsed} />
            <button
              type="button"
              className={s.collapseBtn}
              onClick={() => session.setPref('rail_collapsed', !collapsed)}
              aria-label={collapsed ? tr.nav.expand : tr.nav.collapse}
              title={collapsed ? tr.nav.expand : tr.nav.collapse}
            >
              {collapsed ? <ChevronsRight size={18} aria-hidden /> : <ChevronsLeft size={18} aria-hidden />}
            </button>
          </div>
        </aside>
      )}
      <div className={s.main}>
        <header className={s.topbar}>
          {mobile && (
            <IconButton label={tr.nav.menu} onClick={() => setDrawer(true)}>
              <Menu size={20} aria-hidden />
            </IconButton>
          )}
          <ProjectPicker />
          <div className={s.topActions}>
            <button type="button" className={s.searchBtn} onClick={() => palette.setOpen(true)} aria-label={`${tr.nav.search} (Ctrl+K)`}>
              <Search size={16} aria-hidden />
              {!mobile && <span>{tr.nav.search}</span>}
              {!mobile && <Kbd>Ctrl K</Kbd>}
            </button>
            {session.roles.has('contributor') && (
              <Link to="/katki" className={s.newBtn}>
                <Plus size={16} aria-hidden />
                {!mobile && <span>{tr.nav.newContribution}</span>}
                {mobile && <span className="sr-only">{tr.nav.newContribution}</span>}
              </Link>
            )}
          </div>
        </header>
        {session.project?.is_demo && (
          <div className={s.demoBanner} role="note">
            {tr.common.demoNote}
          </div>
        )}
        <main id="main" className={s.content} tabIndex={-1}>
          <Outlet />
        </main>
        {mobile && <MobileTabs />}
      </div>
      {iz.active && <IzPanel mode={wide ? 'docked' : 'overlay'} />}
      <IzTrace />
      <CommandPalette open={palette.open} onOpenChange={palette.setOpen} />
      <ScopeDialog />
      {mobile && (
        <Drawer open={drawer} onOpenChange={setDrawer} title="METIS" side="left" width={300}>
          <div className={s.drawerNav}>
            {rail(true)}
            <ul className={s.navGroup}>
              <li>
                <RailLink item={{ to: '/ayarlar', label: tr.nav.settings, icon: Settings }} collapsed={false} onNavigate={() => setDrawer(false)} />
              </li>
            </ul>
            <AccountMenu collapsed={false} />
          </div>
        </Drawer>
      )}
    </div>
  );
}

function RailLink({ item, collapsed, onNavigate }: { item: NavItem; collapsed: boolean; onNavigate?: () => void }) {
  const path = useRouterState({ select: (st) => st.location.pathname });
  const active = item.to === '/' ? path === '/' : path === item.to || path.startsWith(item.to + '/');
  const Icon = item.icon;
  const link = (
    <Link to={item.to} className={[s.navLink, active ? s.navActive : ''].join(' ')} aria-current={active ? 'page' : undefined} onClick={onNavigate}>
      <span className={s.navDot} aria-hidden />
      <Icon size={18} aria-hidden className={s.navIcon} />
      {collapsed ? <span className="sr-only">{item.label}</span> : <span className={s.navLabel}>{item.label}</span>}
      {!!item.badge && (
        <span className={s.navBadge} aria-label={`${item.badge} bekleyen`}>
          {item.badge}
        </span>
      )}
    </Link>
  );
  return collapsed ? (
    <Tooltip content={item.label} side="right">
      {link}
    </Tooltip>
  ) : (
    link
  );
}

function ProjectPicker() {
  const session = useSession();
  const members = session.me?.memberships ?? [];
  if (!session.project) return null;
  if (members.length <= 1) {
    // Tek proje: seçilecek bir şey yok, yalnız adı göster.
    return (
      <span className={[s.projectBtn, s.projectStatic].join(' ')}>
        <span className={s.projectName}>{session.project.project_name}</span>
        {session.project.is_demo && <span className={s.demoTag}>{tr.common.demoBadge}</span>}
      </span>
    );
  }
  return (
    <DM.Root>
      <DM.Trigger asChild>
        <button type="button" className={s.projectBtn} aria-label={`${tr.nav.project}: ${session.project.project_name}`}>
          <span className={s.projectName}>{session.project.project_name}</span>
          {session.project.is_demo && <span className={s.demoTag}>{tr.common.demoBadge}</span>}
          <ChevronDown size={16} aria-hidden />
        </button>
      </DM.Trigger>
      <DM.Portal>
        <DM.Content className={s.menu} sideOffset={6} align="start">
          <DM.Label className={s.menuLabel}>{tr.nav.project}</DM.Label>
          {members.map((m) => (
            <DM.Item key={m.project_id} className={s.menuItem} onSelect={() => session.setProject(m.project_id)}>
              <span className={s.menuCheck}>{m.project_id === session.projectId && <Check size={15} aria-hidden />}</span>
              <span>{m.project_name}</span>
              {m.is_demo && <span className={s.demoTag}>{tr.common.demoBadge}</span>}
            </DM.Item>
          ))}
        </DM.Content>
      </DM.Portal>
    </DM.Root>
  );
}

/** Çalışan sunucunun sürümü (ör. 2.0.7); açık uçtan bir kez okunur. */
function useAppVersion(): string | undefined {
  const q = useQuery({ queryKey: ['version'], queryFn: () => api.get<{ version: string }>('/health/live'), staleTime: Infinity });
  return q.data?.version;
}

function AccountMenu({ collapsed }: { collapsed: boolean }) {
  const session = useSession();
  const version = useAppVersion();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const name = session.me?.user.display_name ?? '';
  const initials = name
    .split(/\s+/)
    .map((p) => p[0])
    .join('')
    .slice(0, 2)
    .toLocaleUpperCase('tr-TR');
  return (
    <DM.Root>
      <DM.Trigger asChild>
        <button type="button" className={s.account} aria-label={`${tr.nav.account}: ${name}`}>
          <span className={s.avatar} aria-hidden>
            {initials}
          </span>
          {!collapsed && <span className={s.accountName}>{name}</span>}
        </button>
      </DM.Trigger>
      <DM.Portal>
        <DM.Content className={s.menu} side="right" align="end" sideOffset={8}>
          <DM.Label className={s.menuLabel}>{session.me?.user.username}</DM.Label>
          {version && <DM.Label className={s.menuLabel}>{tr.nav.version(version)}</DM.Label>}
          <DM.Item className={s.menuItem} onSelect={() => navigate({ to: '/ayarlar', search: { tab: 'gorunum' } })}>
            <span className={s.menuCheck} />
            {tr.theme.label}
          </DM.Item>
          <DM.Separator className={s.menuSep} />
          <DM.Item
            className={s.menuItem}
            onSelect={async () => {
              await api.post('/auth/logout').catch(() => undefined);
              qc.clear();
              qc.setQueryData(['me'], null);
              navigate({ to: '/giris' });
            }}
          >
            <span className={s.menuCheck}>
              <LogOut size={15} aria-hidden />
            </span>
            {tr.nav.logout}
          </DM.Item>
        </DM.Content>
      </DM.Portal>
    </DM.Root>
  );
}

function MobileTabs() {
  const items: NavItem[] = [
    { to: '/', label: tr.nav.home, icon: Home },
    { to: '/bilgi', label: tr.nav.library, icon: BookOpen },
    { to: '/mentor', label: tr.nav.mentor, icon: MessagesSquare },
    { to: '/kayitlar', label: tr.nav.records, icon: ClipboardList },
  ];
  const path = useRouterState({ select: (st) => st.location.pathname });
  return (
    <nav className={s.tabbar} aria-label="Hızlı gezinme">
      {items.map((item) => {
        const active = item.to === '/' ? path === '/' : path.startsWith(item.to);
        const Icon = item.icon;
        return (
          <Link key={item.to} to={item.to} className={[s.tab, active ? s.tabActive : ''].join(' ')} aria-current={active ? 'page' : undefined}>
            <Icon size={20} aria-hidden />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export function PageHeader({ title, actions, children }: { title: ReactNode; actions?: ReactNode; children?: ReactNode }) {
  return (
    <div className={s.pageHeader}>
      <div className={s.pageHeaderRow}>
        <h1>{title}</h1>
        {actions && <div className={s.pageActions}>{actions}</div>}
      </div>
      {children}
    </div>
  );
}

export { Button };
