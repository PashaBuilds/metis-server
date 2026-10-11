import { useState } from 'react';
import { Bell, Inbox } from 'lucide-react';
import {
  Button,
  Checkbox,
  Chip,
  ChipButton,
  ConfirmDialog,
  Dialog,
  Drawer,
  EmptyState,
  Field,
  IconButton,
  Input,
  Kbd,
  List,
  Row,
  Segmented,
  Select,
  Skeleton,
  SkeletonRows,
  StatusBadge,
  TabPanel,
  Tabs,
  Textarea,
  Tooltip,
  useToast,
} from '@/design/primitives';
import { EvidenceStripe, IzPanel, IzProvider, IzTrace, Logo, ViaMark, useIz, type EvidenceResolver, type EvidenceView } from '@/design/iz';
import { useMediaQuery } from '@/lib/hooks';
import s from './Vitrin.module.css';

/* Kurgusal örnek kaynak — yalnız vitrin için; gerçek veri değildir. */
const SOURCE_TEXT = `AXI PCIe köprüsü kesme yönetimi — kurgusal uzman notu

VPK120 kartında AXI PCIe köprüsü MSI kesmelerini XAxiPcie_IntrEnable() çağrısı ile etkinleştirir.
Kesme maskesi XPAR_XAXIPCIE_0_BASEADDR + 0x13C adresindeki IMR kaydında tutulur.
Link eğitimi Gen1 hızında kalırsa önce referans saatin 100 MHz olduğu doğrulanır.
Kesme işleyicisi (ISR) içinde yalnız durum bitleri temizlenir; uzun işler görev bağlamına ertelenir.`;

function fakeEvidence(id: string, quote: string): EvidenceView {
  const start = SOURCE_TEXT.indexOf(quote);
  return {
    evidence_id: id,
    source: { id: 'src-demo', title: 'AXI PCIe kesme notu (kurgusal)', kind: 'note' },
    revision: { id: 'rev-demo', number: 2, created_at: '2026-09-12T11:20:00Z', author_name: 'Barış (kurgusal)', filename: 'pcie-kesme.md', media_type: 'text/markdown', sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', extraction: 'complete', is_current: true },
    locator: { section: 'Kesme yönetimi', line_from: 3 },
    locator_label: 'Bölüm: Kesme yönetimi · satır 3',
    excerpt: quote,
    text: SOURCE_TEXT,
    highlight: start >= 0 ? { start, end: start + quote.length } : null,
    can_download: false,
    project_id: 'demo',
  };
}

const CLAIMS = [
  { id: 'e1', quote: 'VPK120 kartında AXI PCIe köprüsü MSI kesmelerini XAxiPcie_IntrEnable() çağrısı ile etkinleştirir.' },
  { id: 'e2', quote: 'Kesme maskesi XPAR_XAXIPCIE_0_BASEADDR + 0x13C adresindeki IMR kaydında tutulur.' },
  { id: 'e3', quote: 'Link eğitimi Gen1 hızında kalırsa önce referans saatin 100 MHz olduğu doğrulanır.' },
];

const resolver: EvidenceResolver = async (target) => {
  await new Promise((r) => setTimeout(r, 120));
  const claim = CLAIMS.find((c) => c.id === target.evidenceId) ?? CLAIMS[0]!;
  return fakeEvidence(claim.id, claim.quote);
};

export default function Vitrin() {
  return (
    <IzProvider resolver={resolver}>
      <VitrinBody />
    </IzProvider>
  );
}

function VitrinBody() {
  const wide = useMediaQuery('(min-width: 1280px)');
  return (
    <div className={s.page}>
      <div className={s.main}>
        <header className={s.header}>
          <Logo size={40} />
          <div>
            <h1>İz tasarım vitrini</h1>
            <p className={s.lead}>Yalnız geliştirme profili. Tokenlar, tipografi, bileşenler ve iki tema yan yana.</p>
          </div>
        </header>

        <section className={s.section} aria-labelledby="proto-h">
          <h2 id="proto-h">İz prototipi</h2>
          <p className={s.lead}>Via işaretine tıkla ya da sekme ile gelip Enter'a bas. Esc paneli kapatır ve odağı işarete döndürür.</p>
          <article className={s.knowledge}>
            <div className={s.pageMeta}>
              <StatusBadge tone="onay" label="Güncel" size="sm" />
              <span className={s.kind}>Bileşen</span>
            </div>
            <h3 className={s.pageTitle}>AXI PCIe kesme yönetimi</h3>
            <p className={s.summary}>VPK120 üzerindeki AXI PCIe köprüsünde MSI kesmelerinin nasıl etkinleştirildiği ve maskelendiği.</p>
            <div className={s.chips}>
              <Chip label="Domain" tone="muted">Gömülü yazılım</Chip>
              <Chip label="Kart" tone="muted">VPK120</Chip>
              <Chip label="Proje" tone="muted">Kurgusal-X</Chip>
            </div>
            <div className="reading">
              <EvidenceStripe count={1}>
                <p className={s.p}>
                  Köprü, MSI kesmelerini <code>XAxiPcie_IntrEnable()</code> ile etkinleştirir.
                  <ViaMark n={1} target={{ key: 'c1:e1', evidenceId: 'e1', label: 'AXI PCIe kesme notu' }} />
                </p>
              </EvidenceStripe>
              <EvidenceStripe count={2}>
                <p className={s.p}>
                  Maske, <code>XPAR_XAXIPCIE_0_BASEADDR</code> tabanına göre <code>0x13C</code> ofsetindeki IMR kaydında tutulur.
                  <ViaMark n={2} target={{ key: 'c2:e2', evidenceId: 'e2', label: 'AXI PCIe kesme notu' }} /> Link Gen1'de kalırsa ilk kontrol referans saattir.
                  <ViaMark n={3} target={{ key: 'c3:e3', evidenceId: 'e3', label: 'AXI PCIe kesme notu' }} />
                </p>
              </EvidenceStripe>
              <EvidenceStripe count={0}>
                <p className={s.p}>Bu paragraf kanıtsızdır; yanında şerit yoktur. Uzun sembol taşma testi: <code>XPAR_XAXIPCIE_0_BASEADDR_EXTREMELY_LONG_IDENTIFIER_NAME</code>.</p>
              </EvidenceStripe>
            </div>
          </article>
        </section>

        <div className={s.themes}>
          <ThemeColumn theme="light" title="Açık tema" />
          <ThemeColumn theme="dark" title="Koyu tema" />
        </div>
      </div>
      {useIzActive() && <IzPanel mode={wide ? 'docked' : 'overlay'} />}
      <IzTrace />
    </div>
  );
}

function useIzActive() {
  return !!useIz().active;
}

const TOKENS = ['--zemin', '--yuzey', '--yuzey-gomuk', '--murekkep', '--soluk', '--cizgi', '--ray', '--ray-metin', '--iz', '--iz-metin', '--iz-zemin'];
const STATUS: { tone: 'onay' | 'inceleme' | 'taslak' | 'dikkat' | 'celiski'; label: string }[] = [
  { tone: 'onay', label: 'Yayımlandı' },
  { tone: 'inceleme', label: 'İncelemede' },
  { tone: 'taslak', label: 'Taslak' },
  { tone: 'dikkat', label: 'Kısmen destekli' },
  { tone: 'celiski', label: 'Çelişki' },
];
const SCALE = [12, 13, 14, 16, 19, 23, 28, 34, 41];

function ThemeColumn({ theme, title }: { theme: 'light' | 'dark'; title: string }) {
  const toast = useToast();
  const [tab, setTab] = useState('a');
  const [seg, setSeg] = useState<'all' | 'human' | 'metis'>('all');
  const [dialog, setDialog] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [check, setCheck] = useState(true);
  return (
    <section className={[s.theme, theme === 'dark' ? 'theme-dark' : 'theme-light'].join(' ')} aria-label={title} data-theme-sample={theme}>
      <h2>{title}</h2>

      <h3 className={s.h3}>Renk tokenları</h3>
      <ul className={s.swatches}>
        {TOKENS.map((t) => (
          <li key={t} className={s.swatch}>
            <span className={s.chipColor} style={{ background: `var(${t})` }} aria-hidden />
            <code>{t}</code>
          </li>
        ))}
      </ul>

      <h3 className={s.h3}>Durum rozetleri</h3>
      <div className={s.rowWrap}>
        {STATUS.map((st) => (
          <StatusBadge key={st.tone} tone={st.tone} label={st.label} />
        ))}
        <StatusBadge tone="celiski" icon="fork" label="Çelişki incelenmeli" />
      </div>

      <h3 className={s.h3}>Tipografi ölçeği</h3>
      <div className={s.scale}>
        {SCALE.map((px) => (
          <p key={px} style={{ fontSize: px, fontWeight: px >= 34 ? 500 : px >= 19 ? 600 : 400 }}>
            {px} px — Çağrı işleyicisi ğüşıöç İĞÜŞÖÇ
          </p>
        ))}
        <p className="mono">IBM Plex Mono — XPAR_PCIE_0_BASEADDR = 0x40000000</p>
      </div>

      <h3 className={s.h3}>Düğmeler</h3>
      <div className={s.rowWrap}>
        <Button variant="primary">Yayımla</Button>
        <Button>İkincil</Button>
        <Button variant="ghost">Hayalet</Button>
        <Button variant="danger">Sil</Button>
        <Button loading>Kaydediliyor</Button>
        <Button disabled>Devre dışı</Button>
        <IconButton label="Bildirimler" variant="secondary">
          <Bell size={18} aria-hidden />
        </IconButton>
      </div>

      <h3 className={s.h3}>Chip ve kısayol</h3>
      <div className={s.rowWrap}>
        <Chip label="Kart" onRemove={() => undefined}>VPK120</Chip>
        <Chip label="Proje">Kurgusal-X</Chip>
        <ChipButton>+ Kapsam</ChipButton>
        <Kbd>Ctrl K</Kbd>
        <Tooltip content="İpucu metni">
          <Button size="sm" variant="ghost">
            İpucu
          </Button>
        </Tooltip>
      </div>

      <h3 className={s.h3}>Form</h3>
      <div className={s.form}>
        <Field label="Başlık" hint="Kısa ve açıklayıcı olsun">
          {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} placeholder="Örn. SPI saat ayarı" />}
        </Field>
        <Field label="Hatalı alan" error="Bu alan boş bırakılamaz.">
          {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} invalid />}
        </Field>
        <Field label="Tür">
          {({ id }) => (
            <Select id={id} defaultValue="note">
              <option value="note">Uzman notu</option>
              <option value="code">Kod</option>
            </Select>
          )}
        </Field>
        <Field label="Not">{({ id }) => <Textarea id={id} rows={3} defaultValue="Okuma metni 16 px, satır yüksekliği 1.65." />}</Field>
        <Checkbox label="İddiaları ve kaynak desteğini kontrol ettim" checked={check} onChange={setCheck} />
      </div>

      <h3 className={s.h3}>Sekmeler ve segmented</h3>
      <Tabs
        label="Örnek sekmeler"
        value={tab}
        onValueChange={setTab}
        tabs={[
          { value: 'a', label: 'İncelemeni bekleyenler', count: 2 },
          { value: 'b', label: 'Taslaklar' },
          { value: 'c', label: 'Yayımlananlar' },
        ]}
      >
        <TabPanel value="a">
          <Segmented
            label="Köken"
            value={seg}
            onChange={setSeg}
            options={[
              { value: 'all', label: 'Tümü' },
              { value: 'human', label: 'Kişi' },
              { value: 'metis', label: 'Metis' },
            ]}
          />
        </TabPanel>
        <TabPanel value="b">Taslak listesi</TabPanel>
        <TabPanel value="c">Yayımlanan listesi</TabPanel>
      </Tabs>

      <h3 className={s.h3}>Satır listesi</h3>
      <List label="Örnek satırlar">
        <Row>
          <div className={s.rowMain}>
            <strong>SPI saat bölücü</strong>
            <span className={s.muted}>Bugün 14:20</span>
          </div>
          <StatusBadge tone="inceleme" label="İncelemede" size="sm" />
        </Row>
        <Row>
          <div className={s.rowMain}>
            <strong>UART baud hesabı</strong>
            <span className={s.muted}>12.09.2026 09:05</span>
          </div>
          <StatusBadge tone="onay" label="Yayımlandı" size="sm" />
        </Row>
      </List>

      <h3 className={s.h3}>Diyalog, çekmece, toast</h3>
      <div className={s.rowWrap}>
        <Button onClick={() => setDialog(true)}>Diyalog</Button>
        <Button variant="danger" onClick={() => setConfirm(true)}>
          Silme onayı
        </Button>
        <Button onClick={() => setDrawer(true)}>Çekmece</Button>
        <Button onClick={() => toast.show('Silindi', { undo: () => toast.show('Geri alındı') })}>Toast (Geri al)</Button>
      </div>
      <Dialog open={dialog} onOpenChange={setDialog} title="Örnek diyalog" description="Odak diyalogda kalır; Esc kapatır." footer={<Button variant="primary" onClick={() => setDialog(false)}>Tamam</Button>} />
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Kayıt silinsin mi?" description="Kayıt aktif görünümlerden kalkar. 8 saniye içinde geri alabilirsin." confirmLabel="Sil" danger onConfirm={() => toast.show('Silindi', { undo: () => undefined })} />
      <Drawer open={drawer} onOpenChange={setDrawer} title="Örnek çekmece">
        <p>Dar ekranda İz paneli de bu şekilde açılır.</p>
      </Drawer>

      <h3 className={s.h3}>Skeleton ve boş durum</h3>
      <Skeleton width="60%" />
      <SkeletonRows rows={2} />
      <EmptyState icon={<Inbox size={28} aria-hidden />} title="Bu filtrelerle yayımlanmış bilgi yok" actions={<Button size="sm">Filtreleri temizle</Button>}>
        Filtreleri temizle ya da ilk bilgiyi ekle.
      </EmptyState>
    </section>
  );
}
