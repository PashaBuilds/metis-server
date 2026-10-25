"""Adres ayrıştırma ve GitLab issue → Markdown. Kurgusal adresler."""

from __future__ import annotations

import pytest

from metis.core.errors import AppError
from metis.modules.external import confluence, gitlab

WIKI = "http://wiki.example.test/confluence"
GIT = "http://git.example.test"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (f"{WIKI}/pages/viewpage.action?pageId=1001", ("1001", None, None)),
        (f"{WIKI}/spaces/BSP/pages/1001/PCIe+Notu", ("1001", "BSP", None)),
        (f"{WIKI}/display/BSP/PCIe+Notu", (None, "BSP", "PCIe Notu")),
        (f"{WIKI}/display/BSP/Ba%C4%9Flant%C4%B1+e%C4%9Fitimi", (None, "BSP", "Bağlantı eğitimi")),
        (f"{WIKI}/x/whatever?pageId=1002#ust", ("1002", None, None)),
    ],
)
def test_confluence_refs(url, expected):  # noqa: ANN001
    ref = confluence.parse_ref(WIKI, url)
    assert (ref.page_id, ref.space, ref.title) == expected


@pytest.mark.parametrize("url", ["http://baska.example.test/confluence/pages/viewpage.action?pageId=1", f"{WIKI}/spaces/BSP/overview", "metin"])
def test_confluence_unrecognized(url):  # noqa: ANN001
    with pytest.raises(AppError) as exc:
        confluence.parse_ref(WIKI, url)
    assert exc.value.code == "EXTERNAL_URL_UNRECOGNIZED"


def test_gitlab_refs():
    assert gitlab.parse_ref(GIT, f"{GIT}/ekip/bsp/-/issues/7") == gitlab.GitlabRef("ekip/bsp", 7)
    assert gitlab.parse_ref(GIT, f"{GIT}/ekip/alt/bsp/issues/12#note_5") == gitlab.GitlabRef("ekip/alt/bsp", 12)
    for bad in (f"{GIT}/ekip/bsp/-/merge_requests/3", "http://baska.example.test/ekip/bsp/-/issues/7", f"{GIT}/ekip/bsp"):
        with pytest.raises(AppError) as exc:
            gitlab.parse_ref(GIT, bad)
        assert exc.value.code == "EXTERNAL_URL_UNRECOGNIZED"


def test_issue_markdown():
    issue = gitlab.GitlabIssue(
        project_id=5,
        project_path="ekip/bsp",
        iid=7,
        title="PCIe bağlantısı kurulmuyor",
        description="Kart açılışta `LTSSM_STATE` 0x11'de kalıyor.",
        state="closed",
        labels=["pcie", "sürücü"],
        author="Kurgusal Kişi",
        created_at="2026-01-05T09:00:00.000Z",
        updated_at="2026-01-07T10:00:00.000Z",
        web_url=f"{GIT}/ekip/bsp/-/issues/7",
        confidential=False,
        notes=[gitlab.GitlabNote("Kurgusal İkinci", "2026-01-06T08:30:00.000Z", "Saat kaynağını değiştirince düzeldi.")],
    )
    assert gitlab.issue_markdown(issue) == (
        "**Durum:** Kapalı · **Etiketler:** pcie, sürücü · **Açan:** Kurgusal Kişi · 2026-01-05\n\n"
        "Kart açılışta `LTSSM_STATE` 0x11'de kalıyor.\n\n"
        "## Yorumlar\n\n"
        "### Kurgusal İkinci — 2026-01-06\n\n"
        "Saat kaynağını değiştirince düzeldi."
    )


def test_upload_refs():
    md = "Log: ![log](/uploads/abc123/log.png) ve [rapor](/uploads/def456/rapor.pdf) ve ![x](https://dis.example.test/a.png)"
    assert gitlab.upload_refs(md) == [("abc123", "log.png"), ("def456", "rapor.pdf")]
