"""Confluence depolama biçimi (XHTML, `ac:`/`ri:` öğeleri) → Markdown. Yalnız standart kütüphane.

Hoşgörülü: bozuk işaretleme (kapanmamış etiket) metni düşürmez. Desteklenmeyen makrolar atlanır ve adları raporlanır;
gövdesi olan bilinmeyen makronun içeriği korunur. Görseller `[Görsel: ad.png]` işaretine döner (dosya ek olarak gelir).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

VOID = {"br", "hr", "img", "col", "ri:attachment", "ri:page", "ri:user", "ri:url", "ri:space", "ri:content-entity", "ac:emoticon"}
BLOCK = {
    "p", "div", "section", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "pre", "blockquote", "hr",
    "ac:structured-macro", "ac:macro", "ac:image", "ac:task-list", "ac:rich-text-body", "ac:layout", "ac:layout-section",
    "ac:layout-cell", "tbody", "thead", "tfoot",
}  # fmt: skip
PANELS = {"info": "Bilgi", "tip": "İpucu", "note": "Not", "warning": "Uyarı", "panel": None}
CODE_MACROS = {"code", "noformat"}
CONTAINER_MACROS = {"section", "column", "details", "div", "excerpt", "panel-body"}
_BR = "\x00BR\x00"


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    children: list[_Node | _Text] = field(default_factory=list)


@dataclass
class _Text:
    text: str
    raw: bool = False  # CDATA: boşluk ve satır sonu korunur


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.stack[-1].children.append(_Node(tag, {k: v or "" for k, v in attrs}))

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(_Text(data))

    def unknown_decl(self, data: str) -> None:
        if data.startswith("CDATA["):
            self.stack[-1].children.append(_Text(data[6:], raw=True))


@dataclass
class Converted:
    markdown: str
    images: list[str] = field(default_factory=list)
    skipped_macros: list[str] = field(default_factory=list)


class _Renderer:
    def __init__(self) -> None:
        self.images: list[str] = []
        self.skipped: list[str] = []

    # ------------------------------------------------------------ yardımcılar
    def _image(self, node: _Node) -> str:
        name = ""
        for c in node.children:
            if isinstance(c, _Node) and c.tag == "ri:attachment":
                name = c.attrs.get("ri:filename", "")
            elif isinstance(c, _Node) and c.tag == "ri:url":
                name = c.attrs.get("ri:value", "")
        if not name:
            return ""
        if not name.startswith(("http://", "https://")) and name not in self.images:
            self.images.append(name)
        return f"[Görsel: {name}]"

    @staticmethod
    def _child(node: _Node, tag: str, name: str | None = None) -> _Node | None:
        for c in node.children:
            if isinstance(c, _Node) and c.tag == tag and (name is None or c.attrs.get("ac:name") == name):
                return c
        return None

    def _param(self, node: _Node, name: str) -> str:
        p = self._child(node, "ac:parameter", name)
        return self.raw(p).strip() if p else ""

    def raw(self, node: _Node) -> str:
        out = []
        for c in node.children:
            out.append(c.text if isinstance(c, _Text) else self.raw(c))
        return "".join(out)

    # ------------------------------------------------------------ satır içi
    def inline(self, nodes: list[_Node | _Text]) -> str:
        return "".join(self.inline_node(n) for n in nodes)

    def inline_node(self, n: _Node | _Text) -> str:
        if isinstance(n, _Text):
            return n.text
        tag = n.tag
        if tag == "br":
            return _BR
        if tag in ("strong", "b", "em", "i", "code", "s", "del"):
            inner = _collapse(self.inline(n.children)).strip()
            mark = {"strong": "**", "b": "**", "em": "*", "i": "*", "code": "`", "s": "~~", "del": "~~"}[tag]
            return f"{mark}{inner}{mark}" if inner else ""
        if tag == "a":
            text = _collapse(self.inline(n.children)).strip()
            href = n.attrs.get("href", "")
            return f"[{text}]({href})" if href and text and href.startswith(("http://", "https://")) else text
        if tag == "ac:link":
            body = self._child(n, "ac:plain-text-link-body")
            if body:
                return self.raw(body)
            rich = self._child(n, "ac:link-body")
            if rich:
                return self.inline(rich.children)
            for c in n.children:
                if isinstance(c, _Node) and c.tag == "ri:page":
                    return c.attrs.get("ri:content-title", "")
                if isinstance(c, _Node) and c.tag == "ri:attachment":
                    return c.attrs.get("ri:filename", "")
            return ""
        if tag == "ac:image":
            return self._image(n)
        if tag in ("ac:structured-macro", "ac:macro"):
            name = n.attrs.get("ac:name", "")
            if name == "status":
                return self._param(n, "title")
            body = self._child(n, "ac:rich-text-body")
            if body:
                return self.inline(body.children)
            self.skipped.append(name)
            return ""
        if tag in ("ac:parameter", "ac:emoticon", "ri:user", "ac:placeholder"):
            return ""
        return self.inline(n.children)

    def _inline_macro(self, n: _Node) -> bool:
        """Gövdesiz makro (status, jira…) satır içidir: paragrafı bölmez, tablo hücresinde kaybolmaz."""
        if n.tag not in ("ac:structured-macro", "ac:macro"):
            return False
        if n.attrs.get("ac:name") == "status":
            return True
        return self._child(n, "ac:rich-text-body") is None and self._child(n, "ac:plain-text-body") is None

    # ------------------------------------------------------------ bloklar
    def blocks(self, nodes: list[_Node | _Text]) -> list[str]:
        out: list[str] = []
        run: list[str] = []

        def flush() -> None:
            text = _finish_inline("".join(run))
            if text:
                out.append(text)
            run.clear()

        for n in nodes:
            if isinstance(n, _Node) and n.tag in BLOCK and not self._inline_macro(n):
                flush()
                out.extend(self.block(n))
            else:
                run.append(self.inline_node(n))
        flush()
        return out

    def block(self, n: _Node) -> list[str]:
        tag = n.tag
        if re.fullmatch(r"h[1-6]", tag):
            text = _finish_inline(self.inline(n.children))
            return [f"{'#' * int(tag[1])} {text}"] if text else []
        if tag in ("ul", "ol"):
            text = self.list_md(n, "")
            return [text] if text else []
        if tag == "table":
            text = self.table_md(n)
            return [text] if text else []
        if tag == "pre":
            return [f"```\n{self.raw(n).strip(chr(10))}\n```"]
        if tag == "blockquote":
            return [_quote(self.blocks(n.children))] if self.blocks(n.children) else []
        if tag == "hr":
            return ["---"]
        if tag == "ac:image":
            img = self._image(n)
            return [img] if img else []
        if tag == "ac:task-list":
            lines = []
            for task in n.children:
                if isinstance(task, _Node) and task.tag == "ac:task":
                    status = self._child(task, "ac:task-status")
                    body = self._child(task, "ac:task-body")
                    done = status is not None and self.raw(status).strip() == "complete"
                    text = _finish_inline(self.inline(body.children)) if body else ""
                    lines.append(f"- [{'x' if done else ' '}] {text}")
            return ["\n".join(lines)] if lines else []
        if tag in ("ac:structured-macro", "ac:macro"):
            return self.macro(n)
        return self.blocks(n.children)

    def macro(self, n: _Node) -> list[str]:
        name = n.attrs.get("ac:name", "")
        body = self._child(n, "ac:rich-text-body")
        if name in CODE_MACROS:
            plain = self._child(n, "ac:plain-text-body")
            code = self.raw(plain).strip("\n") if plain else ""
            return [f"```{self._param(n, 'language')}\n{code}\n```"]
        if name in PANELS:
            inner = self.blocks(body.children) if body else []
            label = PANELS[name]
            if label and inner:
                inner[0] = f"**{label}:** {inner[0]}"
            return [_quote(inner)] if inner else []
        if name == "expand":
            title = self._param(n, "title") or "Ayrıntı"
            return [f"**{title}**", *(self.blocks(body.children) if body else [])]
        if body is not None:
            return self.blocks(body.children)
        plain = self._child(n, "ac:plain-text-body")
        if plain is not None and name not in CONTAINER_MACROS:
            return [f"```\n{self.raw(plain).strip(chr(10))}\n```"]
        self.skipped.append(name)
        return []

    def list_md(self, n: _Node, indent: str) -> str:
        lines: list[str] = []
        number = 0
        for li in n.children:
            if not (isinstance(li, _Node) and li.tag == "li"):
                continue
            number += 1
            marker = f"{number}. " if n.tag == "ol" else "- "
            text_parts: list[_Node | _Text] = []
            nested: list[_Node] = []
            for c in li.children:
                if isinstance(c, _Node) and c.tag in ("ul", "ol"):
                    nested.append(c)
                else:
                    text_parts.append(c)
            text = " ".join(self.blocks(text_parts)).replace("\n", " ")
            lines.append(f"{indent}{marker}{text}".rstrip())
            for sub in nested:
                sub_md = self.list_md(sub, indent + " " * len(marker))
                if sub_md:
                    lines.append(sub_md)
        return "\n".join(lines)

    def table_md(self, n: _Node) -> str:
        rows: list[list[str]] = []

        def walk(node: _Node) -> None:
            for c in node.children:
                if not isinstance(c, _Node):
                    continue
                if c.tag == "tr":
                    cells = []
                    for cell in c.children:
                        if isinstance(cell, _Node) and cell.tag in ("td", "th"):
                            text = " ".join(self.blocks(cell.children)).replace("\n", " ").replace("|", "\\|")
                            cells.append(text.strip())
                    rows.append(cells)
                elif c.tag != "table":
                    walk(c)

        walk(n)
        rows = [r for r in rows if r]
        if not rows:
            return ""
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
        lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
        return "\n".join(lines)


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " "))


def _finish_inline(text: str) -> str:
    text = _collapse(text).strip()
    text = re.sub(rf" ?{re.escape(_BR)} ?", _BR, text)
    return text.replace(_BR, "  \n").strip()


def _quote(blocks: list[str]) -> str:
    return "\n>\n".join("\n".join(f"> {line}" if line else ">" for line in b.split("\n")) for b in blocks)


def storage_to_markdown(xhtml: str) -> Converted:
    builder = _TreeBuilder()
    builder.feed(xhtml or "")
    builder.close()
    r = _Renderer()
    md = "\n\n".join(b for b in r.blocks(builder.root.children) if b.strip())
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    skipped = list(dict.fromkeys(s for s in r.skipped if s))
    return Converted(markdown=md, images=r.images, skipped_macros=skipped)
