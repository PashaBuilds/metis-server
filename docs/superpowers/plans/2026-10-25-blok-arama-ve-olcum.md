# Blok düzeyinde arama ve arama ölçümü (İş 2) — uygulama planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aramayı sayfadan bloğa indirmek; Mentor'un sayfanın tüm blokları yerine ilgili blokları kullanması; model yokken ilgili
yayımlanmış bölümleri göstermek; aramayı METIS içinde ve kurgusal setle ölçmek.

**Architecture:** Önce ölçüm (kurgusal derlem + soru seti, METIS içinde soru seti ve koşu), mevcut aramanın taban çizgisi.
Sonra `search_passages` (yayındaki her iddia/blok bir satır, başlık yolu, iki tsvector) ve blok puanlarından sayfa puanı.
Mentor blok sıralamasıyla paket kurar; `MODEL_UNAVAILABLE`'da ilgili bölümler yanıta eklenir.

**Tech Stack:** PostgreSQL FTS (`simple` + `turkish`), SQLAlchemy, FastAPI, React.

**Spec:** `docs/superpowers/specs/2026-10-25-dis-kaynak-ve-hibrit-arama-design.md` (bölüm 5)

## Global Constraints

- Mentor yalnız yayımlanmış bilgiyi kullanır; kanıt her zaman notun birebir aralığı (iddia = blok).
- `NO_EVIDENCE` ≠ `RETRIEVAL_UNAVAILABLE` ≠ `MODEL_UNAVAILABLE`; model yokken gösterilen bölümler "cevap değil" etiketli.
- Erişim: okunamayan revizyonun bloğu sonuçta/ölçümde görünmez (`unreadable_revisions`).
- Gerçek soru setleri veritabanında (depoya girmez); depodaki derlem ve sorular kurgusal.
- Ölçülmemiş değer `null`/"ölçülmedi"; sahte sayı yok.
- Tüm kullanıcı metni `tr.ts`; 12 px altı yazı yok; yeni rota olursa `tests/visual/min-font.spec.ts`.

## Review Focus

- Başlıksız not (hiç `#` yok) ve yalnız başlıktan oluşan not: başlık yolu boş/kendisi, arama düşmez.
- Kapsamı uymayan sayfanın blokları Mentor'a girmez (`NEEDS_SCOPE` davranışı korunur).
- Yayından kaldırılan/geri çekilen sayfanın blokları indeksten düşer (aynı `index_pages` işlemi).
- Uzun sayfada sorunun cevabı tek bölümde: sayfa ilk 5'te ve o blok paketin içinde.
- Model yokken ilgili bölümler: okunamayan sayfanınki görünmez; kayıtlı cevap yeniden açılınca da görünür.

---

### Task 1: Ölçüm altyapısı ve taban çizgisi

**Files:** `services/metis/modules/search/evaluate.py`, `evals/retrieval/corpus.json`, `evals/retrieval/questions.json`,
`tests/api/test_search_eval.py`, models + `0011_search_passages_eval.py` (yalnız ölçüm tabloları bu adımda), router/schemas

**Interfaces — Produces:**
- `evaluate(db, user, project_id, questions: list[EvalQuestion], search_fn=search) -> EvalResult` — `EvalQuestion(id, question, expected_page_ids: list[uuid], expected_quote: str, kind: str)`; `EvalResult(metrics: dict, per_question: list[dict])`. Metrikler: `n`, `recall_at_5`, `recall_at_10`, `mrr`, `ndcg_at_10` (sayfa; ikili ilgi), `quote_at_5` (ilk 5 sonucun en iyi bloğunda beklenen alıntı; blok bilgisi yoksa `null`), tür başına aynı metrikler.
- Tablolar: `search_eval_questions(id, project_id, question, expected_page_ids uuid[], expected_quote, kind, created_by, created_at, deleted_at)`, `search_eval_runs(id, project_id, created_by, created_at, metrics jsonb, per_question jsonb, note)`.
- API (yönetici ya da proje `steward`): `GET/POST /projects/{pid}/search-eval/questions`, `DELETE …/questions/{id}`, `POST /projects/{pid}/search-eval/runs` (eşzamanlı, en çok 500 soru), `GET …/runs` (son 20).
- Kurgusal derlem: ≥ 20 sayfa (≥ 4 uzun, çok başlıklı; issue biçiminde ≥ 4), ≥ 40 soru (tanımlayıcı / kavram / nasıl / issue / TR-EN karışık).
- Test yardımcı: `tests/retrieval_kit.py: load_corpus(client, pid) -> dict[slug, page_id]` (yayımlar).

- [ ] `test_eval_metrics_math` (sabit sıralamalarla MRR/nDCG/recall hesap doğruluğu), `test_eval_api_roles` (okur 403, sorumlu 201), `test_corpus_baseline_recorded` (kurgusal setle `evaluate` çalışır, metrik anahtarları var; sayıları yazdırır) → FAIL → uygula → PASS. Taban çizgisini PROGRESS'e yaz. Commit.

### Task 2: Blok indeksi

**Files:** models + migration (aynı 0011), `search/index.py`, `search/text.py` (katlama), testler

**Interfaces — Produces:**
- `search_passages(id bigint identity, page_id, project_id, revision_id, publication_id, claim_id, ord, heading_path text, body text, symbols text[], scope jsonb, kind, tsv_simple, tsv_turkish)`; GIN (tsv_simple, tsv_turkish, symbols), btree (project_id), (page_id); grant SELECT, INSERT, UPDATE, DELETE.
- `search.text.fold(text: str) -> str` — `simple` kanalı için: `İ I ı → i`, `ğ→g ş→s ç→c ö→o ü→u` (+ büyük harfleri), sonra `casefold`. İndeks ve sorgu aynı işlev.
- `index.heading_paths(statements: list[str]) -> list[str]` — `^#{1,6} ` ile başlayan tek satırlık blok başlık yığınını günceller; yol `"A › B › C"`; başlık bloğu kendi yolunu taşır.
- `index_pages` sayfa satırıyla birlikte blokları yeniden kurar; tsv: başlık A, başlık yolu B, gövde C (`simple` katlanmış metinle).

- [ ] `test_heading_paths`, `test_fold`, `test_passages_built_on_publish_and_dropped_on_withdraw` → FAIL → uygula → PASS. Commit.

### Task 3: Blok puanlamalı arama

**Files:** `search/service.py`, `test_phase3_search.py` gerilemesi, yeni testler

**Interfaces — Produces:** `SearchHit` alanları korunur + `best_claims: list[uuid]` (en iyi 8 blok, puan sırasıyla) + `heading_path: str` (en iyi bloğun). Sayfa puanı = sembol 10 + başlık 4 + alias 3 + en iyi blok FTS (`ts_rank_cd` simple×2 + turkish×2, blok üzerinde) + ikinci blok×0.25 + bulanık sembol (pg_trgm varsa). Sayfa düzeyi `ts_rank_cd` kaldırılır. Snippet en iyi bloktan (`ts_headline`).

- [ ] `test_long_page_section_found` (uzun kurgusal sayfada tek bölümdeki cevap: sayfa ilk 3'te, `best_claims[0]` o blok), `test_ascii_query_matches_turkish` (`"saat kaynagi"` → "Saat kaynağı" sayfası) → FAIL → uygula → PASS; `test_phase3_search.py` + `test_phase4_mentor.py` yeşil. Ölçüm setinde önce/sonra rakamları PROGRESS'e. Commit.

### Task 4: Mentor paketi ve model yokken ilgili bölümler

**Files:** `mentor/service.py`, `mentor/schemas.py`, `AnswerView.tsx`, `tr.ts`, testler

**Interfaces — Produces:**
- Paket: sayfa ≤ 8 iddia → tümü; değilse `best_claims` ilk 6 + her birinin `ord±1` komşusu + önündeki en yakın başlık bloğu; toplam en çok 40 (sayfa sırasıyla doldurulur).
- `AnswerOut.related_passages: list[RelatedPassage(page_id, title, heading_path, text, claim_id)]` — yalnız karar `MODEL_UNAVAILABLE` iken, en çok 5, `Answer.detail["related_passages"]`'ta saklanır, `answer_out` okunamayanı süzer.
- Arayüz: `MODEL_UNAVAILABLE` kutusunun altında "Model yanıt vermedi. Bu bir cevap değil; sorunla ilgili yayımlanmış bölümler:" + liste (başlık › yol, metin, bilgiye bağlantı).

- [ ] `test_bundle_uses_relevant_blocks_of_long_page`, `test_model_unavailable_returns_related_passages` (model yok → 5'e kadar bölüm, okunamayan yok, GET ile aynı) → FAIL → uygula → PASS; mentor testleri yeşil. Commit.

### Task 5: Arama ölçümü arayüzü

**Files:** `LabPage.tsx` (yeni sekme "Arama ölçümü"; yönetici/sorumlu), `features/lab/SearchEval.tsx`, `tr.ts`, openapi + tipler

- [ ] Soru ekle (soru, beklenen bilgi — arama kutusuyla seç, isteğe bağlı beklenen alıntı, tür), liste/sil, "Ölçümü çalıştır", son koşu + önceki koşu yan yana (recall@5, recall@10, MRR, nDCG@10, alıntı@5, tür kırılımı), soru başına sıra. tsc/eslint/build; tarayıcıda dev yığınında deneme. Commit.

### Task 6: Sürüm 2.0.19

- [ ] Sürüm alanları, RELEASE_NOTES (önce/sonra ölçüm rakamları kurgusal setten; gerçek içerikte ölçülmedi), PROGRESS, `-Derle`, kısmi deneme, `-Yayimla`.
