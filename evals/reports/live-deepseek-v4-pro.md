# Değerlendirme raporu — live

Tarih: 2026-10-18T14:08:14+00:00  
Model: `deepseek-v4-pro`  
Profil: `{"json_mode": "json_object", "thinking": "disabled", "probed": false}`

> Canlı mod: gerçek model. Sonuç hattın ve modelin birlikte davranışıdır; vaka sayısı küçüktür.

## Kanıtlı cevap (evidence-explain-v1)

**26/26** geçti, kritik hata 0; 1 vakada model kapsam dışı cevap verdi, deterministik kapsam koruması durdurdu.

## Worker prompt'ları

**35/36** geçti.

Geçmeyenler:

- `compare-live-05` — {"task": "compare", "expected": "no_change", "verdict": "addition", "error": null, "latency_ms": 2005.0}

## Açıklama cümle denetimi (deterministik)

**15/15** geçti.

## Kaynağa göre (kanıtlı cevap)

- v0.5.5 gateway.cases (ortak benchmark): 6/6
- v0.5.5 evidence_prompt_holdout.json: 16/16
- v0.5.5 evidence_prompt_fresh.json: 4/4
