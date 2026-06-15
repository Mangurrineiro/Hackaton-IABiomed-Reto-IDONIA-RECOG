"""Prueba manual de autenticación contra Idonia."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_settings
from src.idonia_client import IdoniaClient
from src.logger import configure_logging
from src.pipeline_utils import mask_sensitive_text, sanitize


def main() -> int:
    try:
        settings = get_settings()
        configure_logging()
        client = IdoniaClient(
            base_url=settings.idonia_base_url,
            api_key=settings.idonia_api_key.get_secret_value(),
            api_secret=settings.idonia_api_secret.get_secret_value(),
        )
        response = client.whoami()
    except Exception as exc:
        print(f"[ERROR] whoami fallido: {mask_sensitive_text(str(exc))}")
        return 1

    print("[OK] Idonia whoami correcto")
    print(json.dumps(_safe_whoami_summary(response), ensure_ascii=False, indent=2))
    return 0


def _safe_whoami_summary(response: Any) -> Any:
    if not isinstance(response, dict):
        return {"response": mask_sensitive_text(str(response)[:500])}

    keys = ("actorId", "realActorId", "scopes", "actorName", "tenantId")
    summary = {key: sanitize(response[key]) for key in keys if key in response}
    return summary or {"response_keys": list(response.keys())[:20]}


if __name__ == "__main__":
    raise SystemExit(main())
