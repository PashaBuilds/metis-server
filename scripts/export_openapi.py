"""OpenAPI sözleşmesini koddan üretir (apps/web/openapi.json). CI'da diff kontrolü yapılır."""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("METIS_ENV", "test")
os.environ.setdefault("METIS_DATA_DIR", str(Path(__file__).resolve().parents[1] / ".data" / "openapi"))

from metis.app import create_app  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "apps" / "web" / "openapi.json")
spec = create_app().openapi()
out.write_bytes((json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))  # Windows'ta da LF
print(f"wrote {out} ({len(spec['paths'])} paths)")
