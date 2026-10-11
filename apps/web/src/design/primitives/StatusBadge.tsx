import { AlertTriangle, Ban, Eye, GitFork, Loader2, MessageCircleQuestion, PencilLine, SearchX, ShieldCheck, XCircle, Clock, type LucideIcon } from 'lucide-react';
import s from './StatusBadge.module.css';

export type Tone = 'onay' | 'inceleme' | 'taslak' | 'dikkat' | 'celiski';

const ICONS: Record<string, LucideIcon> = {
  onay: ShieldCheck,
  inceleme: Eye,
  taslak: PencilLine,
  dikkat: AlertTriangle,
  celiski: XCircle,
  fork: GitFork,
  spin: Loader2,
  clock: Clock,
  searchx: SearchX,
  ban: Ban,
  question: MessageCircleQuestion,
};

interface Props {
  tone: Tone;
  label: string;
  icon?: keyof typeof ICONS;
  size?: 'sm' | 'md';
}

/** Durum her zaman ikon + etiket ile gösterilir; renk tek başına sinyal değildir. */
export function StatusBadge({ tone, label, icon, size = 'md' }: Props) {
  const Icon = ICONS[icon ?? tone] ?? ShieldCheck;
  return (
    <span className={[s.badge, s[tone], s[size]].join(' ')}>
      <Icon size={size === 'sm' ? 13 : 14} aria-hidden className={icon === 'spin' ? s.spin : undefined} />
      <span>{label}</span>
    </span>
  );
}
