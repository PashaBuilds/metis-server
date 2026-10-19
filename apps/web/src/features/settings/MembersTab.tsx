import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { KeyRound, ShieldCheck, UserCheck, UserPlus, UserX, Users } from 'lucide-react';
import { useState } from 'react';
import { Button, Checkbox, Chip, ConfirmDialog, Dialog, Field, Input, SkeletonRows, useToast } from '@/design/primitives';
import { useSession } from '@/app/session';
import { errorMessage, tr } from '@/i18n/tr';
import { api, ApiError, type Schemas } from '@/lib/api/client';
import { RowMenu } from '@/features/shared/RowMenu';
import { messageOf } from '@/features/shared/hooks';
import s from './Settings.module.css';

const ROLES = ['reader', 'contributor', 'reviewer', 'steward'] as const;
type Role = (typeof ROLES)[number];

interface Person {
  user_id: string;
  username: string;
  display_name: string;
  active: boolean;
  is_admin: boolean;
  roles: Role[];
  /** Şirket hesabı (dizin): parolası METIS'te değil; ilk girişte kendiliğinden oluşur. */
  directory: boolean;
  /** Hiçbir projede rolü yok (şirket hesabıyla ilk kez girmiş). */
  pending: boolean;
}

export function generatePassword(): string {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789';
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join('');
}

export function MembersTab() {
  const session = useSession();
  const pid = session.projectId;
  const qc = useQueryClient();
  const toast = useToast();
  const canManage = session.isAdmin || session.roles.has('steward');
  const members = useQuery({ queryKey: ['members', pid], queryFn: () => api.get<Schemas['MemberOut'][]>(`/projects/${pid}/members`), enabled: !!pid });
  const users = useQuery({ queryKey: ['users'], queryFn: () => api.get<Schemas['UserOut'][]>('/users'), enabled: session.isAdmin });
  const [addOpen, setAddOpen] = useState(false);
  const [rolesFor, setRolesFor] = useState<Person | null>(null);
  const [resetFor, setResetFor] = useState<Person | null>(null);
  const [toggleFor, setToggleFor] = useState<Person | null>(null);

  const people: Person[] = (() => {
    const byId = new Map<string, Person>();
    for (const m of members.data ?? []) byId.set(m.user_id, { user_id: m.user_id, username: m.username, display_name: m.display_name, active: m.active, is_admin: false, roles: m.roles, directory: false, pending: false });
    for (const u of users.data ?? []) {
      const p = byId.get(u.id);
      const directory = u.auth_source === 'directory';
      if (p) {
        p.is_admin = u.is_admin;
        p.directory = directory;
        p.pending = u.pending_role;
      } else byId.set(u.id, { user_id: u.id, username: u.username, display_name: u.display_name, active: u.active, is_admin: u.is_admin, roles: [], directory, pending: u.pending_role });
    }
    // Şirket hesabıyla ilk kez girip rol bekleyenler en üstte.
    const waiting = (p: Person) => (p.pending ? 0 : 1);
    return [...byId.values()].sort((a, b) => waiting(a) - waiting(b) || a.display_name.localeCompare(b.display_name, 'tr'));
  })();

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['members', pid] });
    qc.invalidateQueries({ queryKey: ['users'] });
  };

  if (members.isLoading) return <SkeletonRows rows={4} />;
  if (members.isError) return <p className={s.error}>{messageOf(members.error)}</p>;

  return (
    <div className={s.stack}>
      <div className={s.blockHead}>
        <p className={s.hint}>{tr.settings.rolesHelp}</p>
        {session.isAdmin && (
          <Button variant="primary" icon={<UserPlus size={16} aria-hidden />} onClick={() => setAddOpen(true)}>
            {tr.settings.addUser}
          </Button>
        )}
      </div>
      <ul className={s.people} aria-label={tr.settings.members}>
        {people.map((p) => {
          const me = p.user_id === session.me?.user.id;
          const initials = p.display_name
            .split(/\s+/)
            .map((x) => x[0])
            .join('')
            .slice(0, 2)
            .toLocaleUpperCase('tr-TR');
          return (
            <li key={p.user_id} className={[s.person, p.active ? '' : s.inactiveRow].join(' ')}>
              <span className={s.avatar} aria-hidden>
                {initials}
              </span>
              <div className={s.personMain}>
                <span className={s.personName}>
                  {p.display_name}
                  {me && <span className={s.you}>{tr.shared.you}</span>}
                </span>
                <span className={s.username}>{p.username}</span>
              </div>
              <div className={s.roleChips}>
                {p.is_admin && (
                  <span className={s.adminBadge}>
                    <ShieldCheck size={13} aria-hidden />
                    {tr.roles.admin}
                  </span>
                )}
                {!p.active && (
                  <span className={s.inactive}>
                    <UserX size={13} aria-hidden />
                    {tr.settings.inactive}
                  </span>
                )}
                {p.directory && <Chip tone="muted">{tr.settings.companyAccount}</Chip>}
                {p.roles.length === 0 ? (
                  <span className={p.pending ? s.pending : s.hint}>{p.pending ? tr.settings.pendingRole : tr.settings.noRole}</span>
                ) : (
                  ROLES.filter((r) => p.roles.includes(r)).map((r) => (
                    <Chip key={r} tone="muted">
                      {tr.roles[r]}
                    </Chip>
                  ))
                )}
              </div>
              {canManage && (
                <RowMenu
                  label={tr.settings.memberActions(p.display_name)}
                  actions={[
                    { label: tr.settings.roles, icon: <Users size={15} />, onSelect: () => setRolesFor(p) },
                    ...(session.isAdmin
                      ? [
                          ...(!p.directory ? [{ label: tr.settings.resetPassword, icon: <KeyRound size={15} />, onSelect: () => setResetFor(p) }] : []),
                          ...(!me
                            ? [
                                p.active
                                  ? { label: tr.settings.deactivate, icon: <UserX size={15} />, danger: true, separatorBefore: true, onSelect: () => setToggleFor(p) }
                                  : { label: tr.settings.activate, icon: <UserCheck size={15} />, separatorBefore: true, onSelect: () => setToggleFor(p) },
                              ]
                            : []),
                        ]
                      : []),
                  ]}
                />
              )}
            </li>
          );
        })}
      </ul>

      <AddUserDialog open={addOpen} onOpenChange={setAddOpen} onDone={refresh} />
      {rolesFor && <RolesDialog person={rolesFor} onClose={() => setRolesFor(null)} onDone={refresh} />}
      {resetFor && <ResetDialog person={resetFor} onClose={() => setResetFor(null)} />}
      <ConfirmDialog
        open={!!toggleFor}
        onOpenChange={(o) => !o && setToggleFor(null)}
        title={toggleFor ? (toggleFor.active ? tr.settings.deactivateTitle(toggleFor.display_name) : tr.settings.activate) : ''}
        description={toggleFor?.active ? tr.settings.deactivateDesc : ''}
        confirmLabel={toggleFor?.active ? tr.settings.deactivate : tr.settings.activate}
        danger={!!toggleFor?.active}
        onConfirm={async () => {
          if (!toggleFor) return;
          try {
            await api.patch(`/users/${toggleFor.user_id}`, { active: !toggleFor.active });
            toast.show(toggleFor.active ? tr.settings.deactivated : tr.settings.activated);
            refresh();
          } catch (e) {
            toast.show(messageOf(e), { tone: 'error' });
          }
        }}
      />
    </div>
  );
}

function RoleChecks({ value, onChange }: { value: Role[]; onChange: (v: Role[]) => void }) {
  return (
    <fieldset className={s.roleSet}>
      <legend className={s.label}>{tr.settings.projectRoles}</legend>
      {ROLES.map((r) => (
        <Checkbox key={r} label={tr.roles[r]} checked={value.includes(r)} onChange={(on) => onChange(on ? [...value, r] : value.filter((x) => x !== r))} />
      ))}
    </fieldset>
  );
}

function PasswordField({ value, onChange, error }: { value: string; onChange: (v: string) => void; error?: string | null }) {
  return (
    <div className={s.pwRow}>
      <Field label={tr.settings.tempPassword} hint={tr.settings.tempPasswordHint} error={error ?? null} className={s.grow}>
        {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} invalid={!!error} className="mono" value={value} onChange={(e) => onChange(e.target.value)} autoComplete="new-password" />}
      </Field>
      <Button onClick={() => onChange(generatePassword())} className={s.pwGen}>
        {tr.settings.generate}
      </Button>
    </div>
  );
}

function AddUserDialog({ open, onOpenChange, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => void }) {
  const session = useSession();
  const toast = useToast();
  const [form, setForm] = useState({ display_name: '', username: '', temporary_password: generatePassword(), is_admin: false });
  const [roles, setRoles] = useState<Role[]>(['reader']);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: async () => {
      const user = await api.post<Schemas['UserOut']>('/users', { ...form, display_name: form.display_name.trim(), username: form.username.trim() });
      if (roles.length) await api.put(`/projects/${session.projectId}/members`, { user_id: user.id, roles });
      return user;
    },
    onSuccess: () => {
      toast.show(tr.settings.userAdded);
      onDone();
      onOpenChange(false);
      setForm({ display_name: '', username: '', temporary_password: generatePassword(), is_admin: false });
      setRoles(['reader']);
    },
    onError: (e) => {
      if (e instanceof ApiError) {
        const fe = e.fieldErrors();
        const mapped: Record<string, string> = {};
        if (fe.username || e.code === 'ALREADY_EXISTS') mapped.username = errorMessage(e.code === 'ALREADY_EXISTS' ? 'ALREADY_EXISTS' : 'VALIDATION_ERROR');
        if (fe.display_name) mapped.display_name = errorMessage('VALIDATION_ERROR');
        if (fe.temporary_password || e.code === 'WEAK_PASSWORD') mapped.temporary_password = errorMessage('WEAK_PASSWORD');
        setErrors(mapped);
        if (!Object.keys(mapped).length) setFormError(errorMessage(e.code));
      } else setFormError(errorMessage('NETWORK'));
    },
  });
  const submit = () => {
    const errs: Record<string, string> = {};
    if (!form.display_name.trim()) errs.display_name = errorMessage('VALIDATION_ERROR');
    if (!form.username.trim()) errs.username = errorMessage('VALIDATION_ERROR');
    if (form.temporary_password.length < 12) errs.temporary_password = errorMessage('WEAK_PASSWORD');
    setErrors(errs);
    setFormError(null);
    if (!Object.keys(errs).length) m.mutate();
  };
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={tr.settings.addUser}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {tr.common.cancel}
          </Button>
          <Button variant="primary" loading={m.isPending} onClick={submit}>
            {tr.settings.addUser}
          </Button>
        </>
      }
    >
      <div className={s.dialogForm}>
        {formError && (
          <p className={s.error} role="alert">
            {formError}
          </p>
        )}
        <Field label={tr.settings.displayName} error={errors.display_name ?? null}>
          {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} invalid={!!errors.display_name} value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />}
        </Field>
        <Field label={tr.settings.username} error={errors.username ?? null}>
          {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} invalid={!!errors.username} value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} autoComplete="off" />}
        </Field>
        <PasswordField value={form.temporary_password} onChange={(v) => setForm({ ...form, temporary_password: v })} error={errors.temporary_password} />
        <Checkbox label={tr.settings.isAdmin} description={tr.settings.isAdminHint} checked={form.is_admin} onChange={(v) => setForm({ ...form, is_admin: v })} />
        <RoleChecks value={roles} onChange={setRoles} />
      </div>
    </Dialog>
  );
}

function RolesDialog({ person, onClose, onDone }: { person: Person; onClose: () => void; onDone: () => void }) {
  const session = useSession();
  const toast = useToast();
  const [roles, setRoles] = useState<Role[]>(person.roles);
  const [error, setError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => api.put(`/projects/${session.projectId}/members`, { user_id: person.user_id, roles }),
    onSuccess: () => {
      toast.show(tr.settings.rolesSaved);
      onDone();
      if (person.user_id === session.me?.user.id) void session.refresh();
      onClose();
    },
    onError: (e) => setError(messageOf(e)),
  });
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={tr.settings.editRoles(person.display_name)}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {tr.common.cancel}
          </Button>
          <Button variant="primary" loading={m.isPending} onClick={() => m.mutate()}>
            {tr.common.save}
          </Button>
        </>
      }
    >
      {error && (
        <p className={s.error} role="alert">
          {error}
        </p>
      )}
      <RoleChecks value={roles} onChange={setRoles} />
    </Dialog>
  );
}

function ResetDialog({ person, onClose }: { person: Person; onClose: () => void }) {
  const toast = useToast();
  const [pw, setPw] = useState(generatePassword);
  const [error, setError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => api.patch(`/users/${person.user_id}`, { temporary_password: pw }),
    onSuccess: () => {
      toast.show(tr.settings.passwordReset);
      onClose();
    },
    onError: (e) => setError(e instanceof ApiError && e.code === 'WEAK_PASSWORD' ? errorMessage('WEAK_PASSWORD') : messageOf(e)),
  });
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={tr.settings.resetTitle(person.display_name)}
      description={tr.settings.resetDesc}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {tr.common.cancel}
          </Button>
          <Button
            variant="primary"
            loading={m.isPending}
            onClick={() => {
              if (pw.length < 12) setError(errorMessage('WEAK_PASSWORD'));
              else m.mutate();
            }}
          >
            {tr.settings.resetPassword}
          </Button>
        </>
      }
    >
      <PasswordField value={pw} onChange={setPw} error={error} />
    </Dialog>
  );
}
