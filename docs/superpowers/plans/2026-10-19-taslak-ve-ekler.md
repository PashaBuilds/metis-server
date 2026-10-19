# Taslak hazırla (not + ekler) — Uygulama planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "Yeni katkı" tek adımda not + çoklu görsel/PDF eki olur. Not, bilginin dayanağı (kaynağı) olur; eski alıntılı yazma, demo ve v0.5.5 aktarımı üründen kalkar. Sonuç 2.0.10 olarak yayımlanır.

**Architecture:**

- Taslak öğesi `note=True` taşır. Sunucu her kayıtta notu, sayfaya bağlı bir `Source(kind='note')` revizyonuna yazar ve notu deterministik bloklara böler.
- Her blok kendiliğinden bir iddia olur; kanıtı, notun birebir aralığıdır. Böylece Mentor, arama, İz, yayın öncesi kontrol ve hash'e bağlı yayın değişmeden çalışır.
- Ekler ayrı, değişmez `attachments` + `page_revision_attachments` tablolarında durur. Dosyalar içerik adresli blob deposunda tutulur; ekler hiçbir model yoluna girmez.

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic (PostgreSQL 16); React + TanStack Query/Router + TypeScript; pytest; Playwright.

**Spec:** `docs/superpowers/specs/2026-10-19-taslak-ve-ekler-design.md`

## Global Constraints

- Türkçe arayüz; tüm kullanıcı metni `apps/web/src/i18n/tr.ts`'te. `any` yasak. 12 px altı yazı yok. Altın (`--iz*`) yalnız kanıt için. İki tema.
- **Değişmez tablolar:** yeni `attachments` ve `page_revision_attachments`, `core/db.py` `IMMUTABLE_TABLES` listesine eklenir ve PG trigger'ı (`metis_immutable()`) alır. Migration `0006`; `metis_app` rolüne SELECT/INSERT yetkisi verilir.
- **Ek türleri:** yalnız `.png`, `.jpg`, `.jpeg`, `.pdf`; sihirli bayt denetimi `sources/files.py:check_upload` ile. Dosya başına `METIS_MAX_UPLOAD_BYTES`. Taslak başına en çok 30 ek.
- **Ek indirme:** `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: sandbox`; mevcut kaynak indirme ucu gibi. Erişilemeyene 404.
- **Model yolu:** eklerin içeriği hiçbir model çağrısına, aramaya ya da Mentor paketine girmez.
- **Kullanıcı verisi silinmez:** kaldırma yalnız arayüz ve kod yolu içindir; tablolar ve satırlar kalır.
- **Kurgusal veri:** testler ve tohum kurgusaldır. Gerçek ad ve şirket bilgisi yazılmaz.

## Review Focus

1. **İçeriği değişmeyen not yeniden kaydedilir** (yalnız başlık ya da ek değişir). Yeni not kaynak revizyonu açılmamalı; son revizyon ve kanıtları yeniden kullanılmalı. Bu Task 1'de test edilir.
2. **Boş ya da yalnız boşluktan oluşan not.** Taslak kaydedilebilir (iddia sıfır), ama yayın `no_claims` engeliyle durur ve arayüz bunu "Not boş" diye söyler. Task 1 (API) + Task 3 (arayüz).
3. **Başkasının yüklediği eke kimlikle başvurmak.** Sonuç 404 olmalı. Aynı sayfanın eski revizyonundaki eke başvurmak (düzenlemede ekler korunur) ise izinli. Task 2.
4. **Yayımlanmamış not kaynağı ve ekleri.** Yazar, steward ve reviewer dışındaki üyeye 404 dönmeli. Yayımlandıktan sonra tüm üyeler okuyabilmeli. Task 1 + Task 2.
5. **Not tabanlı sayfa yeniden yayımlanır.** Kendi notunun yeni revizyonu `source_changed`/`dependency_changed` bulgusu üretmemeli (bakım taraması dahil). Task 1.

---

### Task 1: Not kaynağı ve otomatik iddialar (backend)

**Files:**
- Create: `services/metis/modules/notes/__init__.py`, `services/metis/modules/notes/blocks.py`, `services/metis/modules/notes/service.py`
- Create: `services/metis/migrations/versions/0006_note_drafts_attachments.py` (bu görevde yalnız `pages.note_source_id`; Task 2 aynı dosyaya ek tablolarını ekler)
- Modify: `services/metis/core/models.py` (Page.note_source_id), `services/metis/modules/changes/schemas.py` (ItemIn.note), `services/metis/modules/changes/service.py` (`_validate_item`, `_write_contents`), `services/metis/core/access.py` (`can_read_source`, `readable_source_ids`), `services/metis/health/maintenance.py` (source_changed exclusion), `services/metis/modules/sources/service.py` (`list_sources` excludes note sources)
- Test: `tests/api/test_note_drafts.py`, `tests/notes/test_blocks.py` (+ `tests/notes/__init__.py`)

**Interfaces:**
- Produces:
  - `notes.blocks.note_blocks(text: str) -> list[tuple[int, int]]`: code-point spans, deterministic.
  - `notes.service.materialize_note(db, author: User, project_id: UUID, page: Page | None, item: ItemIn, scope: dict) -> tuple[Page, list[ClaimIn]]`.
  - `ItemIn.note: bool = False` (with `note=True`, `claims` must be empty, else `VALIDATION_ERROR`).
  - `Page.note_source_id: UUID | None`.

- [ ] **Step 1: blok testleri.**
  - `test_blocks_split_on_blank_lines`: `"A satırı.\n\nB satırı.\n"` → iki aralık; `text[s:e]` sırasıyla `"A satırı."`, `"B satırı."`.
  - `test_blocks_skip_empty_and_marks`: yalnız `"---"` ya da `"   "` olan bloklar atılır.
  - `test_blocks_long_block_split_at_sentence`: 9000 karakterlik tek blok, her parçası ≤ 8000 ve birleşince bloğun boşluksuz metnini verir.
  - `test_blocks_deterministic`: aynı girdi iki kez → aynı çıktı.
  - Bloklar baştaki ve sondaki boşluktan arındırılmış aralıklardır.
- [ ] **Step 2: Testler kırmızı:** `.venv\Scripts\python -m pytest tests/notes -q`.
- [ ] **Step 3: `note_blocks`'u yaz.** Boş satır (`\n\s*\n`) ayırıcıdır. Harf ya da rakam içermeyen bloklar atılır. 8000 karakteri aşan blok, sınırdan önceki son `. `/`? `/`! `/`\n` noktasından bölünür; yoksa 8000'den kesilir.
- [ ] **Step 4: API testleri** (`tests/api/test_note_drafts.py`, `team` fixture'ı, kurgusal metin).
  - `test_note_draft_creates_claims_from_blocks`:
    - `POST /projects/{pid}/changes`, öğe `{note: true, title, body_md: "UART hızı 115200 baud.\n\nAkış denetimi kapalı."}`.
    - Sonuç: proposed revision'da 2 claim, `statement` blokların kendisi; her claim'in kanıtı tek ve `quote == excerpt == statement`.
    - `kind == "expert_statement"`; `page.note_source_id` dolu.
    - Kaynak `kind == "note"`, `title == item.title`.
  - `test_note_resave_same_text_reuses_source_revision`: aynı gövde, farklı başlıkla `PUT` → not kaynağının `current_revision_no` artmaz.
  - `test_note_text_change_new_source_revision_without_findings`:
    - Not tabanlı sayfa yayımlanır (`/check` + `/publish-direct`).
    - Yeni taslak gövdeyi değiştirip yayımlar; kaynak revizyonu 2 olur.
    - `Finding` (source_changed) yok, `page.freshness == "current"`.
    - `health.maintenance.deterministic_scan` da bulgu üretmez.
  - `test_note_with_claims_rejected`: `note: true` + `claims` dolu → 422 `VALIDATION_ERROR`.
  - `test_empty_note_saves_but_cannot_publish`: boş gövde ile kayıt 201; `/check` + `/publish-direct` → 422 `EVIDENCE_REQUIRED`, `approve_blockers` içinde `no_claims`.
  - `test_unpublished_note_source_hidden_from_other_members`: kaynak `GET /sources/{id}` → reader için 404, yazar için 200; yayından sonra reader 200. Not kaynakları `GET /projects/{pid}/sources` listesinde görünmez.
  - `test_note_page_readable_and_mentor_bundle`: yayımlanan not sayfası reader için 200; `paragraphs` her blok için `claim_ords` taşır.
- [ ] **Step 5: Testler kırmızı.**
- [ ] **Step 6: Uygula.**
  - Migration 0006: `pages.note_source_id UUID NULL REFERENCES sources(id)` + index.
  - `materialize_note`:
    - Sayfa yoksa oluşturur (`_write_revision`'ın sayfa yaratma mantığı buraya taşınır ya da paylaşılır).
    - Not kaynağı yoksa `Source(kind='note', owner=author, title=item.title)` yaratır ve `page.note_source_id`'ye bağlar.
    - Son revizyonun `text` ve `scope`'u `body_md` ve `scope` ile aynıysa onu kullanır. Değilse `sources.service._write_revision` ile `PreparedContent(text bytes, "not.md", "text/markdown", text, "complete", TEXT_EXTRACTOR)` yazar; `mark_dependents` çağrılmaz.
    - Her blok için `Evidence` (span; mevcut `create_evidence` mantığı, erişim kontrolü olmadan iç yardımcı) üretir.
    - `ClaimIn(statement=excerpt, kind="expert_statement", evidence=[EvidenceRef(id, excerpt)])` listesi döner.
  - `_write_contents`: `item.note` ise `materialize_note` çağrılır, `item.claims` yerine geçer, sonra `_write_revision`.
  - `can_read_source`: kaynağa `Page.note_source_id` ile bağlı sayfanın `published_revision_id`'si yoksa, yalnız `owner` ya da `steward`/`reviewer` rolü okuyabilir. Aynı kural `readable_source_ids`'e de uygulanır.
  - `deterministic_scan`: `Page.note_source_id == source.id` olan sayfanın kendi not kaynağı için `source_changed` üretilmez.
- [ ] **Step 7: Yeşil:** `pytest tests/notes tests/api/test_note_drafts.py tests/api/test_phase2_review_publish.py tests/worker/test_phase6_health.py -q`.
- [ ] **Step 8: Commit:** "Not taslağı: not kaynağı ve otomatik iddialar".

### Task 2: Ekler (backend)

**Files:**
- Create: `services/metis/modules/attachments/__init__.py`, `router.py`, `service.py`, `schemas.py`
- Modify: `core/models.py` (`Attachment`, `PageRevisionAttachment`), `core/db.py` (IMMUTABLE_TABLES), migration 0006 (tablolar + trigger + grant), `changes/schemas.py` (`ItemIn.attachments: list[UUID]`, max 30), `changes/service.py` (`_validate_item` → `_validate_attachments`; `_write_revision` hash'e `attachments` yalnız doluysa; satır yazımı; `rebase` öğeyi kurarken `figures` ve `attachments`'ı taşır), `knowledge/views.py` + `knowledge/service.py` (`RevisionView.attachments`), `knowledge/export.py` (`ekler/<sayfa-id>/<ord>-<dosya>`), `ops/backup.py` (geri yüklemede `attachments.sha256` blob doğrulaması), `app.py` ya da router kaydı
- Test: `tests/api/test_attachments.py`; `tests/ops/test_phase10_ops.py` (ek blob'u yedekte)

**Interfaces:**
- Produces:
  - `POST /api/v1/projects/{pid}/attachments` (multipart `files[]`, 1–30) → `201 list[AttachmentOut{id, filename, media_type, size_bytes, is_image}]`.
  - `GET /api/v1/attachments/{id}/download` → blob.
  - `RevisionView.attachments: list[AttachmentOut]` (ord sırasıyla).
  - Model `Attachment(id, project_id, uploader_id, sha256, filename, media_type, size_bytes, created_at)`.
  - Model `PageRevisionAttachment(page_revision_id, ord, attachment_id)`; PK `(page_revision_id, ord)`.

- [ ] **Step 1: Testler** (`tests/api/test_attachments.py`):
  - `test_upload_multiple_png_pdf`: 2 PNG + 1 PDF tek istekte → 3 kayıt, sha256 doğru.
  - `test_upload_rejects_other_types`: `.docx` ya da sahte PNG → 422 (mevcut `check_upload` kodları).
  - `test_upload_limit_30`: 31 dosya → 422.
  - `test_note_draft_with_attachments_published_and_downloadable`:
    - Not + 2 ek → yayın.
    - Reader `GET /pages/{id}` → `revision.attachments` 2 öğe, sıralı.
    - `GET /attachments/{id}/download` → 200; başlıklarda `attachment`, `nosniff`, `sandbox`.
  - `test_attachment_hash_part_of_revision`: ek sırası değişince revizyon hash'i değişir; eksiz revizyon hash'i alanı içermez (eski hash'ler korunur).
  - `test_other_users_upload_cannot_be_referenced`: başka kullanıcının yükleme kimliğiyle taslak → 404.
  - `test_edit_keeps_previous_revision_attachments`: yayımlanmış sayfanın eklerini başka kullanıcı (contributor) yeni taslakta aynen kullanabilir.
  - `test_unpublished_attachment_hidden`: yayımlanmamış taslağın eki reader için 404, yükleyen için 200.
  - `test_attachments_immutable`: `page_revision_attachments` ve `attachments` UPDATE/DELETE → `METIS_IMMUTABLE`.
  - `test_attachments_never_in_mentor_or_search`: PDF eki içindeki benzersiz kelime aramada sonuç vermez.
- [ ] **Step 2: Kırmızı.**
- [ ] **Step 3: Uygula.**
  - Yükleme: `check_upload` + `put_blob`; yalnız `pdf`/`image` kategorileri.
  - Taslakta başvuru izni: `attachment.project_id == project` ve (`uploader_id == actor` ya da ek aynı sayfanın okunabilir bir revizyonunda var).
  - İndirme izni: yükleyen ya da eki içeren ve `can_read_page_revision` ile okunabilen bir revizyon var. Taslak revizyonları için de not kaynağı kuralı geçerli (Task 1).
- [ ] **Step 4: Yedek testi:** `test_backup_restore_roundtrip_into_empty_db` ek blob'u içeren veriyle yeşil; geri yükleme, ek blob'u eksikse reddeder.
- [ ] **Step 5: OpenAPI ve TS tiplerini üret:** `scripts/export_openapi.py`, `npx openapi-typescript`.
- [ ] **Step 6: Yeşil:** `pytest tests/api/test_attachments.py tests/ops -q`, ruff.
- [ ] **Step 7: Commit:** "Ekler: çoklu görsel/PDF, değişmez, revizyona bağlı".

### Task 3: Tek adımlı editör (arayüz)

**Files:**
- Create: `apps/web/src/features/contribute/NoteEditor.tsx`, `apps/web/src/features/contribute/AttachmentsField.tsx`, `apps/web/src/features/shared/Attachments.tsx` (okuma listesi)
- Modify: `features/contribute/ContributePage.tsx` (kaynak adımı ve seçim yok; `?page=`, `?change=` → NoteEditor), `features/contribute/Contribute.module.css`, `i18n/tr.ts`
- Delete: `SourceStep.tsx`, `SourceViewer.tsx`, `MetisOption.tsx`, `FigurePicker.tsx`, `DraftEditor.tsx` (NoteEditor'a dönüşür; ortak parçalar taşınır)
- Test: e2e Task 6'da

**Interfaces:**
- Consumes: Task 1 `ItemIn.note`, Task 2 `POST /projects/{pid}/attachments`, `AttachmentOut`, `RevisionView.attachments`.
- Produces: `<Attachments items={AttachmentOut[]} />` (bilgi sayfası, İz, kayıt ayrıntısı kullanır).

- [ ] **Step 1: NoteEditor.**
  - Alanlar: Başlık, Kapsam (mevcut seçici), Not (geniş textarea, Markdown), **Ekler** (çoklu seçim + sürükle-bırak; PNG/JPEG/PDF; yüklenen her dosya satırı ad + boyut + kaldır; görsellerde küçük önizleme).
  - "Diğer alanlar" katlı bölümü: özet, tür, bilinmeyenler, arama adları.
  - Düğmeler: "Taslağı kaydet" (oluştur ya da güncelle) ve "Yayımla" (kaydet → `usePublishFlow`). Kayıt gövdesi `items[0] = {note: true, attachments: [ids], …}`.
- [ ] **Step 2: Boş not.** Kayıt mümkün; "Yayımla" not boşken devre dışıdır, ipucu "Yayımlamak için not yaz.".
- [ ] **Step 3: Sayfa düzenleme.** `?page=<id>` yayımlanmış revizyonu yükler: gövde, alanlar ve ekler (önceki revizyon ek kimlikleri korunur). `?change=<id>` taslağı aynı biçimde yükler.
- [ ] **Step 4: Ekran metinleri** (`tr.ts`):
  - "Taslak hazırla"; "Not"; ipucu "Bilgiyi kendi cümlelerinle yaz; eklere metinde atıf yapabilirsin (ör. “2. görselde…”).";
  - "Ekler"; "Dosya ekle"; ipucu "Görsel (PNG, JPEG) ya da PDF; birden çok seçebilirsin. Ekler okunmaz, yalnız bilgiyle birlikte saklanır ve açılır.";
  - "Taslağı kaydet"; "Taslak kaydedildi"; "Yayımlamak için not yaz.";
  - "En çok 30 ek eklenebilir."; "Bu dosya türü eklenemez: …".
- [ ] **Step 5: typecheck, lint, build yeşil.**
- [ ] **Step 6: Tarayıcıda dene** (yerel geliştirme yığını, port 8100, kurgusal veri):
  - 2 görsel + 1 PDF'li not → kaydet → Kayıtlar'da taslak → aç → yayımla;
  - iki tema; dar ekran.
- [ ] **Step 7: Commit:** "Yeni katkı: tek adımda not + ekler".

### Task 4: Okuma tarafı — bilgi sayfası, İz, kayıtlar

**Files:**
- Modify: `features/page/KnowledgePage.tsx` + `Knowledge.module.css` (not tabanlı sayfada "İddialar" listesi gizli, altta `<Attachments>`), `design/iz/IzPanel.tsx` (kaynak `kind=note` ve sayfaya bağlıysa başlık "Uzman notu · yazan · tarih", ekler listesi, "Yeni sürüm ekle" yerine "Bilgiyi düzenle" → `/katki?page=`), `features/records/RecordDetailPage.tsx` (eklerin listesi), `knowledge/service.py` page_detail (`note_based: bool`, attachments), `sources/service.py` evidence_view (`page_id` + attachments, not kaynağıysa)
- Test: `tests/api/test_note_drafts.py` (+ `page_detail.note_based`, `evidence_view` ek listesi)

- [ ] **Step 1: API testleri.**
  - `test_page_detail_marks_note_based`: `note_based == True`, `attachments` dolu.
  - `test_evidence_view_note_source_has_page_and_attachments`.
- [ ] **Step 2: Kırmızı → uygula → yeşil.**
- [ ] **Step 3: Arayüz.** Bilgi sayfasında Ekler (görsel küçük önizleme → tıklayınca büyüyen mevcut görsel görüntüleyici; PDF → "Aç" yeni sekmede). İz panelinde ekler.
- [ ] **Step 4: typecheck, lint, build; tarayıcıda dene** (iki tema; axe temiz).
- [ ] **Step 5: Commit:** "Bilgi sayfası ve İz: not tabanlı bilgi ve ekler".

### Task 5: Eski yöntemi kaldır + bağımsız kaynakları taslağa dönüştür

**Files:**
- Delete (arayüz):
  - Kaynak ekranları ve "Yeni sürüm ekle" bağlantıları (`IzPanel`, `HealthPage`'deki kaynak yeni sürüm yönlendirmesi metne dönüşür: "Bilgiyi düzenle");
  - `features/settings` ImportTab ve sekmesi;
  - `Shell.tsx` demo bandı ve etiketi;
  - `AnswerView.tsx` "Bu cevaptan taslak oluştur" ve `/katki?answer=` yolu.
- Delete (backend):
  - `services/metis/legacy_import/` + `metis import-v1` CLI + `/legacy-import` uçları;
  - `worker/prepare.py` ve `worker/refine.py` görevleri + bunları başlatan uçlar ("Metis hazırlasın", "Taslağı düzenle"), görev listesinde yeni kayıt açılamaz (eski kayıtlar listelenir);
  - `tests/legacy_import/`, ilgili worker testleri, `evals` içindeki prepare/refine vakaları;
  - CI `pdf_extract`/`legacy_import` yol filtreleri güncellenir.
- Modify:
  - `deploy/windows/baslat.ps1` (örnek içerik sorusu ve `-Demo`/`-DemoYok` kalkar; `-DemoYok` geriye dönük sessizce kabul edilir);
  - `deploy/windows/install-offline.ps1`/`BASLA.txt`/`docs/KURULUM.md`/`docs/TESLIM.md`/`README.md` (demo ve v0.5.5 anlatımı kalkar);
  - `services/metis/cli.py` (`demo` komutu yalnız `METIS_ENV=development`'ta kalır; kurulu üründe yok);
  - `seed/demo.py` (kurgusal tohum not + ek biçimine çevrilir);
  - `.github/workflows/ci.yml` (Windows "Kurgusal çalışma alanı" adımı kalkar).
- Create:
  - `services/metis/migrations/versions/0007_standalone_sources_to_drafts.py` (veri geçişi);
  - testi `tests/api/test_standalone_source_migration.py`.

**Interfaces:**
- Consumes: Task 1 `materialize_note`, Task 2 `Attachment`.

- [ ] **Step 1: Geçiş testi.** `test_standalone_note_with_image_becomes_draft`:
  - Hiçbir sayfa revizyonunun kanıtında ya da figüründe geçmeyen, silinmemiş bir kaynak (metin + PNG, `annotation_only`) için geçiş fonksiyonu `convert_standalone_sources(db) -> int` (`notes/service.py`) şunları yapar:
    - yazarı adına `draft` durumunda bir ChangeSet ve not tabanlı sayfa üretir;
    - not = kaynak metni, ek = kaynak dosyası (görsel/PDF ise);
    - kaynağı silmez.
  - İkinci çalıştırmada 0 döner (idempotent: `audit` ya da `detail.converted_from_source` işaretiyle).
- [ ] **Step 2: Kırmızı → uygula** (migration 0007 bu fonksiyonu ORM'siz SQL ile değil, `metis migrate` sonrası çağrılan veri adımı olarak çalıştırır: `cli.cmd_migrate` sonunda `convert_standalone_sources`) **→ yeşil.**
- [ ] **Step 3: Kaldırmaları yap.** Kırılan testleri ya güncelle (yeni akış) ya da yalnız kaldırılan özelliği sınıyorsa sil. `tests/kb.py` yardımcıları alıntılı yolu iç API olarak kullanmaya devam edebilir (ürün yüzeyi değil).
- [ ] **Step 4: Tam pytest + ruff + typecheck + lint + build yeşil.**
- [ ] **Step 5: Commit:** "Eski yöntem kalktı: alıntılı yazma, Metis hazırlasın, demo, v0.5.5 aktarımı".

### Task 6: E2E, belgeler, sürüm 2.0.10

**Files:**
- Modify:
  - `tests/e2e/setup-source-iz.spec.ts` → not + 2 ek + yayın + okuyucuda Ekler ve İz;
  - `tests/e2e/figures.spec.ts` → yerine `notes-attachments.spec.ts`;
  - `tests/e2e/review-flow.spec.ts`, `mentor-flow.spec.ts` (taslak/alıntı adımları not editörüne), `helpers.ts`;
  - `docs/KURULUM.md`, `docs/PROGRESS.md`, `deploy/RELEASE_NOTES.md`, `CLAUDE.md` (gerekirse);
  - sürüm alanları 2.0.10.

- [ ] **Step 1: e2e'yi güncelle.** CI'da koşar (Linux).
- [ ] **Step 2: Belgeler + sürüm notu.**
  - "Yeni katkı → Taslak hazırla", ekler, kalkan özellikler.
  - Şema 0006–0007; mevcut bağımsız kaynaklar taslağa dönüşür.
  - Yükseltme yerelde UAC'siz denenmedi (ürün sahibinin istisnası).
- [ ] **Step 3: Commit + push; CI Linux + Windows yeşil.**
- [ ] **Step 4: `scripts\release.ps1 -Derle`; çift tıklamayla kısmi deneme** (soru ve UAC'siz yol); **yayımla** (ürün sahibinin bu sürüm için kararı: beklemeden). Notlarda istisna açıkça yazılır.
- [ ] **Step 5: Ürün sahibine haber ver** (PushNotification + mesaj).
