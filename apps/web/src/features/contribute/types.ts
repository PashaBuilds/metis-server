import type { Schemas } from '@/lib/api/client';

export type SourceDetail = Schemas['SourceDetailOut'];
export type SourceRow = Schemas['SourceOut'];

export interface EvidenceLink {
  evidence_id: string;
  quote: string;
  label?: string;
}

export interface DraftClaim {
  key: string;
  statement: string;
  kind: string;
  evidence: EvidenceLink[];
}

export type ModelOption = Schemas['AvailableModel'];

export const normalize = (t: string) => t.replace(/\s+/g, ' ').trim();

/** İddia en az bir alıntıda birebir geçiyor mu? */
export function isVerbatim(c: DraftClaim): boolean {
  const st = normalize(c.statement);
  if (!st) return false;
  return c.evidence.some((e) => normalize(e.quote).includes(st));
}
