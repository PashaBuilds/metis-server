"""Notta tablo ve satır içi görsel (2.0.27): görsel satırı `![ad](ek:<kimlik>)` iddia olmaz, blokları ayırır."""

from __future__ import annotations

import uuid

from metis.modules.knowledge.figures import inline_image_ids, isolate_inline_images, strip_inline_images
from metis.modules.notes.blocks import note_blocks

A = "0f8f3c52-3a6e-4c51-9a55-3c1e2b7d9a01"
B = "6b1d2e44-8f3a-4b2c-9d7e-5a4c3b2a1f02"


def _texts(text: str) -> list[str]:
    return [text[s:e] for s, e in note_blocks(text)]


def test_image_line_is_not_a_claim():
    body = f"Kart 3,3 V ile beslenir.\n\n![osiloskop](ek:{A})\n\nUART 115200 baud çalışır."
    assert _texts(body) == ["Kart 3,3 V ile beslenir.", "UART 115200 baud çalışır."]


def test_image_inside_paragraph_splits_it_verbatim():
    body = f"Kart 3,3 V ile beslenir.\n![ölçüm](ek:{A})\nUART 115200 baud çalışır."
    spans = note_blocks(body)
    assert [body[s:e] for s, e in spans] == ["Kart 3,3 V ile beslenir.", "UART 115200 baud çalışır."]


def test_pipe_table_stays_one_block():
    table = "| Pin | Gerilim |\n| --- | --- |\n| VCC | 3,3 V |\n| GND | 0 V |"
    assert _texts(f"Besleme tablosu:\n\n{table}") == ["Besleme tablosu:", table]


def test_inline_image_helpers():
    body = f"Giriş.\n![a](ek:{A}) arada ![](ek:{B.upper()})\n![dış](https://ornek.test/x.png)"
    assert inline_image_ids(body) == [uuid.UUID(A), uuid.UUID(B)]
    assert strip_inline_images(body) == "Giriş.\n[Görsel: a] arada \n![dış](https://ornek.test/x.png)"
    iso = isolate_inline_images(body)
    assert f"\n\n![a](ek:{A})\n\n" in iso
