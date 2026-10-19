import { createRootRoute, createRoute, createRouter, Navigate, Outlet } from '@tanstack/react-router';
import { lazy, Suspense, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { SkeletonRows } from '@/design/primitives';
import { api } from '@/lib/api/client';
import { Shell } from './Shell';
import { useSession } from './session';
import { HomePage } from '@/features/home/HomePage';
import { LoginPage } from '@/features/auth/LoginPage';
import { SetupPage } from '@/features/auth/SetupPage';
import { PasswordPage } from '@/features/auth/PasswordPage';
import { LibraryPage } from '@/features/library/LibraryPage';
import { KnowledgePage } from '@/features/page/KnowledgePage';
import { MentorPage } from '@/features/mentor/MentorPage';
import { ContributePage } from '@/features/contribute/ContributePage';
import { RecordsPage } from '@/features/records/RecordsPage';
import { RecordDetailPage } from '@/features/records/RecordDetailPage';
import { TasksPage } from '@/features/tasks/TasksPage';
import { TaskDetailPage } from '@/features/tasks/TaskDetailPage';
import { HealthPage } from '@/features/health/HealthPage';
import { SettingsPage } from '@/features/settings/SettingsPage';
import { NotFound } from '@/features/home/NotFound';
import { BASE_PATH } from '@/lib/api/base';

const MapPage = lazy(() => import('@/features/map/MapPage'));
const LabPage = lazy(() => import('@/features/lab/LabPage'));
const Vitrin = lazy(() => import('@/features/vitrin/Vitrin'));

const str = (v: unknown): string | undefined => (typeof v === 'string' && v.length ? v : undefined);
/** Arama parametresi: TanStack Router "1" gibi değerleri sayıya çevirir; metne geri al. */
const strNum = (v: unknown): string | undefined => (typeof v === 'number' && Number.isFinite(v) ? String(v) : str(v));
const strList = (v: unknown): string[] | undefined => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : typeof v === 'string' && v ? [v] : undefined);

function Lazy({ children }: { children: ReactNode }) {
  return <Suspense fallback={<SkeletonRows rows={6} />}>{children}</Suspense>;
}

function AuthGate() {
  const session = useSession();
  const setup = useQuery({ queryKey: ['setup-status'], queryFn: () => api.get<{ needs_setup: boolean }>('/setup/status'), enabled: !session.loading && !session.me, staleTime: 30_000 });
  if (session.loading || (!session.me && setup.isLoading)) return <div style={{ padding: 32 }}><SkeletonRows rows={4} /></div>;
  if (!session.me) return <Navigate to={setup.data?.needs_setup ? '/kurulum' : '/giris'} />;
  if (session.me.user.must_change_password) return <Navigate to="/parola" />;
  return <Shell />;
}

const rootRoute = createRootRoute({ component: () => <Outlet />, notFoundComponent: NotFound });

const loginRoute = createRoute({ getParentRoute: () => rootRoute, path: '/giris', component: LoginPage });
const setupRoute = createRoute({ getParentRoute: () => rootRoute, path: '/kurulum', component: SetupPage });
const passwordRoute = createRoute({ getParentRoute: () => rootRoute, path: '/parola', component: PasswordPage });
const vitrinRoute = createRoute({ getParentRoute: () => rootRoute, path: '/_vitrin', component: () => <Lazy><Vitrin /></Lazy> });

const appRoute = createRoute({ getParentRoute: () => rootRoute, id: 'app', component: AuthGate });

const homeRoute = createRoute({ getParentRoute: () => appRoute, path: '/', component: HomePage });

export interface LibrarySearch {
  domain?: string;
  yatt?: string[];
  kart?: string[];
  proje?: string[];
  kind?: string;
  freshness?: string;
  q?: string;
}
const libraryRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/bilgi',
  validateSearch: (s: Record<string, unknown>): LibrarySearch => ({
    domain: str(s.domain),
    yatt: strList(s.yatt),
    kart: strList(s.kart),
    proje: strList(s.proje),
    kind: str(s.kind),
    freshness: str(s.freshness),
    q: str(s.q),
  }),
  component: LibraryPage,
});
const pageRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/bilgi/$pageId',
  validateSearch: (s: Record<string, unknown>): { rev?: string } => ({ rev: str(s.rev) }),
  component: KnowledgePage,
});
export interface MentorSearch {
  q?: string;
  answer?: string;
  /** Model kimliği; yoksa "Otomatik" (deterministik yönlendirme). */
  model?: string;
  level?: string;
  /** Aynı soruyu yeniden sormak için tek kullanımlık işaret. */
  n?: string;
}
const mentorRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/mentor',
  validateSearch: (s: Record<string, unknown>): MentorSearch => ({ q: strNum(s.q), answer: str(s.answer), model: str(s.model), level: str(s.level), n: strNum(s.n) }),
  component: MentorPage,
});
export interface MapSearch {
  focus?: string;
  view?: string;
  /** "1": tüm düğümler (odak yok). */
  all?: string;
  depth?: string;
  predicate?: string;
}
const mapRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/harita',
  validateSearch: (s: Record<string, unknown>): MapSearch => ({
    focus: str(s.focus),
    view: str(s.view),
    all: strNum(s.all),
    depth: strNum(s.depth),
    predicate: str(s.predicate),
  }),
  component: () => <Lazy><MapPage /></Lazy>,
});
export interface ContributeSearch {
  page?: string;
  change?: string;
}
const contributeRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/katki',
  validateSearch: (s: Record<string, unknown>): ContributeSearch => ({ page: str(s.page), change: str(s.change) }),
  component: ContributePage,
});
const recordsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/kayitlar',
  validateSearch: (s: Record<string, unknown>): { tab?: string; origin?: string } => ({ tab: str(s.tab), origin: str(s.origin) }),
  component: RecordsPage,
});
const recordRoute = createRoute({ getParentRoute: () => appRoute, path: '/kayitlar/$changeId', component: RecordDetailPage });
const tasksRoute = createRoute({ getParentRoute: () => appRoute, path: '/gorevler', component: TasksPage });
const taskRoute = createRoute({ getParentRoute: () => appRoute, path: '/gorevler/$jobId', component: TaskDetailPage });
const healthRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/saglik',
  validateSearch: (s: Record<string, unknown>): { tab?: string; group?: string; kind?: string; finding?: string } => ({
    tab: str(s.tab),
    group: str(s.group),
    kind: str(s.kind),
    finding: str(s.finding),
  }),
  component: HealthPage,
});
const labRoute = createRoute({ getParentRoute: () => appRoute, path: '/lab', component: () => <Lazy><LabPage /></Lazy> });
const settingsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/ayarlar',
  validateSearch: (s: Record<string, unknown>): { tab?: string } => ({ tab: str(s.tab) }),
  component: SettingsPage,
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  setupRoute,
  passwordRoute,
  vitrinRoute,
  appRoute.addChildren([
    homeRoute,
    libraryRoute,
    pageRoute,
    mentorRoute,
    mapRoute,
    contributeRoute,
    recordsRoute,
    recordRoute,
    tasksRoute,
    taskRoute,
    healthRoute,
    labRoute,
    settingsRoute,
  ]),
]);

export const router = createRouter({ routeTree, basepath: BASE_PATH || '/', defaultPreload: 'intent', scrollRestoration: true });

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
