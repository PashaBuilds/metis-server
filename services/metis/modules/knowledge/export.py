"""Bilgi havuzunu Markdown ZIP olarak dışa aktarma (Ayarlar → Dışa aktar).

Yalnız kullanıcının okuyabildiği aktif yayın sayfaları; her sayfa bir .md dosyası (iddialar ve kaynak dipnotları),
`index.md` (türe göre içindekiler) ve `kaynaklar.md` (kaynak listesi, revizyon, SHA-256). Kaynak dosyaları
ZIP'e eklenmez (erişim listesi ve boyut nedeniyle); bağlantı METIS'teki İz paneline verilir. İstisna: sayfanın
açıklayıcı görselleri sayfanın parçasıdır; `gorseller/` altına eklenir ve metinde yerinde gösterilir.
"""

from __future__ import annotations

import io
import re
import unicodedata
import uuid
import zipfile
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from metis.core.access import require_member
from metis.core.blobs import read_blob
from metis.core.models import Attachment, Project, SourceRevision, User
from metis.modules.knowledge.figures import FIGURE_LINE
from metis.modules.knowledge.service import _active_rows
from metis.modules.knowledge.views import revision_views
from metis.modules.scopes.semantics import DIMENSIONS, normalize_scope

KIND_LABELS = {"concept": "Kavram", "component": "Bileşen", "procedure": "Prosedür", "decision": "Karar", "incident": "Olay", "validation": "Doğrulama", "table": "Tablo", "learning_path": "Öğrenme yolu"}
DIM_LABELS = {"domain": "Domain", "yatt": "YATT", "kart": "Kart", "proje": "Proje"}


def slug(text: str) -> str:
    table = str.maketrans({"ı": "i", "İ": "i", "ğ": "g", "Ğ": "g", "ş": "s", "Ş": "s", "ç": "c", "Ç": "c", "ö": "o", "Ö": "o", "ü": "u", "Ü": "u"})
    ascii_text = unicodedata.normalize("NFKD", text.translate(table)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:80] or "sayfa"


def scope_line(scope: dict) -> str:
    s = normalize_scope(scope)
    parts = []
    for d in DIMENSIONS:
        vals = s[d]
        parts.append(f"{DIM_LABELS[d]}: " + ("Bağımsız" if vals == ["*"] else ", ".join(vals) if vals else "Belirlenmemiş"))
    return " · ".join(parts)


def export_zip(db: Session, user: User, project_id: uuid.UUID) -> tuple[str, bytes]:
    require_member(db, user, project_id)
    project = db.get(Project, project_id)
    assert project is not None
    rows = sorted(_active_rows(db, user, project_id), key=lambda pr: pr[1].title.casefold())
    views = revision_views(db, [r for _, r in rows])
    names: dict[uuid.UUID, str] = {}
    used: set[str] = set()
    for page, rev in rows:
        base = slug(rev.title)
        name, i = base, 2
        while name in used:
            name, i = f"{base}-{i}", i + 1
        used.add(name)
        names[page.id] = f"sayfalar/{name}.md"
    sources: dict[uuid.UUID, dict] = {}
    images: dict[uuid.UUID, str] = {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for page, rev in rows:
            view = views[rev.id]
            for fig in view.figures:
                if fig.source_revision_id not in images:
                    sr = db.get(SourceRevision, fig.source_revision_id)
                    assert sr is not None
                    ext = ".png" if sr.media_type == "image/png" else ".jpg"
                    images[fig.source_revision_id] = f"gorseller/{fig.source_revision_id}{ext}"
                    z.writestr(images[fig.source_revision_id], read_blob(sr.sha256))
            figs = {f.ord: f for f in view.figures}

            def figure_md(m: re.Match[str], figs: dict = figs) -> str:
                f = figs.get(int(m.group(1)))
                return f"![{f.caption}](../{images[f.source_revision_id]})" if f else ""

            notes: list[str] = []
            note_no: dict[uuid.UUID, int] = {}
            claim_lines = []
            for c in view.claims:
                refs = []
                for ev in c.evidence:
                    if ev.evidence_id not in note_no:
                        note_no[ev.evidence_id] = len(note_no) + 1
                        notes.append(f"[^{note_no[ev.evidence_id]}]: {ev.source_title} · r{ev.source_revision_number} · {ev.locator_label or 'konum belirtilmemiş'} — “{ev.quote.strip()}”")
                        sources.setdefault(ev.source_revision_id, {"title": ev.source_title, "kind": ev.source_kind, "number": ev.source_revision_number, "current": ev.source_is_current})
                    refs.append(f"[^{note_no[ev.evidence_id]}]")
                claim_lines.append(f"- {c.statement} {''.join(refs)}".rstrip())
            md = [
                f"# {view.title}",
                "",
                f"> {KIND_LABELS.get(view.kind, view.kind)} · {scope_line(view.scope)} · r{view.number} · {view.author_name}",
                "",
                view.summary,
                "",
                FIGURE_LINE.sub(figure_md, view.body_md).strip(),
                "",
                "## İddialar",
                "",
                *(claim_lines or ["- (iddia yok)"]),
            ]
            if view.unknowns:
                md += ["", "## Bilinmeyenler", "", *[f"- {u}" for u in view.unknowns]]
            if view.attachments:
                folder = "ekler/" + names[page.id].removeprefix("sayfalar/").removesuffix(".md")
                links = []
                for n, att in enumerate(view.attachments, start=1):
                    row = db.get(Attachment, att.id)
                    assert row is not None
                    path = f"{folder}/{n}-{att.filename}"
                    z.writestr(path, read_blob(row.sha256))
                    links.append(f"- [{att.filename}](../{path})")
                md += ["", "## Ekler", "", *links]
            if notes:
                md += ["", *notes]
            z.writestr(names[page.id], "\n".join(md).strip() + "\n")
        by_kind: dict[str, list[str]] = {}
        for page, rev in rows:
            by_kind.setdefault(KIND_LABELS.get(rev.kind, rev.kind), []).append(f"- [{rev.title}]({names[page.id]})")
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        index = [f"# {project.name} — bilgi havuzu", "", f"Dışa aktarma: {stamp} · {len(rows)} sayfa · yalnız aktif yayın ve senin erişebildiğin kayıtlar.", "", "Kaynak listesi: [kaynaklar.md](kaynaklar.md)", ""]
        for kind in sorted(by_kind):
            index += [f"## {kind}", "", *by_kind[kind], ""]
        z.writestr("index.md", "\n".join(index))
        src_lines = ["# Kaynaklar", "", "| Kaynak | Tür | Revizyon | Güncel mi |", "|---|---|---|---|"]
        for s in sorted(sources.values(), key=lambda x: (x["title"].casefold(), x["number"])):
            src_lines.append(f"| {s['title']} | {s['kind']} | r{s['number']} | {'evet' if s['current'] else 'hayır, daha yeni revizyon var'} |")
        z.writestr("kaynaklar.md", "\n".join(src_lines) + "\n")
    filename = f"metis-{slug(project.name)}-{datetime.now(UTC).strftime('%Y%m%d')}.zip"
    return filename, buf.getvalue()
