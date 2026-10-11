# v2-ADR-001 — Temel mimari

Tarih: 2026-10-10 · Durum: kabul edildi

## Bağlam
v0.5.5 monolitik dosyalar, `settings` tablosunda gizli şema, JSON dizilerinde ilişkiler, string zaman damgaları ve
`create_all` tabanlı migration ile büyüdü (brief Bölüm 4). v2 sıfırdan, çok kullanıcılı şirket içi sunucu için yazılır.

## Karar
- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2 (senkron, psycopg 3), Pydantic 2, Alembic. Modül başına
  `router/schemas/service/repo`. Servis katmanı `AppError` fırlatır; HTTP zarfı uygulama sınırında üretilir.
- **Veri:** PostgreSQL 16+ zorunlu (testlerde de). Tüm ID'ler UUID, zamanlar `timestamptz`. İlişkiler join tabloları + FK + indeks.
  Silme `deleted_at/deleted_by`. Değişmezlik PG trigger + ORM kancası.
- **Arama:** yalnız aktif yayının `search_documents` satırları; `tsv_simple` + `tsv_turkish`, `symbols text[]` (GIN), `pg_trgm` varsa bulanık sembol.
- **Worker:** ayrı süreç; `jobs` tablosu üzerinde `FOR UPDATE SKIP LOCKED`, lease + fence + attempt; tek `metis-worker` kimliği.
- **Frontend:** React 19 + TS strict + Vite, TanStack Router/Query, Radix primitive'leri, CSS Modules + `tokens.css`, `motion`, xyflow + elkjs.
  API tipleri OpenAPI'den (`openapi-typescript`).
- **Dağıtım:** Windows Server, WinSW servisleri, IIS/ARR ters vekil; tek ZIP çevrimdışı paket (hash-kilitli wheelhouse).

## Sonuçlar
- SQLite fallback yok; geliştirme ve test için yerel PG gerekir (`scripts/dev-up.sh`).
- Şema değişikliği her zaman yeni Alembic revizyonu ile; `metis_app` rolü migration çalıştırmaz.
