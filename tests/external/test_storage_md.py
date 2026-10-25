"""Confluence depolama biçimi (XHTML, ac:/ri:) → Markdown. Kurgusal içerik."""

from __future__ import annotations

from metis.modules.external.storage_md import storage_to_markdown


def md(xhtml: str) -> str:
    return storage_to_markdown(xhtml).markdown


def test_headings_paragraphs_inline():
    out = md("<h2>Bağlantı eğitimi</h2><p><strong>LTSSM</strong> <em>durum</em> <code>REG_CTRL</code></p>")
    assert out == "## Bağlantı eğitimi\n\n**LTSSM** *durum* `REG_CTRL`"


def test_nested_lists():
    out = md("<ul><li>a<ul><li>b</li></ul></li></ul><ol><li>c</li><li>d</li></ol>")
    assert out == "- a\n  - b\n\n1. c\n2. d"


def test_table():
    out = md(
        "<table><tbody><tr><th>Alan</th><th>Değer</th></tr>"
        "<tr><td><p>EN</p></td><td>0x1 | 0x2</td></tr></tbody></table>"
    )
    assert out == "| Alan | Değer |\n| --- | --- |\n| EN | 0x1 \\| 0x2 |"


def test_code_macro():
    out = md(
        '<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">c</ac:parameter>'
        "<ac:plain-text-body><![CDATA[int x = 1;\nx <<= 2;]]></ac:plain-text-body></ac:structured-macro>"
    )
    assert out == "```c\nint x = 1;\nx <<= 2;\n```"


def test_panels_and_expand():
    out = md(
        '<ac:structured-macro ac:name="info"><ac:rich-text-body><p>Önce saati aç.</p></ac:rich-text-body></ac:structured-macro>'
        '<ac:structured-macro ac:name="warning"><ac:rich-text-body><p>Sıfırlama gerekir.</p></ac:rich-text-body></ac:structured-macro>'
        '<ac:structured-macro ac:name="note"><ac:rich-text-body><p>Kart B.</p></ac:rich-text-body></ac:structured-macro>'
        '<ac:structured-macro ac:name="expand"><ac:parameter ac:name="title">Ayrıntı</ac:parameter>'
        "<ac:rich-text-body><p>Gizli metin.</p></ac:rich-text-body></ac:structured-macro>"
    )
    assert out == "> **Bilgi:** Önce saati aç.\n\n> **Uyarı:** Sıfırlama gerekir.\n\n> **Not:** Kart B.\n\n**Ayrıntı**\n\nGizli metin."


def test_image_and_unknown_macro():
    conv = storage_to_markdown(
        '<ac:structured-macro ac:name="toc"/><p>Şema:</p>'
        '<ac:image ac:height="200"><ri:attachment ri:filename="sema.png"/></ac:image>'
        '<ac:image><ri:attachment ri:filename="sema.png"/></ac:image>'
        '<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">X-1</ac:parameter></ac:structured-macro>'
    )
    assert conv.markdown == "Şema:\n\n[Görsel: sema.png]\n\n[Görsel: sema.png]"
    assert conv.images == ["sema.png"]
    assert conv.skipped_macros == ["toc", "jira"]


def test_broken_markup_keeps_text():
    out = md("<p>bir<strong>iki<p>üç &amp; dört&nbsp;beş")
    assert "bir" in out and "iki" in out and "üç & dört beş" in out


def test_links():
    out = md(
        '<p><a href="https://x.example.test/a">metin</a> ve '
        '<ac:link><ri:page ri:content-title="Diğer Sayfa"/></ac:link> ve '
        '<ac:link><ri:page ri:content-title="Üçüncü"/><ac:plain-text-link-body><![CDATA[görünen]]></ac:plain-text-link-body></ac:link></p>'
    )
    assert out == "[metin](https://x.example.test/a) ve Diğer Sayfa ve görünen"


def test_line_breaks_and_task_list():
    out = md('<p>satır1<br/>satır2</p><ac:task-list><ac:task><ac:task-status>complete</ac:task-status>'
             "<ac:task-body>bitti</ac:task-body></ac:task><ac:task><ac:task-status>incomplete</ac:task-status>"
             "<ac:task-body>açık</ac:task-body></ac:task></ac:task-list>")
    assert out == "satır1  \nsatır2\n\n- [x] bitti\n- [ ] açık"


def test_pre_block():
    assert md("<pre>a  b\n  c</pre>") == "```\na  b\n  c\n```"


STATUS = '<ac:structured-macro ac:name="status"><ac:parameter ac:name="title">ONAYLANDI</ac:parameter></ac:structured-macro>'


def test_status_macro_inline_in_paragraph_and_cell():
    conv = storage_to_markdown(f"<p>Durum: {STATUS} tamam</p><table><tr><th>Adım</th><th>Durum</th></tr><tr><td>A</td><td>{STATUS}</td></tr></table>")
    assert conv.markdown == "Durum: ONAYLANDI tamam\n\n| Adım | Durum |\n| --- | --- |\n| A | ONAYLANDI |"
    assert conv.skipped_macros == []


def test_bodyless_macro_does_not_split_paragraph():
    conv = storage_to_markdown('<p>Bkz <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">X-1</ac:parameter></ac:structured-macro> sonra</p>')
    assert conv.markdown == "Bkz sonra" and conv.skipped_macros == ["jira"]
