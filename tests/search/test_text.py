"""Blok indeksi yardımcıları: Türkçe harf katlama ve not başlık yolu."""

from __future__ import annotations

from metis.modules.search.index import heading_paths
from metis.modules.search.text import fold


def test_fold():
    assert fold("Saat KAYNAĞI İŞLEMİ ılık Çöğüş") == "saat kaynagi islemi ilik cogus"
    assert fold("INIT_BUS 0x1F") == "init_bus 0x1f"


def test_heading_paths():
    blocks = ["## Genel", "Giriş metni.", "### Alt", "Alt metin.", "## İkinci", "Son.", "#etiket değil başlık"]
    assert heading_paths(blocks) == ["Genel", "Genel", "Genel › Alt", "Genel › Alt", "İkinci", "İkinci", "İkinci"]


def test_heading_paths_without_headings_and_multiline():
    assert heading_paths(["a", "b"]) == ["", ""]
    assert heading_paths(["## Başlık\nve devamı", "x"]) == ["", ""]  # çok satırlı blok başlık sayılmaz
