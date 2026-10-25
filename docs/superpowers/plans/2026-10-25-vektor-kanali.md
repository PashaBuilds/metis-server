# Vektör kanalı (İş 3) — uygulama planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Yerel CPU embedding modeliyle blok düzeyinde vektör araması; kelime aramasıyla RRF birleşimi; model yoksa METIS aynen çalışır.

**Architecture:** `onnxruntime` + `tokenizers` + `numpy` ana pakette; model dosyaları ayrı eklenti ZIP'i
(`METIS-vektor-modeli-e5-base-1.zip`). Vektörler `passage_vectors` (model + blok metni hash'i → float16). Worker eksik
vektörleri arka planda hesaplar. API süreci sorgu vektörünü hesaplar, proje matrisini bellekte tutar (sürüm sayacıyla
tazelenir), en yakın blokları bulur; sayfa sıralaması kelime sıralamasıyla RRF (k=60) birleşir; sembol isabeti üstte kalır.

**Tech Stack:** onnxruntime 1.31 (CPU), tokenizers, numpy, PostgreSQL (bytea), FastAPI, React.

**Spec:** `docs/superpowers/specs/2026-10-25-dis-kaynak-ve-hibrit-arama-design.md` (bölüm 6)

## Global Constraints

- Model: `intfloat/multilingual-e5-base` (MIT), ONNX int8 (`Xenova/multilingual-e5-base`, revizyon
  `1ec9243030a27d1a115d5c340572074c125b58b2`), 768 boyut, `query: ` / `passage: ` önekleri, ortalama havuzlama + L2.
  Seçim ölçümle (kurgusal set, yalnız vektör): small MRR 0,939 / 5,7 ms blok; base MRR 0,968 / 18,2 ms blok.
- Model yoksa ya da yüklenemezse: arama yalnız kelime kanalıyla, hata yok; `SearchOut.dense = "unavailable"`.
- Vektörler kanıt değildir; sonuç yine yayımlanmış bloklar ve okunabilirlik süzgeci.
- Ağ yok: model yalnız diskten; indirme yalnız geliştirme bilgisayarında ZIP derlerken (sabit revizyon + sha256).

## Review Focus

- Model dizini var ama dosya bozuk/eksik: API ve worker çökmez, durum "kurulu değil (neden)".
- Yeni yayım sonrası vektörü olmayan bloklar: arama kelimeyle bulur; `dense = "partial"`.
- Proje matrisi önbelleği: yayından kaldırılan sayfa vektör sonuçlarında görünmez (sürüm sayacı).
- Okunamayan revizyonun bloğu vektörle bulunsa da görünmez.
- Kapsam/tür filtresi vektörle gelen sayfaya da uygulanır.

---

### Task 1: Bağımlılıklar, kilit dosyaları, gömme modülü

**Files:** `pyproject.toml`, `deploy/locks/{win64,linux64}.lock` (`--update-lock`), `services/metis/core/config.py`
(`embedding_model_dir`: `METIS_EMBEDDING_MODEL_DIR`, varsayılan `<METIS_HOME>/models/multilingual-e5-base` varsa),
`services/metis/modules/search/embedding.py`, `tests/search/test_embedding.py`

**Interfaces — Produces:** `get_embedder() -> Embedder | None` (süreç başına bir kez, kilitli); `Embedder.model_id: str`,
`.dim: int`, `.embed(texts: list[str], kind: Literal["query","passage"]) -> np.ndarray` (float32, L2 normalize);
`embedder_status() -> dict(state: "absent"|"error"|"ready", model_id, reason)`. Model dizini: `MODEL.json`
(`{"id","dim","query_prefix","passage_prefix","max_tokens"}`), `tokenizer.json`, `onnx/model_quantized.onnx`.
Test kancası: `embedding.FACTORY` (testlerde deterministik sahte gömme).

### Task 2: Vektör saklama ve worker döngüsü

**Files:** models + `0012_passage_vectors.py` (`passage_vectors(model_id, text_sha256, vector bytea, created_at)`
PK (model_id, text_sha256); `search_state(project_id PK, version bigint)`; `search_passages.embed_sha256`),
`search/index.py` (embed metni = başlık + başlık yolu + gövde; sha256; `bump_version`), `search/vectors.py`
(`embed_missing(db, limit=64) -> int`), `worker/loop.py` (`embed_loop` iş parçacığı, 20 sn), testler.

### Task 3: Hibrit arama

**Files:** `search/vectors.py` (`ProjectMatrix` önbelleği, `dense_hits(db, project_id, qvec, k=50)`),
`search/service.py` (RRF; `SearchOut.dense`), testler (`test_dense_finds_paraphrase`, `test_symbol_still_first`,
`test_unreadable_not_leaked_by_dense`, `test_withdrawn_page_not_in_dense`), ölçüm (önce/sonra, kurgusal set + gerçek
model yerelde).

### Task 4: Eklenti ZIP'i ve durum

**Files:** `scripts/vector-model.ps1` (indir → sha256 doğrula → `MODEL.json`, lisans, `SHA256SUMS`, kurulum betiği →
ZIP), `deploy/windows/vektor-modeli-kur.ps1`, Sistem durumu + Lab'da "Vektör arama" satırı, KURULUM.md 10c.

### Task 5: Sürüm 2.0.20 (+ model ZIP'i ayrı dosya olarak aynı sürüme)
