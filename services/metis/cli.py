"""metis komut satırı: migrate | serve | worker | setup-code | admin | doctor | backup | restore | demo | mock-llm."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path


def _alembic_config(url: str | None = None):  # noqa: ANN202
    from alembic.config import Config

    from metis.modules.system.service import MIGRATIONS

    cfg = Config(str(MIGRATIONS / "alembic.ini"))
    cfg.set_main_option("script_location", str(MIGRATIONS))
    if url:
        cfg.attributes["url"] = url
    return cfg


def cmd_migrate(args: argparse.Namespace) -> int:
    from alembic import command

    command.upgrade(_alembic_config(args.url), args.revision)
    out: dict = {"migrated_to": args.revision}
    if args.revision == "head":
        # 2026-10-19: eski yöntemden kalan bağımsız kaynaklar not taslağına dönüşür (veri silinmez; idempotent).
        from metis.core.db import transaction
        from metis.modules.notes.service import convert_standalone_sources

        with transaction() as db:
            report = convert_standalone_sources(db)
        out["converted_sources"] = report.created
        if report.skipped:  # dönüştürülemeyen kaynak silinmez; yönetici görsün diye raporlanır
            out["skipped_sources"] = report.skipped
    print(json.dumps(out))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "metis.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        workers=args.workers,
        proxy_headers=False,
        server_header=False,
        ssl_certfile=args.ssl_certfile or None,
        ssl_keyfile=args.ssl_keyfile or None,
        timeout_graceful_shutdown=10,
    )
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    from metis.worker.loop import run_forever

    run_forever(slots=args.slots, once=args.once)
    return 0


def cmd_setup_code(_args: argparse.Namespace) -> int:
    from metis.core.db import transaction
    from metis.modules.auth.service import issue_setup_code

    with transaction() as db:
        code = issue_setup_code(db)
    print("METIS ilk yönetici kurulum kodu (24 saat geçerli, tek kullanımlık):")
    print(code)
    return 0


def cmd_admin(args: argparse.Namespace) -> int:
    from sqlalchemy import func, select

    from metis.core.audit import audit
    from metis.core.db import transaction
    from metis.core.models import User
    from metis.core.security import check_password_strength, hash_password
    from metis.modules.auth.service import ensure_worker_identity

    if args.action != "create":
        print("Desteklenen: metis admin create", file=sys.stderr)
        return 2
    password = getpass.getpass("Parola (en az 12 karakter): ")
    if password != getpass.getpass("Parola (tekrar): "):
        print("Parolalar eşleşmedi.", file=sys.stderr)
        return 1
    check_password_strength(password)
    with transaction() as db:
        if db.scalar(select(User.id).where(func.lower(User.username) == args.username.lower())):
            print("Bu kullanıcı adı zaten var.", file=sys.stderr)
            return 1
        user = User(
            username=args.username,
            display_name=args.display_name or args.username,
            password_hash=hash_password(password),
            is_admin=True,
        )
        db.add(user)
        db.flush()
        ensure_worker_identity(db)
        audit(db, None, "admin.create_cli", "user", user.id)
    print(f"Yönetici oluşturuldu: {args.username}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from metis.ops.doctor import run_doctor

    report = run_doctor()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["ready"] else 1


def cmd_backup(args: argparse.Namespace) -> int:
    from metis.ops.backup import create_backup, prune_backups

    result = create_backup(Path(args.destination) if args.destination else None)
    if args.keep_days:
        result["pruned"] = prune_backups(args.keep_days)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    from metis.ops.backup import latest_backup, rehearse_restore, restore_backup

    archive = latest_backup() if args.archive == "latest" else Path(args.archive)
    if archive is None:
        print(json.dumps({"ok": False, "code": "NOT_FOUND", "message": "Yedek bulunamadı."}, ensure_ascii=False))
        return 1
    result = rehearse_restore(archive) if args.rehearsal else restore_backup(archive)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1
def cmd_demo(args: argparse.Namespace) -> int:
    from metis.seed.demo import create_demo_workspace

    result = create_demo_workspace(admin_username=args.admin)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_demo_graph(args: argparse.Namespace) -> int:
    from metis.seed.graph import create_graph_workspace

    print(json.dumps(create_graph_workspace(nodes=args.nodes), ensure_ascii=False))
    return 0


def cmd_mock_llm(args: argparse.Namespace) -> int:
    from metis.llm.mock_server import serve

    serve(args.host, args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    # Windows'ta yönlendirilen çıktı (servis, zamanlanmış görev, betik) cp1252 olur; Türkçe metin UnicodeEncodeError verir.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="metis")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("migrate", help="Veritabanı şemasını yükselt (sahip rolüyle)")
    p.add_argument("--revision", default="head")
    p.add_argument("--url", default=None)
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("serve", help="API + web sunucusu")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--ssl-certfile", default="")
    p.add_argument("--ssl-keyfile", default="")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("worker", help="Metis worker iş kuyruğu")
    p.add_argument("--slots", type=int, default=2)
    p.add_argument("--once", action="store_true")
    p.set_defaults(func=cmd_worker)

    p = sub.add_parser("setup-code", help="İlk yönetici için tek kullanımlık kurulum kodu üret")
    p.set_defaults(func=cmd_setup_code)

    p = sub.add_parser("admin", help="Yönetici işlemleri")
    p.add_argument("action", choices=["create"])
    p.add_argument("--username", required=True)
    p.add_argument("--display-name", default="")
    p.set_defaults(func=cmd_admin)

    p = sub.add_parser("doctor", help="Kurulum ve çalışma durumu denetimi")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("backup", help="pg_dump + blob deposu + master key parmak izi arşivi")
    p.add_argument("--destination", default="")
    p.add_argument("--keep-days", type=int, default=0)
    p.set_defaults(func=cmd_backup)

    p = sub.add_parser("restore", help="Yedeği boş veritabanına geri yükle")
    p.add_argument("archive")
    p.add_argument("--rehearsal", action="store_true", help="Geçici DB'ye yükle, doğrula, sil")
    p.set_defaults(func=cmd_restore)


    p = sub.add_parser("demo", help="Kurgusal çalışma alanını oluştur (yalnız geliştirme profili)")
    p.add_argument("--admin", default="")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("demo-graph", help="Harita performans testi için kurgusal büyük graf (geliştirme)")
    p.add_argument("--nodes", type=int, default=200)
    p.set_defaults(func=cmd_demo_graph)

    p = sub.add_parser("mock-llm", help="Kurgusal (deterministik) OpenAI uyumlu test modeli")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9100)
    p.set_defaults(func=cmd_mock_llm)

    args = parser.parse_args(argv)
    from metis.core.errors import AppError

    try:
        return int(args.func(args) or 0)
    except AppError as exc:
        print(f"Hata: {exc.code} — {exc.message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
