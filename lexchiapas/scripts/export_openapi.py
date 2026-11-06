"""Exporta el esquema OpenAPI de la app a un archivo JSON (sin levantar el
servidor). Lo consume el frontend para generar sus tipos:
  python scripts/export_openapi.py ../lexchiapas-web/openapi.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1])
    out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"OpenAPI escrito en {out}")


if __name__ == "__main__":
    main()
