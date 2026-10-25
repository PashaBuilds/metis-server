# İçe aktarmada model zenginleştirmesi (İş 4) — uygulama planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Model açıkken yayımlanmış bloklara "bağlam cümlesi" ve "bu blok hangi soruları cevaplar" üretip saklamak; arama
(kelime + vektör) bunları kullanır; model kapalıyken saklanan zenginleştirme kullanılmaya devam eder; kanıt değildir.

**Architecture:** Worker `enrich_loop`: uygun model (mevcut `route`) varsa, zenginleştirmesi olmayan yayımlanmış blokları
sayfa sayfa (sayfa başına en çok 12 blok) tek çağrıyla gönderir (`passage-enrichment-v1` istemi, JSON sözleşmesi).
Deterministik süzgeç: sorudaki her tanımlayıcı (sembol/hex) blok gövdesinde birebir geçmeli; uzunluk sınırları.
Sonuç `passage_enrichments`'ta (blok metni hash'i + istem sürümü anahtarlı). Sayfa yeniden indekslenir: zenginleştirme
`tsv` D ağırlığına ve gömme metnine girer → vektör yeniden hesaplanır. Art arda 3 hata → 5 dk bekleme.

**Spec:** `docs/superpowers/specs/2026-10-25-dis-kaynak-ve-hibrit-arama-design.md` (bölüm 7)

## Global Constraints

- Yalnız yayımlanmış bloklar modele gider; taslak/okunamayan içerik gönderilmez. Kaynak metin veridir (istem kuralı).
- Zenginleştirme kanıt değildir: alıntı, doğrulama, Mentor paketi ve arayüz gösterimi ona dayanmaz.
- Model yoksa iş beklemede; arama zenginleştirmesiz sürer. Ölçülmemiş kazanç "ölçülmedi" (gerçek model bu bilgisayarda yok).
- Proje ayarı: zenginleştirme açık (varsayılan) / kapalı.

### Task 1: Şema, istem, sözleşme, sahte model yanıtı, süzgeç
### Task 2: Worker döngüsü (`enrich_loop`) ve yeniden indeksleme
### Task 3: İndekste kullanım (tsv D + gömme metni) ve testler
### Task 4: Proje ayarı + Sistem durumu satırı ("Zenginleştirme: n/m blok")
### Task 5: Sürüm 2.0.21
