import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { Download, Link2 } from 'lucide-react';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import s from './Knowledge.module.css';

type Related = Schemas['RelatedOut'];

/** Bağlantılı bilgiler (modelsiz): notta geçen adresler ve ortak nadir tanımlayıcılar; METIS'te olmayan bağlantılı öğeye
 * içe aktarma önerisi (yalnız katkı verebilene). Bir şey yoksa bölüm hiç görünmez. */
export function RelatedPanel({ pageId, canImport }: { pageId: string; canImport: boolean }) {
  const q = useQuery({ queryKey: ['page-related', pageId], queryFn: () => api.get<Related>(`/pages/${pageId}/related`) });
  const links = q.data?.links ?? [];
  const missing = canImport ? (q.data?.missing ?? []) : [];
  if (!links.length && !missing.length) return null;
  return (
    <section id="baglantili" className={s.section} aria-labelledby="baglantili-h">
      <h2 id="baglantili-h" className={s.sectionTitle}>
        {tr.related.title}
      </h2>
      <p className={s.muted}>{tr.related.lead}</p>
      {links.length > 0 && (
        <ul className={s.relations}>
          {links.map((l) => (
            <li key={l.page_id} className={s.relation}>
              <span className={`${s.predicate} ${s.relatedWhy}`}>
                <Link2 size={14} aria-hidden />
                {l.reason === 'reference' ? tr.related.reference : tr.related.shared(l.symbols ?? [])}
              </span>
              <Link to="/bilgi/$pageId" params={{ pageId: l.page_id }} search={{}} className={s.relLink}>
                <span>{l.title}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {missing.length > 0 && (
        <>
          <h3 className={s.relatedSub}>{tr.related.missingTitle}</h3>
          <ul className={s.relations}>
            {missing.map((m) => (
              <li key={m.url} className={s.relation}>
                <Link to="/katki" search={{ kaynak: m.url, baglanti: m.connection_id }} className={s.relLink}>
                  <Download size={14} aria-hidden />
                  <span>{tr.related.importIt}</span>
                </Link>
                <span className={s.relatedUrl}>{m.url}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
