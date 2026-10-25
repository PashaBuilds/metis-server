# Deterministik bağlantılar (İş 5) — uygulama planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bilgi sayfasında modelsiz "İlgili bilgiler" (açık referanslar + ortak nadir tanımlayıcılar) ve METIS'te karşılığı
olmayan bağlantılı Confluence/GitLab öğesi için "İçe aktar" önerisi.

**Architecture:** İstek anında hesaplanır (tablo yok): `GET /pages/{id}/related`. (a) Yayındaki notta geçen adresler →
`external_origins.url`/dış anahtar; GitLab issue sayfasında `#123` → aynı GitLab projesinin issue'su. (b) `search_documents.symbols`
üzerinden ortak nadir semboller (proje içinde en çok max(2, sayfaların %5'i) sayfada geçen), IDF toplamıyla sıralı, en çok 5.
(c) Bağlantı tanımlı bir sunucuya ait ama içe aktarılmamış adresler → öneri. Okunamayan sayfa listelenmez.

**Spec:** `docs/superpowers/specs/2026-10-25-dis-kaynak-ve-hibrit-arama-design.md` (bölüm 8)

## Global Constraints

- Modelsiz, deterministik; kenar türü ve gerekçesi görünür ("aynı issue'ya bağlanıyor", "ortak: `LTSSM_STATE`").
- Okunamayan revizyon ve başka proje görünmez; Mentor paketine kendiliğinden girmez.
- "İçe aktar" yalnız katkı sahibine; `/katki?kaynak=<adres>` önizlemeyi doldurur.

### Task 1: `GET /pages/{id}/related` (servis + testler)
### Task 2: Bilgi sayfasında "İlgili bilgiler" ve "METIS'te yok · İçe aktar"; Yeni katkı `?kaynak=` ön doldurma
### Task 3: Sürüm 2.0.22
