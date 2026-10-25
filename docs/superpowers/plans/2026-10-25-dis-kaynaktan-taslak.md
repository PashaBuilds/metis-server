# Dış kaynaktan taslak (İş 1) — uygulama planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Confluence sayfasını (+ PNG/JPEG/PDF ekleri) ve GitLab issue'sunu bağlantıdan ya da aramadan seçip METIS taslağına çevirmek.

**Architecture:** Yeni `external` modülü: yönetici bağlantıları (şifreli token, izinli kapsamlar), sunucu tarafı çekme
(httpx, yönlendirmesiz, sınırlı), Confluence depolama biçimi → Markdown dönüştürücü, GitLab issue → Markdown. "Önizle"
bir `external_imports` kaydı ve kullanıcı adına ekler üretir; taslak öğesi `import_id` taşır, kayıt `external_origins`
ile sayfaya bağlanır. Arayüz: Ayarlar → Dış kaynaklar; Yeni katkı → Kaynaktan al.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, httpx (`MockTransport` testlerde), stdlib `html.parser`, React + TanStack Query.

**Spec:** `docs/superpowers/specs/2026-10-25-dis-kaynak-ve-hibrit-arama-design.md` (bölüm 3 ve 4)

## Global Constraints

- Yalnız insan; içe aktarma projede `contributor` rolü ister, bağlantı yönetimi yönetici.
- Token yanıtta, logda, audit'te yok; `encrypt_secret` (AES-GCM) ile saklanır; yanıt yalnız `secret_configured`.
- Temel adres `validate_endpoint(url, check_allowlist=False)`; `trust_env=False`, `follow_redirects=False`, toplam 30 sn,
  JSON gövdesi ≤ 8 MiB, ek ≤ `get_settings().max_upload_bytes`; ek adresi bağlantı temel adresiyle aynı köken.
- Kısıtlı Confluence sayfası (`restrictions.read` dolu) ve `confidential` GitLab issue → `EXTERNAL_RESTRICTED`.
- İzinli kapsam dışı → `EXTERNAL_SCOPE_NOT_ALLOWED`. Not > 200 000 karakter → `EXTERNAL_TOO_LARGE`.
- Ekler: yalnız PNG/JPEG/PDF (`check_upload` kategorisi `image`/`pdf`), gövdede geçenler önce, en çok 30; kalanlar
  `skipped` (`reason`: `type` | `size` | `limit` | `fetch`).
- Test verisi kurgusal; tüm kullanıcı metni `apps/web/src/i18n/tr.ts`; `any` yok; 12 px altı yazı yok.
- Hata kodları HTTP: `EXTERNAL_UNAUTHORIZED` 502, `EXTERNAL_UNREACHABLE` 502, `EXTERNAL_TLS` 502, `EXTERNAL_TIMEOUT` 504,
  `EXTERNAL_BAD_RESPONSE` 502, `EXTERNAL_NOT_FOUND` 404, `EXTERNAL_RESTRICTED` 403, `EXTERNAL_SCOPE_NOT_ALLOWED` 403,
  `EXTERNAL_TOO_LARGE` 413, `EXTERNAL_URL_UNRECOGNIZED` 422, `IMPORT_USED` 409.

## Review Focus

- Confluence adresi bağlam yolu içerir (`https://wiki.example.test/confluence/...`): adres ayrıştırma ve ek indirme bağlam yolunu korumalı.
- Aynı öğe ikinci kez: önizleme `existing_page_id` döner, yeni sayfa açılmaz; aynı `import_id` iki taslakta kullanılamaz.
- Başka kullanıcının `import_id`'si ya da başka projenin kaydı → 404 (`NOT_FOUND`), varlığı sızdırılmaz.
- Bozuk/eksik XHTML (kapanmamış etiket, bilinmeyen makro, CDATA) dönüştürücüyü düşürmez; metin kaybolmaz.
- Dış sunucu 401/404/zaman aşımı/HTML hata sayfası döner: anlamlı kod, token sızmaz, kısmi kayıt kalmaz.

---

## Dosya yapısı

- `services/metis/modules/external/__init__.py`
- `services/metis/modules/external/http.py` — `ExternalHttp` (kimlik, sınırlar, hata eşleme; `TRANSPORT` test kancası)
- `services/metis/modules/external/storage_md.py` — Confluence depolama biçimi → Markdown
- `services/metis/modules/external/confluence.py` — adres ayrıştırma, sayfa/ek çekme, arama
- `services/metis/modules/external/gitlab.py` — adres ayrıştırma, issue/not çekme, Markdown, yükleme, arama
- `services/metis/modules/external/schemas.py`, `service.py`, `router.py`
- `services/metis/modules/external/fake.py` — kurgusal Confluence + GitLab (`handle(httpx.Request) -> httpx.Response`), `metis mock-sources` komutu
- `services/metis/core/models.py` — `ExternalConnection`, `ExternalImport`, `ExternalOrigin`
- `services/metis/migrations/versions/0010_external_sources.py`
- `services/metis/modules/changes/{schemas,service}.py` — `ItemIn.import_id`, bağlama
- `services/metis/modules/knowledge/{schemas,service veya views}.py` — `PageDetailOut.origin`
- `services/metis/modules/registry.py`, `services/metis/core/errors.py` (HTTP eşlemesi), `services/metis/cli.py`
- `apps/web/src/features/settings/ExternalTab.tsx`, `SettingsPage.tsx`
- `apps/web/src/features/contribute/ImportPanel.tsx`, `ContributePage.tsx`, `NoteEditor.tsx`
- `apps/web/src/features/page/KnowledgePage.tsx` (köken satırı), `apps/web/src/i18n/tr.ts`
- `apps/web/openapi.json`, `apps/web/src/lib/api/schema.d.ts` (üretilir)
- Testler: `tests/external/test_storage_md.py`, `tests/external/test_refs.py`, `tests/api/test_external_import.py`

---

### Task 1: Şema ve modeller

**Files:** models.py, `0010_external_sources.py`

**Interfaces — Produces:**
- `ExternalConnection(id, kind: 'confluence'|'gitlab', name, base_url, secret_enc, allowed_scopes: list[str], enabled, created_by, created_at, updated_at, deleted_at)`
- `ExternalImport(id, project_id, user_id, connection_id, external_key, url, version, title, body_md, body_sha256, attachment_ids: list[str], skipped: list[dict], restricted: bool=False, used_at, created_at)`
- `ExternalOrigin(id, project_id, page_id, connection_id, external_key, url, version, imported_body_sha256, imported_at, imported_by)`; `UniqueConstraint(project_id, external_key)`, `UniqueConstraint(page_id)`.
- Check: `kind in ('confluence','gitlab')`. Grant: SELECT, INSERT, UPDATE on üç tablo (`_role()` deseni, 0009 gibi).

- [ ] Modelleri ve migration'ı yaz; `tests/conftest.py` zaten `upgrade head` yapar.
- [ ] `.venv\Scripts\python -m pytest -q tests/api/test_foundation.py` → PASS (migration uygulanır).

### Task 2: Confluence depolama biçimi → Markdown

**Files:** `storage_md.py`, `tests/external/test_storage_md.py`

**Interfaces — Produces:** `storage_to_markdown(xhtml: str) -> Converted` ; `Converted(markdown: str, images: list[str], skipped_macros: list[str])` (images = `ri:attachment ri:filename` sırasıyla, tekrarsız).

- [ ] Testler (kurgusal içerik):
  - `test_headings_paragraphs_inline`: `<h2>Bağlantı eğitimi</h2><p><strong>LTSSM</strong> <em>durum</em> <code>REG_CTRL</code></p>` → `"## Bağlantı eğitimi\n\n**LTSSM** *durum* `REG_CTRL`"`.
  - `test_nested_lists`: `<ul><li>a<ul><li>b</li></ul></li></ul><ol><li>c</li></ol>` → `"- a\n  - b\n\n1. c"`.
  - `test_table`: 2×2 `<table><tbody><tr><th>Alan</th><th>Değer</th></tr><tr><td>EN</td><td>0x1</td></tr></tbody></table>` → `"| Alan | Değer |\n| --- | --- |\n| EN | 0x1 |"`; hücredeki `|` → `\|`.
  - `test_code_macro`: `ac:structured-macro ac:name="code"` + `ac:parameter ac:name="language"`=c + `<ac:plain-text-body><![CDATA[int x = 1;]]></ac:plain-text-body>` → "```c\nint x = 1;\n```".
  - `test_panels_and_expand`: `info`/`note`/`warning` → `> **Bilgi:** …`/`> **Not:** …`/`> **Uyarı:** …`; `expand` (title param) → `**<başlık>**` + içerik.
  - `test_image_and_unknown_macro`: `<ac:image><ri:attachment ri:filename="sema.png"/></ac:image>` → `[Görsel: sema.png]`, `images == ["sema.png"]`; `toc`/`jira` → atlanır, `skipped_macros == ["toc","jira"]`.
  - `test_broken_markup_keeps_text`: kapanmamış `<p>bir<strong>iki` → çıktı "bir" ve "iki" içerir, istisna yok.
  - `test_links`: `<a href="https://x.example.test/a">metin</a>` → `[metin](https://x.example.test/a)`; `ac:link` + `ri:page ri:content-title="Diğer"` → `Diğer`.
- [ ] Çalıştır → FAIL. Uygula: `html.parser.HTMLParser` alt sınıfı (`convert_charrefs=True`), blok yığını; `unknown_decl` ile CDATA. Çıktı: art arda 3+ satır sonu → 2, kenar boşlukları kırpılır.
- [ ] `pytest tests/external/test_storage_md.py -q` → PASS. Commit.

### Task 3: HTTP istemcisi, Confluence ve GitLab erişimi + kurgusal sunucu

**Files:** `http.py`, `confluence.py`, `gitlab.py`, `fake.py`, `tests/external/test_refs.py`

**Interfaces — Produces:**
- `ExternalHttp(kind: str, base_url: str, token: str)`; `.get_json(path_or_url: str, params: dict | None = None) -> Any`; `.get_bytes(path_or_url: str, limit: int) -> bytes`; modül değişkeni `TRANSPORT: httpx.BaseTransport | None = None`. Kimlik: confluence `Authorization: Bearer <t>`, gitlab `PRIVATE-TOKEN: <t>`. Göreli yol `base_url` + yol; mutlak adres aynı köken (şema+host+port) değilse `EXTERNAL_BAD_RESPONSE`. Hata eşleme: 401/403 → `EXTERNAL_UNAUTHORIZED`, 404 → `EXTERNAL_NOT_FOUND`, diğer ≥300 → `EXTERNAL_BAD_RESPONSE`, JSON değil → `EXTERNAL_BAD_RESPONSE`, `ConnectError` → `EXTERNAL_UNREACHABLE`, `SSLError` → `EXTERNAL_TLS`, zaman aşımı → `EXTERNAL_TIMEOUT`.
- `confluence.parse_ref(base_url: str, url: str) -> ConfluenceRef(page_id: str | None, space: str | None, title: str | None)`; `confluence.fetch(http, ref) -> ConfluencePage(id, title, space, version: int, url, storage: str, restricted: bool)`; `confluence.attachments(http, page_id) -> list[RemoteFile(filename, media_type, size, download: str)]`; `confluence.search(http, spaces: list[str], q: str) -> list[SearchItem(key, title, url, container)]`; `confluence.current_user(http) -> str`.
- `gitlab.parse_ref(base_url, url) -> GitlabRef(project_path: str, iid: int)`; `gitlab.fetch(http, ref) -> GitlabIssue(project_id: int, project_path, iid, title, description, state, labels, author, created_at, updated_at, web_url, confidential, notes: list[GitlabNote(author, created_at, body)])` (system notlar atılmış, `sort=asc&order_by=created_at`, `per_page=100`, `page` döngüsü); `gitlab.issue_markdown(issue) -> str`; `gitlab.upload_refs(markdown) -> list[tuple[secret, filename]]`; `gitlab.download_upload(http, project_id, secret, filename, limit) -> bytes`; `gitlab.search(http, projects: list[str], q) -> list[SearchItem]`; `gitlab.current_user(http) -> str`.
- `fake.handle(request: httpx.Request) -> httpx.Response` — `/confluence` bağlam yolu altında Confluence, kökte `/api/v4` GitLab; geçerli token `kurgusal-token`; kurgusal alan `BSP` (sayfa 1001 PCIe notu + `sema.png` + `veri.xlsx` eki; sayfa 1002 kısıtlı), alan `GIZLI` (izinsiz kapsam testi); GitLab `ekip/bsp` issue 7 (2 yorum + 1 system not + `/uploads/abc/log.png`), issue 8 confidential.

- [ ] `test_refs.py`: `parse_ref` biçimleri — `…/confluence/pages/viewpage.action?pageId=1001`, `…/confluence/spaces/BSP/pages/1001/PCIe+Notu`, `…/confluence/display/BSP/PCIe+Notu` (space+title), başka host → `EXTERNAL_URL_UNRECOGNIZED`; GitLab `…/ekip/bsp/-/issues/7`, `…/ekip/alt/bsp/issues/12`, `…/ekip/bsp/-/merge_requests/3` → `EXTERNAL_URL_UNRECOGNIZED`. `issue_markdown` biçimi: ilk satır `**Durum:** Kapalı · **Etiketler:** pcie, sürücü · **Açan:** Kurgusal Kişi · 2026-01-05`, sonra açıklama, `## Yorumlar`, `### Kurgusal İkinci — 2026-01-06`.
- [ ] FAIL → uygula (fake dahil) → PASS. Commit.

### Task 4: Bağlantı yönetimi API'si

**Files:** `schemas.py`, `service.py`, `router.py`, registry, errors, `tests/api/test_external_import.py`

**Interfaces — Produces (HTTP, `/api/v1`):**
- `GET /external/connections` → `list[ConnectionOut]` (yönetici: tüm alanlar; katkı sahibi: yalnız etkin olanlar, `id, kind, name, allowed_scopes`) — `ConnectionOut(id, kind, name, base_url, allowed_scopes, enabled, secret_configured, updated_at)`.
- `POST /external/connections` (`ConnectionIn(kind, name, base_url, token, allowed_scopes, enabled=True)`) → 201; `PUT /external/connections/{id}` (token boşsa korunur); `DELETE …/{id}` → 204 (`deleted_at`).
- `POST /external/connections/test` (`ConnectionTestIn(kind, base_url, token, connection_id?)`) → `ConnectionTestOut(ok: bool, error: str | None, user: str | None)`; kaydetmez; `token` boş ve `connection_id` verilmişse kayıtlı token.
- `allowed_scopes`: 1–50 öğe, her biri boş değil; Confluence alan anahtarı `^[A-Za-z0-9_~-]{1,255}$`, GitLab yol `^[\w.-]+(/[\w.-]+)+$`.
- Audit: `external.connection.create|update|delete` (token yok).

- [ ] Testler: `test_admin_manages_connections_token_never_returned` (oluştur, listede `secret_configured`, yanıt metninde token yok, audit detayında token yok, contributor yönetemez 403, contributor listede yalnız etkin ve `base_url` yok); `test_connection_test_ok_and_unauthorized` (fake ile `ok=True user="kurgusal.okur"`; yanlış token `ok=False error="EXTERNAL_UNAUTHORIZED"`); `test_base_url_outside_networks_rejected` (`http://8.8.8.8` → `ADDRESS_NOT_ALLOWED`). Fake: `monkeypatch.setattr(http, "TRANSPORT", httpx.MockTransport(fake.handle))`, temel adres `http://127.0.0.1:9160/confluence` ve `http://127.0.0.1:9160`.
- [ ] FAIL → uygula → PASS. Commit.

### Task 5: Arama, önizleme ve taslağa bağlama

**Files:** service/router/schemas, `changes/schemas.py`, `changes/service.py`, knowledge schemas + detay, test dosyası

**Interfaces — Produces:**
- `GET /projects/{pid}/external/search?connection_id=&q=` → `list[SearchItem(key, title, url, container)]` (q 2–200).
- `POST /projects/{pid}/external/preview` (`PreviewIn(connection_id, url)`) → 201 `PreviewOut(import_id, kind, title, body_md, attachments: list[AttachmentOut], skipped: list[SkippedOut(name, reason, url)], origin: OriginOut(kind, url, version, connection_name), existing_page_id: uuid | None, existing_title: str | None, edited_since_import: bool)`.
- `ItemIn.import_id: uuid.UUID | None = None`. `_write_contents` not öğesinde sayfa belli olunca `external.service.bind_import(db, actor, project_id, page, import_id)`: kayıt bu kullanıcı + proje değilse `NOT_FOUND`; `used_at` doluysa `IMPORT_USED`; köken upsert (aynı `external_key` başka sayfaya bağlıysa `VALIDATION_ERROR` field `import_id`); `used_at=now`.
- `PageDetailOut.origin: OriginOut | None`.
- Önizleme sırası: bağlantı etkin mi → adres ayrıştır → kapsam izinli mi → çek → kısıtlı mı → Markdown (Confluence: `storage_to_markdown`, görseller listesi; GitLab: `issue_markdown`) → uzunluk → ekler (sıra: gövdede geçenler, sonra diğerleri; tür/boyut/sınır süzgeci; indirme hatası `fetch`) → **yetki yeniden kontrolü** (`require_member(..., ["contributor"])`) → `Attachment` satırları (uploader = kullanıcı) + `ExternalImport` → audit `external.import.preview` (key, url).
- `existing_page_id`: aynı proje + `external_key` kökeni varsa; `edited_since_import`: o sayfanın yayındaki revizyon notu sha256'sı `imported_body_sha256`'dan farklıysa.

- [ ] Testler: `test_confluence_page_to_draft` (önizle → `body_md` "## " başlıkları içerir, ek `sema.png` var, `veri.xlsx` `skipped` reason `type`; taslak `import_id` ile kaydedilir → 201; sayfa detayında `origin.kind=="confluence"` ve `version==3`; aynı `import_id` ikinci taslakta → 409 `IMPORT_USED`); `test_reimport_points_to_existing_page` (yayımla, tekrar önizle → `existing_page_id` == sayfa, `edited_since_import` False; METIS'te notu düzenleyip yayımla → True); `test_gitlab_issue_to_draft` (system not yok, iki yorum başlığı, `log.png` eki); `test_restricted_and_scope_rejected` (1002 → 403 `EXTERNAL_RESTRICTED`; issue 8 → 403; `GIZLI` alanı → 403 `EXTERNAL_SCOPE_NOT_ALLOWED`); `test_import_record_private` (başka katkı sahibi aynı `import_id` ile → 404; okur önizleyemez → 403); `test_search_lists_allowed_only` (q="PCIe" → yalnız `BSP` sonuçları); `test_remote_errors_mapped` (fake'e kapalı bağlantı: `TRANSPORT` `ConnectError` fırlatır → 502 `EXTERNAL_UNREACHABLE`, ek satırı ve import kaydı oluşmaz).
- [ ] FAIL → uygula → PASS; `pytest tests/api/test_note_drafts.py tests/api/test_attachments.py -q` (gerileme yok). Commit.

### Task 6: Arayüz

**Files:** `ExternalTab.tsx`, `SettingsPage.tsx`, `ImportPanel.tsx`, `ContributePage.tsx`, `NoteEditor.tsx`, `KnowledgePage.tsx`, `tr.ts`, openapi + `schema.d.ts`, `tests/visual/min-font.spec.ts` (yeni rota yok; ayar sekmesi mevcut rota)

**Interfaces — Consumes:** Task 4–5 uç noktaları. `NoteValues.importId?: string | null`; kaydetmede `import_id` gönderilir.

- [ ] `scripts/export_openapi.py` + `openapi-typescript` ile tipleri üret.
- [ ] Ayarlar → **Dış kaynaklar** (yalnız yönetici): liste, ekle/düzenle formu (tür, ad, adres, token — kayıtlıysa "kayıtlı; değiştirmek için yazın", izinli kapsamlar virgülle), "Bağlantıyı dene" sonucu, sil onayı.
- [ ] Yeni katkı (yalnız yeni taslakta, `search.page`/`search.change` yokken) üstte katlanır **Kaynaktan al**: bağlantı seçimi, adres alanı + "Önizle", arama kutusu + sonuç listesi (tıklayınca önizle); önizlemede başlık, kaynak satırı, ek sayısı, atlananlar listesi, Markdown önizlemesi; `existing_page_id` varsa uyarı + "Var olan bilgiyi aç" / "Güncelleme taslağı hazırla" (`/katki?page=<id>` ve önizleme değerleriyle; `edited_since_import` uyarısı); yoksa "Taslağa çevir" → editör yeni `key` ile yeniden kurulur, değerler dolu.
- [ ] Bilgi sayfasında köken satırı: "Kaynak: Confluence · sürüm 3 · 25.10.2026" + dış bağlantı (`rel="noreferrer noopener"`, yeni sekme).
- [ ] `npx tsc -p apps/web --noEmit`, `npx eslint apps/web/src`, `npm run build:web` → temiz.
- [ ] Tarayıcı: geliştirme sunucusu (`metisdev`, :8100) + `metis mock-sources --port 9160`; bağlantı ekle/dene, Confluence sayfası ve GitLab issue'sunu önizle → taslak → yayımla → bilgi sayfasında köken; tekrar alma uyarısı. Commit.

### Task 7: Sürüm 2.0.18

- [ ] Sürüm alanları (CLAUDE.md listesi; `package-lock.json` yalnız ilk 3 eşleşme), `deploy/RELEASE_NOTES.md` (gerçek Confluence/GitLab ile **denenmedi**; kurgusal sahte sunucuyla denendi), `docs/PROGRESS.md` bölümü.
- [ ] Commit + push → `scripts\release.ps1 -Derle` → kısmi yükseltme denemesi → `-Yayimla` → yayın kaydı commit'i.

---

İş 2–5 için planlar, bir önceki iş yayımlandıktan sonra aynı klasörde ayrı dosya olarak yazılır (her biri kendi başına
çalışan yazılım üretir).
