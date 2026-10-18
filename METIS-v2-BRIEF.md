# METIS v2 — Claude Code Yeniden Yapım Brief'i

> **Kimin için:** Bu doküman, METIS'i sıfırdan yeniden yazacak Claude Code (Opus 5.5) oturumunun ana talimatıdır.
> **Kaynak:** önceki sürümün deposu, `v0.5.5` etiketi (14 Eyl 2026). O repo ChatGPT/Codex ile yazıldı; burada **referans** olarak kullanılır, kod yapısı kopyalanmaz.
> **Hazırlayan:** Claude, 10 Eki 2026.

> **Ürün sahibinin kararları (10 Eki 2026) — kesinleşti, yeniden sorma:**
> 1. **Yeni repo.** v0.5.5'ten gereken referans dosyaları geliştirme sırasında `reference/v0.5.5/` altındaydı; bu klasör yalnız özel arşiv deposunda tutulur, bu depoda yoktur.
> 2. **Doğrudan sunucu:** İlk hedef çok kullanıcılı şirket içi sunucu. Tek kullanıcılı masaüstü EXE v2'de **yok**.
> 3. **Veriler taşınacak:** v0.5.5'teki tüm bilgi, kaynak, onay ve yayın geçmişi v2'ye aktarılır (Bölüm 5.10).
> 4. **Mentor cevabı:** Alıntılar + her cümlesi kanıta bağlı, deterministik denetlenen kısa açıklama (Bölüm 5.6).

---

## 0. Çalışma biçimi: kesintisiz, uçtan uca

Ürün sahibinin tercihi (10 Eki 2026): **Oturum tüm fazları (0-10) baştan sona, ara onay beklemeden bitirir.** Ürün sahibi bitmiş ürün üzerinden yorum yapacak.

- Soru sorma, onay bekleme. Bölüm 11'deki altyapı sorularında **önerilen varsayılanı** kullan, kararı `docs/PROGRESS.md`'ye yaz.
- Tasarım vitrini (Faz 0) yine yapılır ama onay kapısı değildir: ekran görüntüleri `docs/design/` altına konur, sonraki fazlara devam edilir.
- Her fazın sonunda: kabul ölçütlerini çalıştır, `docs/PROGRESS.md`'yi güncelle, **commit + push** et (oturum kesilirse iş kaybolmasın; yeni oturum PROGRESS.md'den devam edebilsin).
- Bir kabul ölçütü bu ortamda doğrulanamıyorsa (gerçek Windows sunucu, şirket modeli, ürün sahibinin gerçek yedeği) mock/sentetik ile doğrula, gerçek ortam doğrulamasını "yapılmadı" olarak işaretle ve devam et. Takılıp kalma; engeli raporla, sonraki işe geç.
- Faz 11 (tool-call döngüsü) opsiyoneldir; yapma, yalnız gerekçesini raporla.
- Bitişte `docs/TESLIM.md` yaz (Bölüm 10 sonundaki "Teslim" maddesi).

---

---

## 1. METIS nedir — tek paragraf

METIS, bir şirketin gömülü yazılım ekibinin teknik bilgisini **kaynaklarıyla** tutan, insan onayıyla büyüyen, şirket içi ve internetsiz çalışan bir bilgi ve mentorluk platformudur. Kullanıcı bir kaynak (uzman notu, kod, PDF, tablo, test kaydı) ekler; Metis'in yerleşik worker'ı şirket içi LLM ile bundan bir taslak çıkarır; bir insan taslağı kanıtıyla birlikte inceler ve yayımlar. Mentor yalnızca **yayımlanmış, onaylı ve kapsamı uyan** bilgiden cevap verir; bilgi yoksa bunu açıkça söyler. Hedef: yeni bir mühendisin "ilk başvurduğu mentor" olmak.

**Ürün sloganı (korunur):** *Ekibin teknik bilgisi, kaynaklarıyla.*

---

## 2. Değişmez ilkeler (eski repodan aynen taşınır)

Bunlar pazarlık konusu değildir. Her faz bunlara karşı test edilir.

1. **İnsan onayı zorunlu.** LLM veya worker hiçbir zaman onaylamaz, yayımlamaz, silmez, yetki değiştirmez, anahtar okumaz. Bu, prompt ile değil **sunucu tarafı yetki denetimiyle** sağlanır.
   > **Güncelleme (2026-10-18, ürün sahibinin kararı):** onay ilkesi "**yazar + otomatik kontrol**" olarak değişti. Varsayılan politika `self_publish` ("Yazar yayımlar"): katkı sahibi taslağını (kendi ya da başkasının bilgisi için) **kendisi** yayımlar; ikinci bir kişinin onayı gerekmez. Yayından hemen önce Metis taslağı yayındaki bilgilerle karşılaştırır — kural (aynı biçimli, farklı değerli iddia, örtüşen kapsam) + uygun model varsa yapay zekâ (çelişki, tekrar, örtüşme) — ve sorun varsa yan yana gösterip uyarır. Kullanıcı "Yine de yayımla" derse çelişki Bilgi sağlığına bulgu olarak düşer; model yoksa ya da yanıt vermezse bu açıkça yazılır ve yalnız kural sonucuyla yayımlanabilir. Başkasının bilgisi güncellenince sahibine ana sayfada "Bilgilerin güncellendi" bildirimi gider. Değişmeyenler: yayın yine bir **insanın** açık eylemidir (model/worker yayımlamaz), onay kaydı (`policy=self_publish`) içerik hash'ine bağlıdır, kontrol sonucu hash'e bağlıdır (içerik değişince yeniden kontrol), atomik yayın, kanıt kuralları. "Bağımsız inceleme" politikası Ayarlar'dan seçilebilir; seçilirse eski akış aynen geçerlidir.
2. **Revizyonlar değişmez.** Kaynak, sayfa, ilişki ve kanıt revizyonları immutable'dır (ORM hook + PostgreSQL trigger). Düzenleme = yeni revizyon.
3. **Onay hash'e bağlıdır.** Onay, değişiklik setinin içerik hash'ine bağlanır. Onaydan sonra tek karakter değişirse yeniden onay gerekir. Taban revizyon ilerlediyse `409 REVISION_CONFLICT`.
4. **Atomik yayın.** Yayın: proje satır kilidi → manifest → arama indeksi → en son aktif yayın işaretçisi. Arada hata olursa eski yayın hizmete devam eder.
5. **Kaynaksız teknik iddia yok.** Mentor'un her iddiası onaylı bir kanıta bağlıdır; kanıt ID'leri ve alıntılar **deterministik** olarak doğrulanır. Model çıktısı validator'ı geçsin diye yamalanmaz.
6. **Dürüst çekimserlik.** "Bilgi havuzunda yok" (`NO_EVIDENCE`) ile "arama/model hatası" (`RETRIEVAL_UNAVAILABLE`, `MODEL_UNAVAILABLE`) asla karıştırılmaz. Gizli bir projede cevap olduğu ima edilmez.
7. **Kapsam metadata'dan karar verilir**, alıntı metninden çıkarılmaz. Boş kapsam "her şeye uyar" demek değildir; `*` (Bağımsız) ile boş (Belirlenmemiş) ayrıdır.
8. **Sahte veri yok.** Ölçülmemiş değer `null`/"ölçülmedi" olarak gösterilir, 0 değil. Demo/kurgusal içerik her yerde açıkça etiketlenir. Test edilmeyen davranışa "çalışıyor" denmez.
9. **Kaynak içeriğindeki talimatlar veridir** (prompt injection). Model'e yayın aracı verilmez.
10. **Hedef ortam:** şirket içi ağda, internetsiz bir **sunucu** (varsayılan Windows Server, servis olarak); kullanıcılar tarayıcıdan bağlanır. Docker/WSL zorunluluğu yok. Kurulum çevrimdışı paketle yapılır. Çalışma zamanında CDN yok — font, ikon, her şey paketin içinde.
11. **Anahtarlar** kodda, logda, Git'te, tarayıcıda asla yer almaz. Sunucuda AES-GCM ile şifreli; UI'da yalnız "anahtar tanımlı" görünür.
12. **Erişim yavaş çağrılardan sonra yeniden kontrol edilir** (model çağrısı bitince, kaydetmeden önce). Erişilemeyen kayıt için `404` (varlığı sızdırma).

---

## 3. Ürün sahibinin tercihleri (v0.5.x geçmişinden çıkarıldı)

Eski reponun `PROGRESS.md`, release notları ve `AGENTS.md` dosyasından çıkan, kullanıcının açıkça istediği/şikâyet ettiği şeyler. **Bunlar tasarım kararlarını yönlendirir.**

**Sadelik (en güçlü tema)**
- "Önce en sade kullanıcı akışını sun. Yeni özellikleri somut ihtiyaç olmadan ekleme; teknik ayrıntıları isteğe bağlı göster, kritik soru ve etkileri gizleme."
- Başlıkları tekrar eden sloganlar, üç kez yinelenen güven satırları, gereksiz dipnotlar kaldırıldı. **Tekrar etme.**
- Görev sonuçları **sonuç odaklı**: önce ne oldu, sonra (katlanmış) teknik ayrıntı.
- Görev kataloğu 7 → 2'ye indi: "Taslağı düzenle ve karşılaştır", "Bilgi havuzunu denetle".
- "Katkılarım" ve "İncelemeler" tek **Kayıtlar** ekranında birleşti (Taslaklar / Yayımlananlar sekmeleri).
- Kullanıcı isteğiyle animasyon duraklat/oynat düğmesi ve kafa karıştıran "ayrı yayın" rozeti kaldırıldı.

**Silme**
- Her aşamada silinebilmeli (önce yasaktı, kullanıcı kaldırttı); bilgi havuzundan doğrudan "Bilgiyi sil".
- Silinen kayıtların kaynakları, görevleri ve mentor cevapları aktif görünümlerden kaybolmalı.
- Kapsam tanımları silinebilmeli.

**Kapsam modeli**
- Yazılım sürümü / yapılandırma boyutları **istenmedi**.
- Dört boyut: **Domain / YATT / Kart / Proje** ("YATT grubu" değil, "YATT").

**Model laboratuvarı ve mentor modeli**
- UI asla sessizce model seçmesin: açık onay kutuları + "Tümünü seç".
- Test sonuçları model bazında ve topluca temizlenebilmeli, temizlenen geri gelmemeli (v1'de localStorage ile yapılmıştı — v2'de **sunucuda** tutulmalı).
- Projeye özel yeterlilik kaldırıldı: **ortak benchmark'ı geçen model her yerde kullanılabilir.**
- Mentor modeli ana sayfada ve mentor ekranında seçilebilmeli; **sessiz fallback yok** — model kullanılamıyorsa nedeni açıkça yazılır.
- Model gerekçeleri **Türkçe** olmalı.

**Diğer**
- Kayıtlarda saat:dakika görünsün; filtre tercihleri kalıcı olsun; bot/Metis kimliği görünsün.
- Kurulumu basit olsun: v1'de "tek dosya" ve "tek ZIP release asset'i" istedi. v2'de karşılığı: **tek ZIP çevrimdışı sunucu kurulum paketi** + tek PowerShell komutu.
- Taslak ↔ yayımlanan kayıt bağlantısı görünür olsun.

**Geliştirme ajanına çalışma kuralları** (eski `AGENTS.md` → yeni `CLAUDE.md`, Faz 0'da oluştur):
- Kullanıcı eylem istediğinde uygula; rutin, geri alınabilir adımlarda tekrar izin sorma. Kapsamı veya veri güvenliğini etkileyen belirsizliği netleştir.
- Kısa, somut Türkçe. İlerleme mesajında bulgu + sonraki adım; teslimde değişiklik, doğrulama, kalan sınırlar.
- Mock, gerçek model, izole DB ve tarayıcı doğrulamalarını **ayrı** bildir.
- Önemli kararları ve doğrulamaları `docs/PROGRESS.md`'de tut. Yerel commit / push / release durumlarını ayır.
- Kullanıcı verisini, kaynak revizyonlarını ve mevcut çalışmayı koru; denemeleri kurgusal veriyle yap.

---

## 4. v1'den alınan dersler

| Sorun (v1) | v2'de yapılacak |
|---|---|
| `main.py` 44 KB, `gateway.py` 37 KB tek satırlık monolit; star import; handler'lar kütüphane gibi çağrılıyor | Modül başına `router / schemas / service / repo`; HTTPException yalnız router katmanında |
| `settings` tablosu gizli şema (çelişki vakaları, çözümler, veri setleri, kapsam kataloğu…) `LIKE 'prefix:%'` ile taranıyor | Her biri gerçek tablo |
| İlişkiler JSON dizilerinde (roller, ACL, evidence_ids, revisions), FK/indeks yok, N+1 ve doğrusal tarama | Join tabloları + FK + indeks |
| Zaman damgaları `String(40)`, lease'ler float | `timestamptz` |
| `create_all` + elle "v2" migration | **Alembic** |
| Her yayında tüm arama indeksinin kopyası | Yalnız güncel yayımlanmış revizyonların indeksi + `publication_pages` geçmişi |
| Arama: Python'da kaba ILIKE puanlama, her sayfa "kapsama örneği" olarak modele gidiyor | PG FTS (`simple` + `turkish`) + `ts_rank_cd` + başlık/alias/sembol eşleşmesi; `pg_trgm` varsa sembol bulanık arama |
| Her mentor cevabı 2 model çağrısı (seçim + cevap) | Seçim çağrısı yalnız aday sayısı eşiği aşınca |
| OpenAPI sözleşmesi koddan kopmuş | OpenAPI koddan üretilir, frontend tipleri ondan üretilir (`openapi-typescript`), CI'da diff kontrolü |
| Frontend: tüm tipler `any`, router yok (elle hash), 91 KB `App.tsx`, 69 KB tek CSS (seçiciler 4-6 kez yeniden tanımlı) | Typed router, feature klasörleri, CSS Modules + token dosyası |
| 8-10 px yazılar (130+ kullanım) | Minimum 12 px; okuma metni 16 px |
| İnceleme detayında diff'ten önce ~10 banner/panel | Diff merkezde; bağlam tek bir "Geçmiş ve bağlam" bölümünde katlı |
| Fencing, lease, checkpoint JSON, prompt sürümü UI'ya sızıyor | Yalnız "Teknik ayrıntılar" katlanır bölümünde |
| Ölü kontroller (çalışmayan dropdown, tıklanmayan TOC, JSON indiren "Markdown" düğmesi) | Çalışmayan hiçbir kontrol gösterilmez |
| `window.confirm` ile silme | Erişilebilir onay diyaloğu + 8 sn "Geri al" toast'u |
| DeepSeek desteği `api.deepseek.com` origin'ine sabit kodlu | Transport profili **probe sonucundan** seçilir (json_schema destekleniyor mu?) |
| "Yeni not/eski not" çerçevesi modeli yeniye yanlı yaptı | Nötr `kayit_a / kayit_b`; tarih tek başına güncelleme gerekçesi değil |
| Benchmark worker döngüsünü bloke ediyor | Ayrı kuyruk/öncelik; mentor sorguları her zaman önce |

**Korunacak iyi tasarımlar:** immutable revizyon + hash'e bağlı onay + atomik yayın; sadece onaylı iddialara indeks olan mentor çıktısı + deterministik validator; yavaş çağrı sonrası yetki yeniden kontrolü; lease + fence + idempotency + iddia fingerprint'i + bütçe; kalıcı `model_calls` logu + doğrulanan cache; prompt/config/anahtar değişince yeterliliği düşüren fingerprint; SSRF koruması (allowlist + DNS + ağ kontrolü); sandbox'lı PDF çıkarımı; 4 boyutlu kapsam semantiği.

---

## 5. Teknik mimari

### 5.1 Yığın

| Katman | Seçim | Not |
|---|---|---|
| Frontend | React 19 + TypeScript (strict) + Vite | |
| Router | TanStack Router | Typed URL search params → filtreler URL'de |
| Veri | TanStack Query | Cache, dedupe, polling, optimistic update |
| API tipleri | `openapi-typescript` + ince `fetch` sarmalayıcı | `any` yasak |
| Erişilebilir primitive'ler | Radix UI (Dialog, Popover, DropdownMenu, Tabs, Tooltip, ScrollArea) | Kendi stilimizle |
| Stil | CSS Modules + `tokens.css` (CSS custom properties) | Tailwind yok; tek kaynak tokenlar |
| Hareket | `motion` (Framer Motion) | `prefers-reduced-motion` saygısı |
| Graf | `@xyflow/react` + `elkjs` (orthogonal routing) | Kavram haritası |
| Markdown | `react-markdown` + `remark-gfm` + `rehype-sanitize` | Ham HTML, script, tehlikeli URL yok |
| Kod vurgulama | Hafif, paketlenmiş bir highlighter (ör. `prism-react-renderer`) | C/C++/Python/Tcl/VHDL |
| Fontlar | `@fontsource/ibm-plex-sans`, `@fontsource/ibm-plex-mono` | `latin-ext` alt kümesi (ğ ş ı İ) — **doğrula** |
| İkonlar | `lucide-react` | |
| Backend | Python 3.12+ / FastAPI / SQLAlchemy 2 / Pydantic 2 | Sunucuda kurulabilen sürüme göre wheelhouse |
| DB | PostgreSQL 16+ (Windows servisi olarak, native) | SQLite hiçbir yerde, testlerde bile kullanılmaz — PG semantiği farklı |
| Migration | Alembic | |
| HTTP istemci | httpx (async) | `trust_env=False`, redirect yok, şirket CA bundle |
| PDF | pypdf, subprocess sandbox (zaman/bellek limiti) | v1'deki yaklaşım korunur |
| Test | pytest, Playwright + `@axe-core/playwright` | |
| Paket | Çevrimdışı sunucu ZIP'i: hash-kilitli wheelhouse + derlenmiş frontend + PowerShell kurulum/servis betikleri | Bölüm 5.9 |

### 5.2 Repo yapısı

```
metis/
├─ CLAUDE.md                     # ajan çalışma kuralları (Bölüm 3'ten)
├─ docs/
│  ├─ PROGRESS.md
│  ├─ adr/                       # yeni ADR'ler (v2-ADR-001…)
│  └─ design/                    # tasarım sistemi notları, ekran görüntüleri
├─ apps/web/src/
│  ├─ app/                       # shell, router, providers, komut paleti
│  ├─ design/                    # tokens.css, primitives (Button, Chip, Dialog…), İz bileşenleri
│  ├─ features/
│  │  ├─ home/  library/  page/  mentor/  contribute/  records/
│  │  ├─ tasks/  health/  map/  scopes/  lab/  settings/  auth/
│  ├─ lib/api/                   # generated schema.d.ts + client
│  └─ i18n/tr.ts                 # TÜM kullanıcı metinleri + hata kodu → mesaj
├─ services/metis/
│  ├─ core/                      # config, db, security, errors (kod kataloğu), audit
│  ├─ modules/
│  │  ├─ auth/ projects/ scopes/ sources/ knowledge/ changes/
│  │  ├─ search/ mentor/ jobs/ prep/ health/ lab/ export/ backup/
│  │  │   └─ (her biri) router.py schemas.py service.py repo.py
│  ├─ llm/
│  │  ├─ client.py transport.py validators.py
│  │  └─ prompts/                # versiyonlu .md prompt dosyaları
│  ├─ worker/                    # job döngüsü, pipeline adımları
│  ├─ legacy_import/             # v0.5.5 yedeğinden içe aktarma (Bölüm 5.10)
│  ├─ cli.py                     # metis admin|migrate|backup|restore|import-v1|doctor
│  └─ migrations/                # Alembic
├─ domain-packs/embedded-software/manifest.json
├─ evals/                        # prompt değerlendirme vakaları (v1'den taşınır)
├─ deploy/
│  ├─ windows/                   # install-offline.ps1, upgrade.ps1, servis tanımları
│  ├─ linux/                     # systemd birimleri (ikincil hedef)
│  └─ build-bundle.py            # çevrimdışı ZIP üretimi
└─ tests/  (api/, worker/, e2e/, visual/, legacy_import/)
```

### 5.3 Veri modeli (temizlenmiş)

Tüm ID'ler UUID; zaman `timestamptz` (UTC saklanır, UI yerel saat:dakika gösterir). Silme = `deleted_at` + `deleted_by` (soft delete); her liste sorgusu silinmişleri filtreler.

**Kimlik ve proje**
- `users` (username, display_name, password_hash scrypt, kind: human|worker, is_admin, active)
- `sessions` (token_digest, user_id, expires_at, csrf)
- `projects` (name, description, is_demo, review_policy: independent|owner_review, review_interval_days, active_publication_id)
- `project_members` (project_id, user_id, role) — rol başına satır: reader | contributor | reviewer | steward

**Kapsam**
- `scope_values` (project_id, dimension: domain|yatt|kart|proje, value, deleted_at) — kapsam kataloğu
- Kapsam atamaları revizyonlarda `scope jsonb` (`{domain:[], yatt:[], kart:[], proje:[]}`, `["*"]` = Bağımsız) + GIN indeks

**Kaynak ve kanıt**
- `sources` (project_id, owner_id, title, kind: note|code|document|image|table|test, current_revision_no)
- `source_acl` (source_id, user_id) — boşsa tüm proje üyeleri
- `source_revisions` immutable (number, sha256, media_type, filename, text, meta jsonb: repo/commit/path/symbol/pages, extraction: complete|partial|annotation_only, extractor_version)
- `evidence` immutable (source_revision_id, locator jsonb: {page, section, symbol, line_from, line_to}, excerpt, char_start, char_end)

**Bilgi**
- `pages` (project_id, kind, owner_id, lifecycle: active|deprecated|withdrawn, freshness: current|review_due|dependency_changed|unknown, current_revision_no, published_revision_id)
- `page_revisions` immutable (title, summary, body_md, scope jsonb, unknowns jsonb, author_id, hash)
- `claims` immutable (page_revision_id, ord, statement, kind: design_intent|observed_behavior|tested_result|expert_statement|hypothesis|derived_calculation, support: supported|partial|conflicting|unsupported|not_reviewed)
- `claim_evidence` (claim_id, evidence_id, quote)
- `relations` + `relation_revisions` (subject_page, predicate, object_page, scope, evidence, review_state)

**Değişiklik ve yayın**
- `change_sets` (project_id, author_id, origin: human|metis, job_id, summary, state: draft|in_review|approved|rejected|published|superseded, hash, predecessor_id)
- `change_set_items` (change_set_id, page_id, base_revision_id, proposed_revision_id)
- `change_set_relations`
- `reviews` immutable (change_set_id, hash, reviewer_id, decision: approve|request_changes|reject, reason, evidence_checked, policy)
- `publications` immutable (project_id, change_set_id, created_at) + `publication_pages` (publication_id, page_id, revision_id)
- `search_documents` (page_id PK, revision_id, publication_id, title, aliases, symbols text[], tsv_simple, tsv_turkish) — yalnız aktif yayın

**Worker ve hazırlık**
- `jobs` (project_id, requester_id, kind, inputs jsonb, state, priority, worker_id, fence, attempt, lease_until, checkpoint jsonb, budget_used)
- `job_messages` (job_id, role: metis|user, body, created_at) — "Yanıtını bekliyor" soruları
- `job_outputs` (job_id, change_set_id)
- `extracted_claims` (fingerprint unique, subject, attribute, value, condition, quote, quote_start, quote_end, scope, state)
- `open_decisions`

**Sağlık**
- `findings` (project_id, kind: conflict|source_changed|review_due|broken_ref|missing_owner, severity, state, page_ids, detail, resolution_reason)
- `conflict_cases`, `conflict_options`, `conflict_resolutions` (gerçek tablolar)
- `schedules` (kind, interval, next_run_at, enabled) — **tek** bakım zamanlayıcısı

**Model**
- `providers` (name, base_url, secret_enc, secret_version, ca_bundle_ref, max_concurrency, timeout_s)
- `models` (provider_id, remote_id, display_name, enabled, transport_profile, config_version, circuit_until)
- `model_probes` (model_id, capability, status: tested_pass|tested_fail|unknown, detail, at)
- `benchmark_datasets`, `benchmark_cases`, `benchmark_runs`, `benchmark_results`
- `model_qualifications` (model_id, fingerprint, task_class, passed, critical_errors, run_id, at, hidden_at) — "sonucu temizle" = `hidden_at`, sunucuda kalıcı
- `model_calls` (model_id, prompt_id, prompt_version, input_hash, state, raw_output, parsed_output, usage, latency_ms, error, cached_from, job_id, answer_id)
- `model_cache`

**Mentor ve çapraz kesen**
- `answers` (owner_id, project_id, question, scope, decision, publication_id, model_id, prompt_version, timings jsonb, deleted_at)
- `answer_citations` (answer_id, ord, claim_id, evidence_id, quote)
- `answer_feedback`
- `audit_events` immutable (actor_id, op, target_type, target_id, detail, correlation_id)
- `idempotency_keys` (user_id, key, payload_hash, result_ref)
- `login_attempts` (username, ip, at, success) — çok kullanıcılı sunucuda hız sınırı süreç içinde değil DB'de
- `user_preferences` (user_id, key, value) — tema, yoğunluk, son filtreler, ray durumu
- `legacy_import_runs` (started_at, source_sha256, mode: dry_run|apply, report jsonb, state) — v0.5.5 aktarım kaydı

**ID ve hash sürekliliği:** v0.5.5 kayıtlarının UUID'leri v2'de **aynen korunur** (bağlantılar, yer imleri ve denetim kaydı kırılmasın). Hash'i olan tablolarda (`page_revisions`, `change_sets`, `reviews`) `legacy_hash` sütunu tutulur; v2 hash'i yeni şemayla yeniden hesaplanır.

### 5.4 API ilkeleri
- `/api/v1`, OpenAPI koddan; cursor sayfalama; boyut limitleri.
- Hata zarfı: `{error:{code, message, retryable, correlation_id, details}}`. `message` İngilizce/teknik; **kullanıcıya gösterilen Türkçe metin frontend'de `i18n/tr.ts`'teki kod kataloğundan**.
- 401 / 403 / 404 (varlık gizleme) / 409 / 422 / 429 / 503. HTTP hataları ile epistemik sonuçlar (NO_EVIDENCE vb.) ayrı.
- Aktör her zaman oturumdan; payload ile inceleyici taklit edilemez.
- Idempotency-Key: aynı payload aynı sonuç, farklı payload 409.
- Uzun işler: SSE + `Last-Event-ID` ile yeniden bağlanma (v1'de replay yoktu). Ters vekil (IIS/nginx) arkasında buffering kapalı ve heartbeat'li çalışmalı.
- Güvenlik başlıkları (CSP, frame deny, nosniff, HSTS), cookie HttpOnly + Secure + SameSite=Strict, CSRF token, Origin allowlist (`METIS_PUBLIC_URL`), `Host` doğrulaması, güvenilir vekil başlıkları yalnız tanımlı vekil IP'lerinden.
- Kimlik: v2 ilk sürümde yerel hesaplar (scrypt). Kimlik doğrulama bir `AuthProvider` arayüzünün arkasında olsun; şirket AD/LDAP entegrasyonu (Açık soru 2) koda dokunmadan eklenebilsin. Parola sıfırlama yöneticinin geçici parola vermesiyle (e-posta yok).
- Çok kullanıcılı varsayılanlar: inceleme politikası **bağımsız inceleme** (kendi taslağını onaylayamaz); `owner_review` yalnız yöneticinin açıkça seçtiği projelerde.

### 5.5 Arama
1. Metadata filtreleri (kapsam, tür, yayın durumu, erişim).
2. Tam sembol eşleşmesi (`XAxiPcie_IntrEnable`, `INIT_BUS`) — sembol asla normalize edilmez; `symbols text[]` + GIN.
3. Başlık / alias / sözlük (domain-pack terminolojisi: "kesme" ↔ interrupt ↔ ISR).
4. PG FTS: `tsv_simple` (semboller, İngilizce) + `tsv_turkish` (Türkçe kök), `ts_rank_cd` ile birleşik puan.
5. `pg_trgm` gömülü PG paketinde varsa bulanık sembol araması; yoksa özellik kapalı ve UI'da "bulanık arama kullanılamıyor".
6. pgvector **Faz 10 sonrası**, ölçülmüş kazanç varsa (RRF ile birleşim, embedding fingerprint'i).

### 5.6 Kaynaklı mentor hattı
```
kimlik → kapsam → aktif yayın → arama (top-k, deterministik)
  → [aday > 8 ise] kaynak seçimi çağrısı (mentor-source-selection)
  → kanıt paketi: yalnız onaylı, desteklenen, kanıt metninde birebir geçen iddialar
  → cevap çağrısı (evidence-explain-v1) → deterministik doğrulama
  → yetki/geri çekme yeniden kontrolü → kaydet (publication_id, model, prompt sürümü, zamanlar)
```
- Karar kodları ve UI karşılıkları (v1'den aynen):
  `SUPPORTED` Kanıtla destekli · `PARTIAL` Kısmen destekli · `NEEDS_SCOPE` Kapsamı netleştirelim · `CONFLICTING` Çelişki incelenmeli · `NO_EVIDENCE` Yeterli kanıt bulunamadı · `RETRIEVAL_UNAVAILABLE` Arama kullanılamıyor · `MODEL_UNAVAILABLE` Model servisi kullanılamıyor · `VALIDATION_FAILED` Kanıt kontrolü geçilemedi
- Açık çelişki bulgusu olan sayfa seçilirse karar zorla `CONFLICTING`.
- Akış: yalnız ilerleme olayları ("Kaynaklar aranıyor" → "İlgili kayıtlar bulundu" → "Cevap denetleniyor"); doğrulanmamış teknik token asla gösterilmez. Kaynaklar doğrulamadan önce gösterilebilir.
- **Cevap biçimi (karar verildi): alıntılar + kaynaklı kısa açıklama.**
  - Model çıktısı: `{decision, explanation: [{text, claim_ids: [..]}], claims: [{claim_id, evidence_id, quote}]}`. `explanation` 1-4 cümle; `level` (Kısa / Adım adım / Ayrıntılı) cümle sayısını ve yapısını belirler (Adım adım = numaralı adımlar, her adım yine kanıtlı).
  - **Deterministik cümle denetimi** (`llm/validators.py`, saf fonksiyon, birim testli):
    1. Her cümlenin ≥1 `claim_id`'si olmalı ve bu ID'ler kanıt paketinde olmalı.
    2. Cümledeki her **sayı** (birim dahil normalize: `100 MHz` = `100MHz`; ondalık virgül/nokta), her **sembol/tanımlayıcı** (`[A-Za-z_][A-Za-z0-9_]{2,}` içinde büyük harf, alt çizgi veya rakam içerenler, ör. `XPAR_PCIE_0_BASEADDR`, `init_bus`), her **hex/ikili değer** (`0x40000000`) ve **sürüm dizgesi** bağlı iddiaların metninde **birebir** geçmeli.
    3. Olumsuzlama tersine dönmemeli: iddia "desteklemez/yoktur/değildir" içeriyorsa ve cümle aynı özneyle olumlu kurulmuşsa cümle reddedilir (basit kural; kapsamı testlerle belgelenir, mükemmel olduğu iddia edilmez).
    4. Geçmeyen cümle **atılır**, düzeltilmez. Hiç cümle kalmazsa yalnız alıntılar gösterilir ve kayda `explanation_dropped` düşülür.
    5. `claims` alıntıları v1'deki gibi: onaylı iddianın tamamı, karakteri karakterine.
  - Çekimser kararlarda (`NO_EVIDENCE`, `NEEDS_SCOPE`, `CONFLICTING`…) `explanation` ve `claims` boş; açıklama metni sabit Türkçe mesaj kataloğundan gelir. `NEEDS_SCOPE`'ta hangi kapsam boyutunun cevabı değiştirdiği yazılır.
  - UI'da açıklama cümleleri normal metin, sonlarında ●n işaretleri; altında "Kaynak alıntıları" numaralı kartlar. Atılan cümle sayısı yalnız "Kanıt, kapsam ve üretim kaydı"nda görünür.
  - Değerlendirme: `evals/` setine açıklama vakaları eklenir — doğru cümle, uydurma sayı, yanlış sembol, ters olumsuzlama, kapsam dışı genelleme. Prompt sürümü `evidence-explain-v1`; v1'in `evidence-quotes-v4` sonuçlarının altına düşmemeli (aynı vakalarda karar doğruluğu).
- Model seçimi: kullanıcı seçtiyse o; "Otomatik" ise deterministik routing. **Sessiz fallback yok** — seçilen model uygun değilse neden yazılır ve kullanıcıya alternatif önerilir.

### 5.7 Metis worker (Hermes yok)
Eylül 2026 kararı: Hermes, MCP köprüsü, webhook, snapshot dizini **tamamen kalkar**. Model çağrıları worker içinde doğrudan yapılır.

- Kuyruk: `jobs` tablosu, `SELECT … FOR UPDATE SKIP LOCKED`, `lease_until` + `fence` + `attempt` (≤3). İptal/yeniden dene/yanıt fence'i artırır. Her yazma öncesi `check_fence` + yetki yeniden kontrolü. İş başına yeni kimlik **oluşturma** — tek `metis-worker` kimliği + `requester_id` üzerinden yetki türetimi.
- Öncelik: mentor ve kullanıcı etkileşimli işler > hazırlık > bakım > benchmark. Benchmark ayrı slotta, hazırlığı bloke etmez.
- Bütçe: adım ≤20, kaynak ≤10, kaynak başına ≤30k karakter, token rezervi muhafazakâr; aşımda `budget_exceeded` + kısmi sonuç korunur.
- **Faz 5 pipeline (sabit adımlar, araçsız):**
  1. `extract` — iddialar `{subject, attribute, value, condition, quote}`, açık kararlar, kapsam soruları; her alıntı kaynakta birebir.
  2. `retrieve` — deterministik top-3 aday, kendi kanıtı hariç.
  3. `compare` — `no_change | addition | update | conflict_candidate | supersede`.
  4. `judge` — aynı subject+attribute, farklı değer çiftleri; kapsamlar ayrıksa model çağrılmaz.
  5. `relate` — yalnız gerçekten yeni kavramsal ilişki (kaynağın kendisi ilişki değildir).
  6. Kapsam sorusu varsa `awaiting_input` → kullanıcı yanıtı → yeniden kuyruk. Engel yoksa taslak `change_set` (origin=metis). **Çıktı her zaman insan incelemesine giden taslaktır.**
- `refine_draft` — ≤5 sayfalık taslağı paragraf→iddia indeksiyle yeniden yazar; tüm iddialar kapsanmalı; kanıt ID'leri ve kapsam korunur.
- **Faz 11 (opsiyonel, değerlendirmeye bağlı):** dar tool-call döngüsü — yalnız salt-okunur araçlar (`search_published`, `read_source_span`, `list_scope_values`), adım limiti, her araç sonucu veri olarak işaretli. Sabit pipeline'ın yetmediği ölçülmeden açılmaz.

### 5.8 Model istemcisi
- OpenAI uyumlu `POST {base_url}/chat/completions`; çift `/v1` hatası engellenir; `temperature 0`.
- Transport profili probe'dan: `json_schema` destekleniyorsa strict; değilse `json_object` + şema system mesajında; düşünme modu kapatılabiliyorsa kapalı. Desteklenmeyen parametre **sessizce düşürülmez**, profil kaydedilir.
- Toplam süre `asyncio.timeout` ile sınırlı, cevap gövdesi 1 MiB cap, sınırlı onarım denemesi (0-2), 429/5xx'te jitter'lı sınırlı retry.
- Her çağrı `model_calls` satırı. Cache anahtarı: prompt sürümü + mesajlar + şema + model/config/provider/URL/secret_version + max_tokens. Cache'ten gelen çıktı da yeniden doğrulanır. Benchmark ve probe cache kullanmaz.
- Sağlayıcı başına eşzamanlılık semaforu (DB tabanlı).
- Yeterlilik fingerprint'i: model + config + prompt hash + transport profili. Biri değişince yeterlilik düşer.
- Hedef model: şirket içi **DeepSeek V4 Flash 0731** (OpenAI uyumlu endpoint). v1'de doğrulanan DeepSeek ayarları (json_object, thinking kapalı, Türkçe gerekçe zorunluluğu) prompt/profile olarak taşınır.

### 5.9 Sunucu dağıtımı
Hedef: şirket içi, internetsiz bir sunucuda çok kullanıcılı çalışma. Varsayılan **Windows Server**; Linux verilirse systemd birimleri ikincil hedef (Açık soru 1).

**Süreçler**
- `metis-api`: FastAPI (uvicorn, birden çok worker süreci), statik frontend'i de sunar.
- `metis-worker`: iş kuyruğu (bir veya daha fazla süreç; lease/fence sayesinde güvenle çoğaltılabilir).
- PostgreSQL 16+: şirketin yönettiği bir sunucu ya da aynı makinede native Windows servisi (Açık soru 3).
- Windows'ta servis kaydı: WinSW (paketle gelen tek EXE, XML tanımı) — kurulum betiği servisleri adanmış bir servis hesabıyla kaydeder, otomatik yeniden başlatma açık.

**TLS ve erişim**
- HTTPS zorunlu. İki seçenek (Açık soru 4): (a) IIS/ARR ters vekil TLS'i sonlandırır, METIS `127.0.0.1`'de dinler; (b) uvicorn şirket sertifikasıyla doğrudan TLS. Varsayılan (a).
- `METIS_PUBLIC_URL` tek kaynak: Origin allowlist, cookie, CSRF, mutlak bağlantılar buradan.
- Model endpoint'lerine giden çağrılar şirket CA bundle'ı ile; SSRF allowlist + ağ kontrolü v1'deki gibi.

**Gizli bilgiler**
- Master key (sağlayıcı anahtarlarını şifreleyen) dosyada, ACL'i yalnız servis hesabı + yöneticiler; yolu ortam değişkeninde. İsteğe bağlı: Windows DPAPI (makine kapsamı) ile sarılı.
- DB rolleri v1 ADR-003'teki gibi ayrı: `metis_owner` (yalnız migration), `metis_app` (çalışma zamanı, süper kullanıcı değil, BYPASSRLS değil).

**Kurulum paketi** (`deploy/build-bundle.py` → `METIS-<sürüm>-server-win64.zip`)
- Hash-kilitli wheelhouse (`pip install --no-index --require-hashes`), derlenmiş frontend, WinSW, `install-offline.ps1`, `upgrade.ps1`, `BASLA.txt`, `SHA256SUMS.txt`.
- `install-offline.ps1`: ön koşul kontrolü (Python sürümü, PG erişimi, port, disk) → venv → wheelhouse kurulumu → `metis migrate` → servis kaydı → `metis doctor` → ilk yönetici için tek kullanımlık kurulum kodu ekrana basılır.
- `upgrade.ps1`: servisleri durdur → **otomatik yedek** → yeni sürümü yan klasöre kur → migrate → başlat → `doctor`; başarısızsa önceki klasöre dön (migration öncesi yedekten).
- `metis doctor`: DB bağlantısı, migration sürümü, blob deposu bütünlüğü (örneklem), master key parmak izi, model endpoint erişimi (ayrı durum; model yokken uygulama "hazır" sayılır), disk alanı, servis durumu.

**Yedek ve geri yükleme**
- Sunucuda PG araçları var: `pg_dump -Fc` + blob deposu + master key parmak izi tek arşivde; zamanlanmış görev (varsayılan günlük, 14 gün saklama — şirket politikasıyla değiştirilebilir).
- `metis restore` yalnız boş DB'ye; geri yükleme tatbikatı komutu (`metis restore --rehearsal` geçici DB'ye yükler, doğrular, siler).

**Gözlemlenebilirlik**
- `/health/live`, `/health/ready`; yapılandırılmış JSON log (döner dosya), correlation ID; Ayarlar'da yöneticiye "Sistem durumu": kuyruk gecikmesi, süresi dolmuş lease'ler, başarısız işler, model hata oranı, disk.
- Harici telemetri yok.

**CI**
- GitHub Actions: Linux'ta lint/typecheck/pytest/Playwright; `windows-latest` üzerinde PG servisiyle pytest + kurulum paketini üretip temiz bir dizine `install-offline.ps1` ile kuran duman testi. Release'te tek ZIP asset.

### 5.10 v0.5.5 verisinin taşınması
Ürün sahibinin v0.5.5 masaüstü uygulamasındaki tüm bilgi v2 sunucusuna aktarılır.

**Girdi:** v0.5.5 başlatıcısından alınan **şifreli yedek dosyası** (ürün sahibinin uygulamada "Yedek al" ile ürettiği dosya) + yedek parolası. Bu yol seçildi çünkü bu dosya ana anahtarı da içerir; model sağlayıcı anahtarları dahil her şey taşınabilir.

**Format** (kaynak: `reference/v0.5.5/deployment/desktop/recovery.py`, `deployment/backup.py`):
- Dosya: `b"METISBK1"` (8) + salt (16) + nonce (16) + tag (16) + şifreli veri. AES-256-GCM, AAD = `METISBK1`, anahtar = `scrypt(parola, salt, n=32768, r=8, p=1, dklen=32)`.
- Açılan içerik ZIP: `snapshot.zip` + `recovery.json` (`{"format":1,"master": …}` — v0.5.5 master key'i).
- `snapshot.zip`: `manifest.json` (`format: metis-backup-v1`, `schema: 2`, `master_key_fingerprint`, `tables: {tablo: [satırlar]}`) + `blobs/xx/<sha256>`.
- v0.5.5 tabloları ve sütunları: `reference/v0.5.5/services/api/db.py`.

**Komut:** `metis import-v1 <yedek> [--dry-run]` (parola etkileşimli sorulur, komut satırına yazılmaz, loglanmaz).

**Kurallar**
- Yalnız **boş** v2 veritabanına (kullanıcı/proje yok) uygulanır; doluysa reddeder, hiçbir şey değiştirmez.
- Önce `--dry-run`: tüm dönüşümü bellekte yapar, doğrular, rapor üretir, yazmaz. `apply` tek transaction'da yazar; hata olursa hiçbir satır kalmaz. Bloblar transaction öncesi geçici dizine yazılır, commit sonrası yerine taşınır.
- Her blob SHA-256 ile doğrulanır; yedek arşivinden dosya yolu doğrudan çıkarılmaz (v1'deki path traversal koruması korunur), boyut sınırları uygulanır.
- UUID'ler korunur; v1 hash'leri `legacy_hash`'te saklanır.
- Kaynak revizyonlarının, onayların, yayınların **geçmişi** korunur; içe aktarma yeni bir onay veya yayın üretmez. Audit'e tek bir `legacy_import` olayı + rapor bağlantısı düşer.

**Eşleme (özet — ayrıntı Faz 9'da `docs/adr/v2-ADR-00x-legacy-import.md` olarak yazılacak)**
| v0.5.5 | v2 | Not |
|---|---|---|
| `identities` (human) | `users` | scrypt hash formatı (`salt:hex`, N=16384) doğrulayıcı olarak desteklenir; ilk girişte v2 parametreleriyle yeniden hash'lenir |
| `identities` (worker/bot, `worker-<id>`) | — | Aktarılmaz; `origin=metis` ve `job_id` ile ilişkilendirilir, tek `metis-worker` kimliğine bağlanır |
| `credentials` | — | Oturumlar taşınmaz, herkes yeniden giriş yapar |
| `memberships.roles` (JSON) | `project_members` (satır başına rol) | |
| `projects` | `projects` | `independent_review=false` → `review_policy=owner_review` **korunur** (pilot geçmişi); yönetici sonra değiştirebilir |
| `settings['scope-catalog:*']` | `scope_values` | Eski `platform`→`proje`, `hardware`→`kart` normalizasyonu |
| `sources` + `acl` (JSON) | `sources` + `source_acl` | |
| `source_revisions`, `evidence` | aynı adlı tablolar | Locator metni (`"PDF · sayfa 3"`) yapılandırılmış `locator`'a ayrıştırılır; ayrıştırılamayan metin `locator.raw`'da kalır |
| `pages`, `page_revisions` | aynı | `claims` JSON → `claims` + `claim_evidence`; `unknowns` aynen |
| `change_sets` (`revisions`, `bases` JSON) | `change_sets` + `change_set_items` | `deleted` durumu → `deleted_at` |
| `approvals` | `reviews` | `decision`, `policy` aynen |
| `publications.manifest` | `publications` + `publication_pages` | Aktif yayın işaretçisi korunur; `search_documents` yalnız aktif yayın için yeniden kurulur |
| `findings` | `findings` | |
| `settings['conflict-case:*']`, `['resolution-change:*']`, `['successor:*']` | `conflict_cases`, `conflict_resolutions`, `change_sets.predecessor_id` | |
| `work_items` | `jobs` (yalnız bitmiş olanlar, salt-okunur geçmiş) | Bitmemiş işler `cancelled` olarak aktarılır, raporda listelenir |
| `extracted_claims`, `open_decisions` | aynı | |
| `answers.result` (JSON) | `answers` + `answer_citations` | Eski cevaplar "v1 alıntı cevabı" olarak işaretli gösterilir |
| `providers.secret` | `providers.secret_enc` | v0.5.5 master key ile çözülür (`b64(nonce16‖tag16‖ct)`, AAD yok), v2 master key ile yeniden şifrelenir; düz metin diske/loga yazılmaz |
| `models` | `models` | Yeterlilik **taşınmaz** (prompt ve transport değişti → yeniden benchmark gerekir); model "test edilmedi" durumunda gelir |
| `benchmark_runs`, `model_calls`, `model_cache` | — | Taşınmaz (operasyonel veri; raporda sayıları yazılır) |
| `audit_events` | `audit_events` | Aynen, `detail.legacy=true` |
| `settings['maintenance-schedule:*']`, `['preparation-auto:*']` | `schedules` (tek zamanlayıcı) | İki eski ayar birleşir; çakışırsa daha seyrek olan seçilir ve raporda belirtilir |
| Diğer `settings` anahtarları | — | Raporda "aktarılmadı" listesi |

**Doğrulama raporu** (`legacy_import_runs.report` + insan okunur Markdown):
- Tablo başına kaynak/hedef satır sayısı; atlanan kayıtlar ve nedeni.
- Tüm blobların hash doğrulaması.
- Her yayının, eşleşen bir onaya (v1 hash'iyle) sahip olduğu (v1 `verify()` mantığı).
- Aktif yayındaki her sayfa v2'de açılabiliyor ve iddiaları kanıtlarına bağlı.
- Silinmiş kayıtların aktif görünümlerde görünmediği.
- Örnek 5 mentor sorusunun v2'de çalıştırılıp karar dağılımı (model tanımlıysa; değilse "atlandı").

**Test:** v1 kodu çalıştırılmadan, `reference/v0.5.5` şemasına uygun **sentetik yedek dosyaları** üreten bir fixture (tüm tablo türleri, Türkçe karakterli dosya adları, silinmiş kayıtlar, çelişki vakası, owner_review projesi). Yanlış parola, bozuk tag, eksik blob, hash uyuşmazlığı, dolu hedef DB ve path traversal denemesi testleri. **Gerçek veriyle doğrulama yalnız ürün sahibinin gerçek yedeğiyle yapılır** ve ayrı raporlanır.

---

## 6. Tasarım dili: **İz**

> Bu bölüm Claude'un tasarım yönüdür. Ürün sahibinin isteği: modern, canlı, gezinmesi keyifli, kendine özgü. Eski arayüzün mor/Inter/kart yığını görünümünden bilinçli olarak ayrılır.
>
> **Güncelleme (2026-10-17, ürün sahibinin onayı):** palet "Lehim yeşili + Turkuaz" olarak canlandırıldı. Eylem ve seçim için turkuaz **vurgu** rengi eklendi (birincil düğme, aktif menü/sekme, sayaç, bağlantı alt çizgisi, odak halkası); uyarı (`--dikkat`) altınla karışmasın diye turuncuya çekildi. Altın = kanıt kuralı aynen geçerli. Güncel değerler aşağıdaki tablolarda; tek kaynak `apps/web/src/design/tokens.css`.

### 6.1 Fikir
METIS'in asıl değeri **iz sürülebilirlik**: her bilginin bir kaynağa giden izi var. "İz" kelimesi hem Türkçe *iz/ize* (provenance) hem de devre kartındaki *bakır iz*dir (PCB trace). Ekibin dünyası kartlar, lehim maskesi, ENIG altın kaplama pedler, via'lar, datasheet'ler. Tasarım bu dünyadan **dekor değil dil** çıkarır:

- **Altın = kanıt.** Arayüzde altın renk *yalnızca* kaynağa bağlı şeyler için kullanılır: alıntı vurgusu, kaynak işaretleri, kanıt şeridi, iz çizgisi. Kullanıcı birkaç dakikada öğrenir: *altın gördüğün yerde bir kaynak var.* Bu kuralın istisnası yoktur.
- **Lehim yeşili = Metis'in zemini.** Sol navigasyon rayı koyu lehim maskesi yeşilidir — kartın kendisi. İçerik alanı sakin, ferah, soğuk-kâğıt tonudur.
- **Durumlar kendi renginde, her zaman ikon + etiketle.** Renk tek başına sinyal değildir.

### 6.2 Renk tokenları

**Açık tema**
| Token | Hex | Kullanım |
|---|---|---|
| `--zemin` | `#F4F7F6` | Sayfa arka planı (soğuk silika; krem değil) |
| `--yuzey` | `#FFFFFF` | Paneller, okuma sütunu |
| `--yuzey-gomuk` | `#E9EFED` | Girdi alanları, kod blokları, gömülü bölgeler |
| `--murekkep` | `#10201B` | Ana metin |
| `--soluk` | `#56645F` | İkincil metin (zemin üzerinde ≥4.5:1) |
| `--cizgi` | `#D6E0DC` | Kenarlıklar, ayraçlar |
| `--ray` | `#0A4038` | Sol navigasyon rayı (lehim maskesi) |
| `--ray-metin` | `#DCEFE9` | Ray üzerindeki metin |
| `--ray-nokta` | `#5EEAD4` | Aktif menü noktası/ikonu, menü sayaçları |
| `--vurgu` | `#0B8576` | Birincil düğme dolgusu, aktif sekme, sayaç, odak halkası (beyaz metinle ≥4.5:1) |
| `--vurgu-yazi` | `#0A6B60` | Vurgu renginde metin |
| `--iz` | `#A77B0A` | İz çizgileri, kanıt şeridi, via noktaları (grafik) |
| `--iz-metin` | `#7A5900` | Altın metin (beyaz üzerinde ≥5:1) |
| `--iz-zemin` | `#F7ECC4` | Alıntı vurgusu `<mark>` |

**Koyu tema**
| Token | Hex |
|---|---|
| `--zemin` | `#0B1412` |
| `--yuzey` | `#111C19` |
| `--yuzey-gomuk` | `#172622` |
| `--murekkep` | `#E6EEEB` |
| `--soluk` | `#9AABA5` |
| `--cizgi` | `#243833` |
| `--ray` | `#082A24` |
| `--ray-metin` | `#CFE7E0` |
| `--vurgu` | `#2DD4BF` (üstündeki metin `#06201B`) |
| `--iz` | `#E2BC4E` |
| `--iz-metin` | `#E8C664` |
| `--iz-zemin` | `#3B3113` |

**Durum renkleri** (açık / koyu; her biri `-zemin` soft varyantıyla)
| Durum | Anlam | Açık | Koyu | İkon |
|---|---|---|---|---|
| `--onay` | Yayımlandı, Kanıtla destekli, Güncel | `#2A7550` | `#7FCB9F` | ShieldCheck |
| `--inceleme` | İncelemede | `#2D55C8` | `#8FA8F0` | Eye |
| `--taslak` | Taslak, Henüz incelenmedi | `#5E6A64` | `#A3AFA9` | PencilLine |
| `--dikkat` | Kısmen destekli, İnceleme zamanı, Kapsamı netleştir | `#C2410C` | `#FB923C` | AlertTriangle |
| `--celiski` | Çelişki, Geri çekildi, hata | `#B3263F` | `#F08C9E` | GitFork / XCircle |

Ön kontrol (brief hazırlanırken hesaplandı): tüm metin tokenları kendi zeminlerinde ≥5.2:1, durum renkleri yüzey üzerinde ≥5.4:1 (koyu temada ≥7.2:1), grafik `--iz` açık temada 3.8:1 (grafik eşiği 3:1). Kurallar: tüm metin/zemin çiftleri iki temada WCAG AA (Playwright + axe ile test). Tema: varsayılan **sistem** (`prefers-color-scheme`), kullanıcı Sistem / Açık / Koyu seçebilir, sunucuda kullanıcı tercihi olarak saklanır. `theme-color` meta temaya göre güncellenir.

### 6.3 Tipografi
- **IBM Plex Sans** — arayüz ve okuma metni. Mühendislik mirası, datasheet hissi, güçlü Türkçe desteği, tabular rakamlar.
- **IBM Plex Mono** — kod, register/sembol adları, hash'ler. Satır içi semboller `--yuzey-gomuk` üzerinde, 0.92em.
- Ölçek (16 px taban, ~1.2 oran): `12 · 13 · 14 · 16 · 19 · 23 · 28 · 34 · 41`. **12 px altı yasak.**
- Arayüz metni 14 px; okuma metni 16 px / satır yüksekliği 1.65; okuma sütunu **68ch**.
- Başlıklar 600 ağırlık, hafif negatif harf aralığı (−0.01em, büyük boyutlarda −0.02em). Ana sayfa soru alanı 34-41 px, ağırlık 500 — sayfanın tipografik odağı odur.
- Tablolarda `font-variant-numeric: tabular-nums`.
- Kaçınılacaklar: tüm-büyük-harf etiketler, her başlığın üstünde "eyebrow" etiketi, başlıkta tek kelimeyi renklendirme, meta dizilerini " · " ile zincirleme (kapsam bilgisi chip'lerle gösterilir, nokta zinciriyle değil).

### 6.4 Biçim, boşluk, yükselti
- Boşluk ölçeği 4 px tabanlı: `4 8 12 16 24 32 48 64`.
- Köşe yarıçapı **hiyerarşiye göre**: chip/girdi 4 px · panel/kart 8 px · diyalog/çekmece 14 px · via noktası/avatar tam yuvarlak.
- Gölge neredeyse yok: derinlik `--cizgi` + yüzey farkıyla. Yalnız diyalog ve komut paleti tek bir yumuşak gölge alır.
- Kart yığını yok: listeler **satırlar** halindedir (yoğunluk ayarlanabilir: Rahat / Sıkı). Kart yalnız gerçekten ayrı bir nesne için.

### 6.5 İmza bileşenler (cesaret burada harcanır)

**1. İz paneli ve iz çizgisi** — uygulamanın akılda kalan anı.
- Bilgi sayfasında ve mentor cevabında her iddianın sonunda küçük altın bir **via işareti** vardır: `●1`.
- Tıklayınca sağda **İz paneli** açılır (≥1280 px'de içeriği itip yanına yerleşir; dar ekranda çekmece). Panel kaynağın doğru revizyonunu açar, alıntı `--iz-zemin` ile vurgulanır ve oraya kaydırılır.
- Aynı anda işaretten panele kadar **ortogonal, PCB tarzı bir altın iz** SVG ile çizilir (köşeler 45°, iki uçta via halkası), ~320 ms stroke-dashoffset animasyonu. İz, panel kapanana veya başka işaret seçilene kadar kalır; kaydırmada yeniden hesaplanır.
- Panel içeriği: kaynak türü rozeti, başlık, revizyon no ve tarih, yazar, konum (sayfa / bölüm / commit + yol + sembol), tam metin + vurgu, "Vurgulanan bölüme git", "Orijinali indir", "Yeni kaynak sürümü ekle". SHA-256 ve teknik alanlar katlı "Teknik ayrıntılar"da.
- Erişilemeyen kaynak için önizleme yok, başlık sızdırma yok.
- `prefers-reduced-motion`: iz animasyonsuz anında görünür. Klavye: işaretler sekme sırasında, Enter paneli açar, Esc kapatır ve odağı işarete döndürür.

**2. Kanıt şeridi.** Okuma sütununun sol kenarında, kanıtlı iddia içeren paragrafların yanında ince (2 px) altın dikey çizgi. Kanıtsız paragrafın yanında hiçbir şey yok. Sayfaya göz atan biri kanıt yoğunluğunu tek bakışta görür. Şeride hover → o paragrafın kaynak sayısı tooltip'i.

**3. Kavram haritası = devre kartı.** v1'de düz listeydi. v2'de:
- Düğümler bileşen ayak izi gibi: ince çerçeveli dikdörtgen, kenarlarında küçük pin çizgileri, içinde sayfa türü ikonu + başlık.
- Kenarlar `elkjs` ile ortogonal yönlendirilmiş izler; ilişki türü etiketli (Bağımlıdır, Parçasıdır, Uygular, Doğrulanır, Açıklar, Önkoşuludur, Yerine geçer). Mürekkep/gri — altın değil (altın kanıta ayrılmış).
- Varsayılan görünüm: seçili konu + 1-2 adım komşu. Bir düğüme tıklamak onu merkeze alır, yol vurgulanır, sağda kısa özet + "Sayfayı aç".
- Kapsam ve ilişki türü filtreleri; mini harita; klavyeyle düğümler arası gezinme.
- **Erişilebilir liste görünümü zorunlu** (aynı veri, tablo halinde) ve geçiş düğmesi.

**4. Komut paleti** (`Ctrl/Cmd+K`): bilgide ara, sayfaya git, "Mentora sor: …", "Yeni katkı", kapsam değiştir, tema değiştir. `/` arama alanına odaklanır. Mühendisler klavyeyle gezmeyi sever; bu, "gezinmesi keyifli" hissinin büyük kısmıdır.

**5. Logo.** İki ortogonal izden oluşan soyut bir **M**: üç via noktası, ortadaki altın. Mitolojik görsel yok. SVG, favicon dahil. Ray üstünde açık tonda.

### 6.6 Hareket
- Süreler: 120 ms (hover/odak) · 180 ms (panel, sekme) · 280-320 ms (iz çizimi, çekmece). Eğri `cubic-bezier(.2,.7,.2,1)`.
- **Tek orkestre an:** mentor cevabı doğrulandığında ilerleme adımları kapanır, cevap belirir ve iddiaların via işaretleri sırayla (40 ms aralık) altınla yanar. Başka sayfa-yükleme koreografisi yok; bölümler tek tek kayarak girmez.
- Kullanıcı eylemine cevap veren hareket serbest: panel açılması, satır genişlemesi, onaydan sonra durum chip'inin "İncelemede → Yayımlandı" geçişi.
- Skeleton'lar son düzenle aynı şekilde; parıltı animasyonu sakin.

### 6.7 Yazı sesi (mikro metin)
- **"Sen" dili**, kısa, düz fiiller, cümle düzeni büyük harf (Title Case yok).
- Bir eylem akış boyunca aynı adı taşır: düğme "Yayımla" → toast "Yayımlandı".
- Hatalar özür dilemez, ne olduğunu ve ne yapılacağını söyler: *"Model servisine ulaşılamadı. Kaynaklar aşağıda; cevabı yeniden denemek için Tekrar sor."*
- Boş ekran bir davettir: *"Bu filtrelerle yayımlanmış bilgi yok. Filtreleri temizle ya da ilk bilgiyi ekle."*
- Slogan **yalnız giriş ekranında** bir kez. Footer sloganı yok.
- Teknik terimler (fence, lease, checkpoint, prompt sürümü, fingerprint, `owner_review`) yalnız "Teknik ayrıntılar" bölümlerinde.

### 6.8 Erişilebilirlik ve kalite tabanı
- Tam klavye kullanımı, görünür odak halkası (`--murekkep` 2 px + 2 px offset), diyalog/panelde focus trap + Esc.
- Test çözünürlükleri: 1366×768, 1920×1080, 390 px mobil; yatay kaydırma yok.
- Uzun sembol, kod ve tablo stres testleri (ör. `XPAR_XAXIPCIE_0_BASEADDR` gibi 40+ karakterlik sembol taşmamalı).
- Form hataları alana bağlı, çift gönderim yok, otomatik kaydetme hatası belirgin.

---

## 7. Bilgi mimarisi ve ekranlar

### 7.1 Kabuk

```
┌──────┬──────────────────────────────────────────────────┬───────────────┐
│ RAY  │ Üst çubuk: [Proje ▾]                      [⌘K Ara] [＋ Yeni katkı] │
│ (M)  ├──────────────────────────────────────────────────┤               │
│      │                                                  │   İZ PANELİ   │
│ Ana  │                  İÇERİK                          │ (açıkken; ≥1280│
│ Bilgi│          (okuma sütunu 68ch / listeler           │  px'de içerikle│
│ Mentor│           tam genişlik)                          │  yan yana)    │
│ Harita│                                                 │               │
│ ──── │                                                  │               │
│ Kayıt│                                                  │               │
│ Görev│                                                  │               │
│ Sağlık│                                                 │               │
│ ──── │                                                  │               │
│ Lab* │                                                  │               │
│ ⚙ 👤 │                                                  │               │
└──────┴──────────────────────────────────────────────────┴───────────────┘
```
- Ray 232 px, daraltılınca 64 px (yalnız ikon + tooltip); seçim kalıcı. <760 px: ray çekmece olur, alt kısımda 4 öğelik sekme çubuğu (Ana sayfa, Bilgi, Mentor, Kayıtlar).
- Aktif öğe: turkuaz zeminli satır, solda `--ray-nokta` renginde dolu via noktası ve ikon; pasif öğeler %70 opaklık. Nav'da altın **kullanılmaz** — altın yalnız kanıta ayrılmıştır.
- Bildirim/sayı rozetleri: Kayıtlar'da "incelemeni bekleyen" sayısı, Görevler'de "yanıtını bekleyen" sayısı. Sıfırsa rozet yok.
- Proje seçici gerçek çalışır (tek proje varsa yalnız adı görünür). **Güncelleme (2026-10-17):** üst çubukta kapsam gösterilmez; kapsam yalnız onu kullanan yerlerde (ana sayfa soru kutusu, Mentor, Kavram haritası) görünür ve oradan açılan pencerede seçilir.

**Navigasyon (son hali):**
- Ana sayfa `/`
- Bilgi havuzu `/bilgi`
- Mentor `/mentor`
- Kavram haritası `/harita`
- *(ayraç)*
- Kayıtlar `/kayitlar` (sekmeler: İncelemeni bekleyenler · Taslaklar · Yayımlananlar)
- Metis görevleri `/gorevler`
- Bilgi sağlığı `/saglik`
- *(ayraç, yalnız yönetici)*
- Model laboratuvarı `/lab`
- Ayarlar `/ayarlar` (Üyeler, Kapsam tanımları, Bakım planı, Sistem durumu, Dışa aktar, Görünüm)

> v1'deki "Kapsam tanımları" ayrı nav öğesiydi; v2'de Ayarlar altına taşınır ve üst çubuktaki kapsam seçiciden "Tanımları yönet" ile de açılır. **Bu bir değişikliktir — `docs/TESLIM.md`'de belirt.**

### 7.2 Ana sayfa
```
┌─────────────────────────────────────────────────────────────┐
│  Ne öğrenmek istiyorsun?                                    │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ PCIe link training neden Gen1'de kalıyor?            ⏎│ │
│  └───────────────────────────────────────────────────────┘ │
│  Kapsam: [Kart: VPK120 ×] [＋]     Model: [DeepSeek V4 ▾]   │
├──────────────────────────────┬──────────────────────────────┤
│ Kaldığın yerden              │ Seni bekleyenler             │
│  satır · satır · satır       │  2 inceleme · 1 görev sorusu │
│                              │                              │
│ Yeni yayımlananlar           │ Bilgi sağlığı (yalnız açık   │
│  satır · satır · satır       │  bulgu varsa, tek satır)     │
└──────────────────────────────┴──────────────────────────────┘
```
- Pazarlama hero'su, dekoratif yörünge sanatı, slogan yok. Soru alanı sayfanın tipografik odağı.
- İlk açılış (boş havuz): "İlk bilgini ekle" — 3 adımlı rehber (Kaynağı ekle → Taslağı hazırla → İncele ve yayımla) + "Kurgusal çalışma alanını aç" (yalnız geliştirme profilinde). Asla boş dashboard.
- "Seni bekleyenler" sıfırsa bölüm hiç görünmez.

### 7.3 Bilgi havuzu `/bilgi`
- Varsayılan: domain listesi (sayfa sayısı, son güncelleme). Domain seçilince satır listesi.
- Filtreler (YATT, Kart, Proje, tür, güncellik, metin) **URL'de**; ayrıca kullanıcı başına son filtre sunucuda hatırlanır. "Filtreleri temizle".
- Satır: tür ikonu, başlık, tek satır özet, kapsam chip'leri, güncellik durumu, yayın tarihi (gün.ay.yıl ss:dd), kanıt sayısı (altın via + sayı).
- Satırda "…" menüsü: Aç · Mentora sor · Düzeltme öner · Sil.

### 7.4 Bilgi sayfası `/bilgi/:id`
```
┌───────────────────────────────────────────┬────────────┐
│ [Bileşen] [Güncel]                        │ İçindekiler│
│ AXI PCIe kesme yönetimi                   │ (tıklanır, │
│ Tek paragraf özet…                        │  scroll-spy)│
│ [Domain: Gömülü] [Kart: VPK120] [Proje: X]│            │
│ Onaylayan: Barış · 12.09.2026 14:20       │ Kaynaklar  │
│                                           │  ● Not 1   │
│ ┃ Paragraf… kanıtlı iddia ●1             │  ● PDF s.4 │
│ ┃ Paragraf… ●2 ●3                        │            │
│   Paragraf (kanıtsız, şerit yok)          │ Bu konuyu  │
│                                           │ sor  →     │
│ Doğrulanabilir iddialar (numaralı)        │            │
│ Bildiklerimizin sınırı                    │            │
│ İlgili bilgiler                           │            │
├───────────────────────────────────────────┴────────────┤
│ [Bu konuyu sor] [Düzeltme öner] [Geçmiş] [⋯ Geri çek/Sil]│
└────────────────────────────────────────────────────────┘
```
- ●n işareti → İz paneli + iz çizgisi.
- **Açıklayıcı görseller (2026-10-18, ürün sahibinin isteği):** gövdede kendi satırında `{{görsel N}}` ile metnin içinde, açıklamasıyla gösterilir; tıklayınca büyür. Görsel bir görsel kaynağın (PNG/JPEG) belirli revizyonudur; revizyona değişmez satır olarak bağlanır (`page_revision_figures`), onay hash'ine dahildir, kaynağına erişimi olmayan sayfayı göremez, kaynak yeni sürüm alınca sayfa "Kaynak değişti" olur. **Kanıt değildir:** altın işaret almaz, iddia desteği yine alıntılanabilir metinden gelir. Editörde "Görsel ekle": var olan görsel kaynağı seç ya da yükle + açıklama; yer tutucu imlecin olduğu yere girer. Kayıt detayında inceleyici görselleri görür; Markdown dışa aktarımında `gorseller/` altında yer alır.
- Geri çekilmiş / kaynağı değişmiş sayfada üstte açık banner (ne oldu + ne yapılabilir).
- "Geçmiş": revizyon zaman çizelgesi; iki revizyonu karşılaştırma.
- "Sorun bildir" → bulgu oluşturur.

### 7.5 Mentor `/mentor`
- Sol: soru alanı, kapsam, model, detay düzeyi (Kısa / Adım adım / Ayrıntılı — **gerçekten etkili olmalı** veya kaldırılmalı; v1'de etkisizdi).
- Cevap kartı: karar rozeti (ikon + Türkçe etiket) → kaynaklı açıklama (1-4 cümle, her cümle ●n işaretli; 5.6) → "Kaynak alıntıları" numaralı kartlar → uygulanabilir kapsam → "Bildiklerimizin sınırı" → ilgili okuma.
- Çekimser kararlarda boş durum: ne biliniyor, ne eksik, ilgili kayıtlar, "Bu soruyu kaydet / katkı iste".
- `CONFLICTING`: iki tarafın alıntısı yan yana + "Çelişkiden çözüme" akışı başlat.
- Alt: "Bu cevaptan bilgi taslağı öner" (cevabın kanıtlarını taşıyan taslak; cevap kendisi kanıt değildir).
- "Kanıt, kapsam ve üretim kaydı" katlı: model, prompt sürümü, yayın no, süreler.
- Sağ ray: "Son soruların" (kişisel; silinebilir).

### 7.6 Yeni katkı `/katki`
Tek akış, iki adım; sahte 4 adımlı stepper yok.
1. **Kaynak:** var olanı seç veya yeni (başlık, tür, sürüm/commit, dosya bırakma ≤10 MB veya uzman notu metni) + kapsam (öneri gelir, kullanıcı onaylar).
2. **Taslak:** iki yol yan yana sunulur:
   - *Metis hazırlasın* → worker işi başlar, ilerleme aynı sayfada canlı görünür; soru gelirse sayfada cevaplanır; bitince taslak açılır.
   - *Kendim yazayım* → editör (Yaz / Önizle), iddialar (her biri ayrı satır, kaynak alıntısı seçilerek bağlanır — metin seçimi → "Bu alıntıyı iddiaya bağla"), bilinen sınırlar.
- Sonuç: "Taslak kaydedildi" → Kayıtlar'daki detayına git. Kaydedilmemiş metin uyarısı. Desteklenmeyen dosya asla "başarıyla işlendi" demez.
- **Güncelleme (2026-10-17):** projede kaynak yoksa "Yeni kaynak" formu doğrudan açılır; kaynak seçilince/eklenince iki yol hemen altında sunulur (ara "Taslağa geç" adımı yok). Kaynak formunda kapsam çip + açılır seçici; sürüm/commit/dosya yolu "Ek bilgiler" altında katlı. İddia türü varsayılan "Uzman beyanı", gerekirse açılıp değiştirilir.

### 7.7 Kayıtlar `/kayitlar` ve inceleme detayı
Liste: sekmeler **İncelemeni bekleyenler · Taslaklar · Yayımlananlar**; köken filtresi (Tümü / Kişi / Metis) küçük segmented kontrol (v1'deki üç dev kart değil). Filtreler kalıcı.

Detay (yeniden düzenlenmiş):
```
┌──────────────────────────────────────────────┬──────────────────┐
│ Başlık · [Metis hazırladı] [İncelemede]      │  KARAR           │
│                                              │  Gerekçe [_____] │
│ Değişiklik özeti (3 satır: +2 iddia, 1       │  ☐ İddiaları ve  │
│  değişen, kapsam aynı)                       │    kaynak desteğini│
│                                              │    kontrol ettim │
│ ── Önceki ─────────┬── Önerilen ──────────── │  [Onayla]        │
│   iddia            │   iddia ●1 (yeni)      │  [Düzeltme iste] │
│   iddia (silindi)  │   iddia ●2 (değişti)   │  [Reddet]        │
│ (iddia bazlı diff; satır diff'i katlı)       │  (yapışkan, diff  │
│                                              │   ile yan yana)  │
│ ▸ Geçmiş ve bağlam (zaman çizelgesi, önceki  │                  │
│   yayınlar, çelişki adayları, önerilen       │                  │
│   ilişkiler) — katlı, sayı rozetli           │                  │
└──────────────────────────────────────────────┴──────────────────┘
```
- Zorunlu kontrol başarısızsa "Onayla" devre dışı ve **nedeni yazılı**.
- Taban revizyon ilerlediyse: "Bu taslak eski bir sürüme dayanıyor — yeniden temellendir".
- **Güncelleme (2026-10-17):** onay ve yayın tek düğme: "Onayla ve yayımla" (insan onayı, gerekçe kuralları, kontrol kutusu ve hash bağı aynen). Yayın tamamlanamazsa kayıt onaylı kalır ve "Yayımla" düğmesi görünür; yayınlanınca "Yayımlanan bilgiyi aç".
- `owner_review` politikasında kendi taslağını onaylama izinli ama rozetle belirtilir ("Kişisel pilot incelemesi").
- **Güncelleme (2026-10-18):** `self_publish` ("Yazar yayımlar", varsayılan) politikasında karar panelinde tek "Yayımla" düğmesi: yayın öncesi kontrol → sorun yoksa yayımlanır; varsa "Yayımlamadan önce bak" penceresi (tür: Çelişebilir / Zaten var olabilir / Aynı konuyu kapsıyor; iki tarafın ifadesi yan yana; yayındaki bilgiye bağlantı; kontrolün kural mı model mi olduğu) → "Taslağa dön" ya da "Yine de yayımla". Editörde birincil düğme de "Yayımla". Bilgi sayfasında "Yayımlayan: …". İncelemedeki kayıtta inceleyici "Düzeltme iste ya da reddet" katlı bölümünü kullanabilir.
- Silme her aşamada: onay diyaloğu → "Silindi · Geri al" toast'u (8 sn).

### 7.8 Metis görevleri `/gorevler`
- İki görev türü kartı: "Taslağı düzenle ve karşılaştır", "Bilgi havuzunu denetle". Model seçimi açık (sessiz seçim yok).
- **Güncelleme (2026-10-17):** "Bilgi havuzunu denetle" kartı kaldırıldı; aynı tarama Bilgi sağlığındaki "Şimdi denetle" ile (isteğe bağlı model) başlatılır.
- Görev satırı: durum (Sırada / Çalışıyor / Yanıtını bekliyor / Tamamlandı / Hata), başlangıç saat:dakika, sonuç özeti tek cümle.
- Detay: **önce sonuç** ("2 yeni iddia, 1 çelişki adayı bulundu → Taslağı incele"), sonra Metis'in soruları ve cevap alanı, en altta katlı "Teknik ayrıntılar" (adımlar, model çağrıları, bütçe, ham çıktı).
- Polling yerine SSE.

### 7.9 Bilgi sağlığı `/saglik`
- Tek kavram: **bulgu**. Türler: Çelişki · Kaynak değişti · İnceleme zamanı · Kırık referans · Sahipsiz sayfa. (v1'deki "güncellik kontrolü / lint / Metis incelemesi / bulgu" karmaşası tek listede toplanır.)
- Görünümler: liste (varsayılan) ve türe göre gruplama. Sekmeler: Açık · Çözülen.
- Bulgu eylemleri: "Düzeltme taslağı hazırla" · "Bilgiyi geri çek" · "Gerekçeyle kapat". Toplu kapatma yok.
- "Şimdi denetle" düğmesi + tek bakım planı (Ayarlar'da).
- Çelişki çözümü: seçenekler (korunacak / geri çekilecek), iki tarafın kanıtı, gerekçe + onay kutusu → normal inceleme akışına giden değişiklik seti.

### 7.10 Model laboratuvarı `/lab` (yönetici)
- **Sağlayıcılar**: ad, base URL, "Anahtar tanımlı · 03.10.2026" + Değiştir. Ekleme 3 alan: base URL, anahtar, model ID'leri (liste yapıştırılabilir).
- **Modeller tablosu** (en fazla 6 sütun): Seç ☐ · Model · Bağlantı (probe özet rozeti) · Ortak benchmark (geçti/kaldı, n, kritik hata) · Gecikme p50/p95 (n<30 ise "yetersiz örnek") · ⋯ (Test et, Sonucu aç, Sonucu temizle).
- Üstte: "Tümünü seç", "Seçilenleri test et", "Benchmark çalıştır", "Tüm sonuçları temizle". Seçim **asla** otomatik değil.
- "En iyi model" rozeti yok; yerine görev bazlı ifade: "Kaynaklı kısa cevap için uygun".
- Benchmark geçmişi, karşılaştırma (kalite vs gecikme dağılımı grafiği).
- Temizlenen sonuçlar sunucuda gizli işaretlenir, polling ile geri gelmez.

### 7.11 Ayarlar `/ayarlar`
Üyeler ve roller (Okur / Katkı sahibi / İnceleyici / Bilgi sorumlusu; Yönetici ayrı) · İnceleme politikası · Kapsam tanımları (4 boyut, ekle/sil) · Bakım planı (**tek** zamanlayıcı) · Sistem durumu (servisler, kuyruk, son yedek, disk, model endpoint'leri; yedek/geri yükleme komut satırından — UI yalnız durumu gösterir) · v0.5.5 aktarım raporu (varsa) · Dışa aktar (gerçek Markdown ZIP: her sayfa `.md` + `index.md` + kaynak listesi) · Görünüm (tema, yoğunluk).

### 7.12 Giriş / kurulum
- İlk yönetici: kurulum betiğinin ekrana bastığı **tek kullanımlık kurulum kodu** ile `/kurulum` açılır (sunucuda "yalnız localhost" yeterli değil); kod kullanılınca ve 24 saat sonra geçersiz. Alternatif: `metis admin create`.
- Kurulum ekranı: kurulum kodu, ad, kullanıcı adı, parola (≥12), sonra iki yol: "Boş başla" (ilk proje adı) veya "v0.5.5 yedeğinden aktar" (aktarım komutunun nasıl çalıştırılacağını gösterir ve tamamlandığında raporu açar).
- Yönetici kullanıcıları Ayarlar > Üyeler'den ekler, geçici parola verir; kullanıcı ilk girişte parolasını değiştirir.
- Sol yarıda logo + slogan (tek yer), ince altın iz motifi; sağda form. Sade.

---

## 8. Türkçe terim sözlüğü (UI'da tutarlı kullanılacak)

| Kavram | UI terimi |
|---|---|
| Knowledge base | Bilgi havuzu |
| Published page | Bilgi (sayfa) |
| Source / basis | Kaynak / Dayanak |
| Evidence | Kanıt |
| Quote | Kaynak alıntısı |
| Claim | İddia ("Doğrulanabilir iddialar") |
| Unknowns | Bildiklerimizin sınırı |
| Contribution | Katkı ("Yeni katkı") |
| Draft | Taslak |
| Change set | Kayıt |
| Review | İnceleme · Onayla / Düzeltme iste / Reddet |
| Publish | Yayımla → Yayımlandı |
| Withdraw | Geri çek → Geri çekildi |
| Revision | Revizyon ("Geçmiş") |
| Scope | Kapsam · Domain / YATT / Kart / Proje · Bağımsız / Belirlenmemiş |
| Finding | Bulgu |
| Conflict | Çelişki ("Çelişkiden çözüme") |
| Worker / AI | Metis ("Metis hazırladı") vs "Kişi oluşturdu" |
| Job | Görev |
| Demo | Kurgusal çalışma alanı |
| Roles | Okur, Katkı sahibi, İnceleyici, Bilgi sorumlusu, Yönetici |
| Page kinds | Kavram, Bileşen, Prosedür, Tasarım kararı, Problem incelemesi, Doğrulama, Yapılandırılmış tablo, Öğrenme yolu |
| Freshness | Güncel / İnceleme zamanı / Kaynak değişti / Henüz incelenmedi |

---

## 9. v1'den taşınacak varlıklar

Okuma: `reference/v0.5.5/<yol>` (Faz 0 öncesinde bu repoya kopyalandı; içerik `reference/v0.5.5/README.md`'de listeli). **Kopyalama değil, uyarlama.**

| Varlık | Yol (v0.5.5) | Ne yapılacak |
|---|---|---|
| Ürün şartnamesi | `docs/METIS_Urun_Mimari_Codex_Hermes_Sartnamesi.md` | Hermes bölümleri (§1.2, §21, curator prompt, Hermes görev merkezi) hariç ürün gereksinimi olarak oku |
| Evidence prompt v4 | `services/api/evidence_prompt.py` | Karar prosedürü sırası aynen korunarak `llm/prompts/evidence-explain-v1.md`'nin temeli olur (5.6) |
| Yedek formatı | `deployment/backup.py`, `deployment/desktop/recovery.py` | İçe aktarıcının okuyacağı format (5.10) |
| Answer validator | `services/api/gateway.py` → `validate_answer` | Saf fonksiyon olarak yeniden yaz + birim testleri |
| Kaynak seçimi prompt'u | `services/api/source_selection.py` | Taşı |
| Worker prompt'ları | `services/worker/preparation.py` (`extract-claims-v2`, `page-diff-v4`, `claim-conflict-v3`, `relation-v3`), `draft_refinement.py` | Taşı; nötr `kayit_a/kayit_b` çerçevesini koru |
| DeepSeek transport bilgisi | `services/api/model_transport.py` | Probe tabanlı profile dönüştür |
| Değerlendirme vakaları | `tests/evidence_prompt_*.json`, `tests/deepseek_complex_cases.json`, `tests/deepseek_holdout_cases.json` | `evals/` altına; mock ve canlı mod |
| Kapsam semantiği | `services/api/scopes.py` | Saf fonksiyon + property testleri |
| Sunucu kurulum bilgisi | `deployment/windows/install-offline.ps1`, `deployment/linux/*.service`, `scripts/build-offline.py`, `docs/INSTALL-OFFLINE.md`, `docs/OPERATIONS.md`, `docs/architecture/ADR-003.md` | v1'in çevrimdışı wheelhouse ve ayrı DB rolleri yaklaşımı temel alınır |
| Masaüstü sertleştirme dersleri | `docs/architecture/ADR-006.md` | Masaüstü paket yok, ama dersler (HTTPX toplam zaman aşımı, ilk açılış yarışı, Unicode yollar) sunucuda da geçerli |
| Domain pack | `domain-packs/embedded-software/manifest.json` | Taşı (sayfa türleri, ilişki türleri, terminoloji) |
| Karar geçmişi | `docs/PROGRESS.md`, `docs/architecture/ADR-00*.md` | Bağlam için oku |

---

## 10. Yol haritası (fazlar ve kabul ölçütleri)

Her faz: kod + test + `PROGRESS.md` güncellemesi + commit. Bir faz kabul ölçütleri geçmeden sonrakine geçilmez. Test edilmeyen hiçbir şey "tamam" sayılmaz.

### Faz 0 — İskelet ve tasarım vitrini
- Repo yapısı, `CLAUDE.md`, lint/format/typecheck, Alembic, pytest + PG test fixture'ı, Playwright.
- `tokens.css` (iki tema), fontlar (Türkçe glif kontrolü), primitive bileşenler: Button, IconButton, Chip, StatusBadge, Input, Textarea, Select, Tabs, Segmented, Dialog, Drawer, Toast (Geri al destekli), Tooltip, Skeleton, EmptyState, Row/List, Kbd.
- Kabuk: ray (daraltılabilir), üst çubuk, komut paleti, tema seçici, mobil sekme çubuğu.
- **İz prototipi:** sahte bir bilgi sayfasında via işareti → İz paneli → animasyonlu iz çizgisi; kanıt şeridi.
- `/_vitrin` (yalnız geliştirme): tüm tokenlar, tipografi ölçeği, bileşenler, durum rozetleri, iki tema yan yana.
- **Kabul:** vitrin iki temada axe AA temiz; 1366/1920/390 ekran görüntüleri `docs/design/`'da; iz çizgisi klavye ve reduced-motion ile çalışıyor. (Onay kapısı yok — Bölüm 0.)

### Faz 1 — Kimlik, proje, kapsam, kaynak
- Kurulum, giriş/çıkış, oturum, CSRF, roller, üyeler, kapsam kataloğu.
- Kaynak oluşturma, dosya yükleme (allowlist + magic byte + 10 MB), revizyonlar (`expected_revision` → 409), PDF çıkarımı sandbox'ta, kanıt satırları, bloblar SHA-256.
- **Kabul:** pytest ile yetki matrisi (rol × uç nokta), immutability trigger testi, PDF zaman/bellek limiti testi, e2e: kurulum → giriş → kaynak ekle → İz panelinde aç.

### Faz 2 — Katkı, inceleme, yayın
- Taslak (elle), iddia ↔ alıntı bağlama, değişiklik seti, iddia bazlı diff, inceleme (hash'e bağlı), yayın (atomik), geri çekme, soft delete + geri al.
- **Kabul:** onaydan sonra içerik değişirse yayın reddedilir; eşzamanlı düzenlemede 409; yayın ortasında hata → eski yayın aktif kalır (fault-injection testi); e2e tam akış.

### Faz 3 — Bilgi havuzu, bilgi sayfası, arama
- Domain/liste görünümleri, URL filtreleri, bilgi sayfası (kanıt şeridi, İz paneli, TOC scroll-spy, geçmiş), arama (FTS simple+turkish, sembol, alias), komut paleti araması.
- **Kabul:** Türkçe çekim ("kesmeler" → "kesme"), birebir sembol ve TR↔EN alias aramaları testte geçiyor; erişilemeyen sayfa arama sonucunda ve ilişkilerde sızmıyor.

### Faz 4 — Model gateway ve kaynaklı mentor
- Sağlayıcı/model ekleme (şifreli anahtar), probe (bağlantı, auth, JSON, şema desteği), transport profili, `model_calls` logu, cache.
- Mentor hattı (5.6), 8 karar durumu, iz işaretli cevap, çelişki gösterimi, "cevaptan taslak öner".
- **Kabul:** `evals/` vakaları mock modelde %100; canlı modelde ayrı rapor (sayı/payda/n ile); `RETRIEVAL_UNAVAILABLE` ≠ `NO_EVIDENCE` testi; yetki iptali model çağrısı sırasında → `403`/cevap kaydedilmez testi; sessiz fallback olmadığı testi.

### Faz 5 — Metis worker
- Job kuyruğu (lease/fence/attempt/öncelik), SSE, `extract → retrieve → compare → judge → relate` pipeline'ı, `awaiting_input`, `refine_draft`, "Bilgi havuzunu denetle".
- Yeni katkı ekranında "Metis hazırlasın" akışı.
- **Kabul:** worker öldürülünce lease dolar ve iş devam eder; iptal fence'i artırır ve eski worker yazamaz; aynı kaynak iki kez → idempotent tek taslak; bütçe aşımı kısmi sonucu korur; çıktı her zaman `draft`/`in_review`, asla `published`.

### Faz 6 — Bilgi sağlığı ve çelişki çözümü
- Bulgular, kaynak değişimi → `dependency_changed`, inceleme zamanı taraması, tek bakım planı, çelişki çözüm akışı.
- **Kabul:** kaynak yeni revizyon alınca bağlı sayfalar işaretlenir ve mentor onları kullanmaz; çelişki çözümü normal inceleme akışından geçmeden yayımlanamaz.

### Faz 7 — Kavram haritası
- İlişki önerme (kaynaklı, incelemeli), devre kartı görünümü (xyflow + elk), liste görünümü, filtreler, klavye gezinmesi.
- **Kabul:** 200 düğümde akıcı (60 fps hedefi, ölçülmüş); liste görünümü axe temiz; erişilemeyen düğüm görünmüyor.

### Faz 8 — Model laboratuvarı
- Ortak benchmark (v1'in 6 vakalık seti + `evals/`'tan seçilen vakalar), sonuç geçmişi, sunucuda kalıcı temizleme, basit deterministik routing (kalite kapısı → gecikme), circuit breaker.
- **Kabul:** kritik hata (uydurma sayı, sahte kaynak, kapsam ihlali) olan model ortalamadan bağımsız elenir; n<30 için p95 "yetersiz örnek".

### Faz 9 — v0.5.5 verisinin taşınması
- `metis import-v1` (5.10): şifre çözme, dry-run, eşleme, tek transaction, doğrulama raporu, aktarım ADR'si.
- Sentetik v0.5.5 yedek fixture'ı ve hata vakası testleri.
- **Kabul:** sentetik yedek dry-run ve apply ile birebir aynı raporu veriyor; tüm hata vakaları "hiçbir şey değiştirilmedi" ile sonlanıyor; aktarılan yayımlanmış sayfalar v2'de açılıyor, ●n işaretleri doğru kaynağa gidiyor; sağlayıcı anahtarı yeniden şifrelenmiş ve düz metin hiçbir dosya/logda yok. Ürün sahibinin gerçek yedeğiyle tatbikat ayrı raporlanır.

### Faz 10 — Sunucu kurulum paketi
- `build-bundle.py`, `install-offline.ps1`, `upgrade.ps1`, WinSW servisleri, `metis doctor`, zamanlanmış yedek, restore tatbikatı, TLS/vekil yapılandırma rehberi (`docs/KURULUM.md`, Türkçe, adım adım), GitHub Actions Windows duman testi, tek ZIP release.
- **Kabul:** internetsiz temiz bir Windows ortamında (CI runner'da ağ kapalı adım) ZIP'ten kurulum → servisler ayakta → tarayıcıdan giriş → yeniden başlatma sonrası veri kalıcı → yükseltme betiği önceki sürümden geçiş yapıyor → yedek → boş DB'ye geri yükleme turu geçiyor. Gerçek şirket sunucusunda doğrulama ayrı raporlanır.

### Faz 11 (opsiyonel) — Dar tool-call döngüsü
Yalnız Faz 5 pipeline'ının yetmediği somut vakalarla gösterilirse (5.7).

### Teslim (tüm fazlardan sonra)
`docs/TESLIM.md` (Türkçe, ürün sahibinin okuyacağı ilk dosya):
- Ürünü bu ortamda / kendi bilgisayarında **çalıştırma** adımları (geliştirme modu: PG + API + worker + web, kurgusal çalışma alanı ile) ve sunucu kurulum paketinin nerede olduğu.
- Ana ekranların iki temada ekran görüntüleri (`docs/design/final/`): ana sayfa, bilgi havuzu, bilgi sayfası + İz paneli, mentor cevabı, yeni katkı, inceleme, görevler, bilgi sağlığı, kavram haritası, model laboratuvarı, ayarlar, 390 px mobil.
- Faz faz yapılanlar; her kabul ölçütü için **doğrulandı (nasıl: mock / izole DB / tarayıcı / canlı model)** veya **doğrulanmadı (neden)**.
- Uygulanan altyapı varsayılanları (Bölüm 11) ve brief'ten bilinçli sapmalar.
- Ürün sahibinin yapması gerekenler: gerçek v0.5.5 yedeğini aktarma tatbikatı, şirket sunucusunda kurulum, şirket model endpoint'ini ekleyip benchmark.
- Bilinen sınırlar ve önerilen sonraki adımlar (kısa).

---

## 11. Altyapı varsayılanları (sorma — varsayılanla ilerle)

Ürün kararları verildi (en üstteki kutu). Kalanlar şirket altyapısıyla ilgili; ürün sahibi kesintisiz çalışma istediği için **sorulmaz**, aşağıdaki varsayılanlar uygulanır ve hepsi yapılandırılabilir bırakılır. Seçimler `docs/PROGRESS.md` ve `docs/TESLIM.md`'de listelenir.

**1. Sunucu işletim sistemi.** Windows Server *(varsayılan)* / şirket Linux sunucusu.

**2. Kimlik doğrulama.** Yerel hesaplar *(varsayılan, v2 ilk sürüm)* / şirket Active Directory (LDAP) ile giriş — gerekiyorsa sunucu adı, bağlama yöntemi ve grup→rol eşlemesi sonradan öğrenilir; kod `AuthProvider` arayüzüyle hazır olur.

**3. PostgreSQL.** Aynı sunucuda METIS'e ayrılmış native PG servisi *(varsayılan; kurulum betiği EDB çevrimdışı kurucusunu çalıştırma talimatı verir, kendisi kurmaz)* / şirketin yönettiği mevcut PG sunucusu.

**4. TLS.** IIS/ARR ters vekil + şirket sertifikası *(varsayılan)* / uvicorn doğrudan şirket sertifikasıyla.

**5. İlk kullanıcı sayısı ve ekip.** Tahmini eşzamanlı kullanıcı (worker/uvicorn süreç sayısı varsayılanlarını belirler). Varsayılan: 25 kullanıcı, 2 API süreci, 1 worker.


---

## 12. Kapsam dışı (v2'de yapılmayacak)
Hermes veya herhangi bir harici ajan entegrasyonu · tek kullanıcılı masaüstü EXE / gömülü PostgreSQL paketi · Docker/WSL · MCP sunucusu · LLM'in kendi kendini onaylaması · otomatik internet araştırması · harici telemetri/analitik/crash reporter · graf veritabanı · Kubernetes/mikroservis · ince ayar (fine-tuning) · donanım sürme · v1'in projeye özel model yeterliliği · yazılım sürümü/yapılandırma kapsam boyutları.

---

## 13. Bilinen doğrulanmamış alanlar (dürüstlük notu)
v1'de de doğrulanmamıştı; v2'de de **ayrıca** doğrulanana kadar "çalışıyor" denmez:
- Gerçek şirket sunucusu, şirket antivirüs/uygulama beyaz liste politikası, şirket model endpoint'i, şirket CA'sı ve şirket TLS sertifikası ile uçtan uca test.
- Ürün sahibinin gerçek v0.5.5 yedeğinin aktarımı (sentetik fixture ile test edilmiş olmak, gerçek veride doğrulanmış olmak demek değildir).
- Gerçek çok kullanıcılı yük.
- Canlı modelde `page-diff`, `draft-refinement` prompt'larının değerlendirmesi (v1'de hiç ölçülmedi).
- Evidence prompt değerlendirmesi: 22 vaka geliştirme setine dönüştü, taze set yalnız 4 vaka — genel doğruluk iddiası değildir. v2'de **gizli (holdout) set büyütülmeli**.
