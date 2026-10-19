"""Not → bloklar: deterministik, birebir aralıklar (her blok bir iddia, kanıtı notun aynı aralığı)."""

from __future__ import annotations

from metis.modules.notes.blocks import MAX_BLOCK, note_blocks


def _texts(text: str) -> list[str]:
    return [text[s:e] for s, e in note_blocks(text)]


def test_blocks_split_on_blank_lines():
    assert _texts("A satırı.\n\nB satırı.\n") == ["A satırı.", "B satırı."]


def test_blocks_trim_surrounding_whitespace_and_keep_inner_lines():
    assert _texts("  İlk satır\nikinci satır  \n\n\n   son blok  ") == ["İlk satır\nikinci satır", "son blok"]


def test_blocks_skip_empty_and_marks():
    assert _texts("---\n\n   \n\n***\n\nGerçek bilgi 3,3 V.") == ["Gerçek bilgi 3,3 V."]


def test_blocks_long_block_split_at_sentence():
    sentence = "Bu kurgusal bir ölçüm cümlesidir ve 42 değerini içerir. "
    block = (sentence * 200).strip()  # ~11 bin karakter, boş satırsız
    parts = _texts(block)
    assert len(parts) >= 2
    assert all(len(p) <= MAX_BLOCK for p in parts)
    assert all(p.endswith(".") for p in parts[:-1])  # cümle sınırından bölünür
    assert " ".join(parts) == block


def test_blocks_long_block_without_sentence_end_is_cut():
    block = "x" * (MAX_BLOCK + 10)
    parts = _texts(block)
    assert [len(p) for p in parts] == [MAX_BLOCK, 10]


def test_blocks_deterministic_and_empty():
    text = "Bir.\n\nİki.\n\nÜç."
    assert note_blocks(text) == note_blocks(text)
    assert note_blocks("") == [] and note_blocks(" \n\n ") == []
