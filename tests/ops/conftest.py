from __future__ import annotations

import pytest

from tests.factories import add_scope_values, create_user, setup_admin


@pytest.fixture
def team(client, make_client):  # noqa: ANN001, ANN201
    """Yönetici + katkı sahibi + inceleyici + okur + üye olmayan kullanıcı, ortak kapsam kataloğu."""
    me = setup_admin(client)
    pid = me["memberships"][0]["project_id"]
    add_scope_values(
        client, pid, {"domain": ["Gömülü yazılım"], "kart": ["VPK120", "K2"], "proje": ["Atlas"], "yatt": ["Y1"]}
    )
    contributor = create_user(client, "kemal", ["contributor"], pid, make_client)
    reviewer = create_user(client, "rana", ["reviewer"], pid, make_client)
    reader = create_user(client, "okan", ["reader"], pid, make_client)
    outsider = create_user(client, "dilek", [], pid, make_client)
    return {
        "pid": pid,
        "admin": client,
        "contributor": contributor,
        "reviewer": reviewer,
        "reader": reader,
        "outsider": outsider,
    }
