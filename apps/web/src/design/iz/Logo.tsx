/** METIS logosu: iki ortogonal izden soyut bir M; üç via, ortadaki altın. */
export function Logo({ size = 28, tone = 'ink', title = 'METIS' }: { size?: number; tone?: 'ink' | 'rail'; title?: string }) {
  const stroke = tone === 'rail' ? 'var(--ray-metin)' : 'var(--murekkep)';
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-label={title} fill="none">
      <path d="M6 26 V10 L16 20" stroke={stroke} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M26 26 V10 L16 20" stroke={stroke} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="6" cy="26" r="2.6" fill={tone === 'rail' ? 'var(--ray)' : 'var(--yuzey)'} stroke={stroke} strokeWidth="2" />
      <circle cx="26" cy="26" r="2.6" fill={tone === 'rail' ? 'var(--ray)' : 'var(--yuzey)'} stroke={stroke} strokeWidth="2" />
      <circle cx="16" cy="20" r="3.4" fill="var(--iz)" />
    </svg>
  );
}
