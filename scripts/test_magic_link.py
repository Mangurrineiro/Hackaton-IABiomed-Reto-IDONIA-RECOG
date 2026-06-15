"""Script de prueba para crear y obtener Magic Link en Idonia."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_settings
from src.idonia_client import IdoniaClient
from src.logger import configure_logging
from src.models import PatientCase
from src.pipeline_utils import mask_sensitive_text, sanitize


def main() -> int:
    try:
        # Cargamos configuración y logging
        settings = get_settings()
        configure_logging()
        patient_case = PatientCase(
            patient_dni=settings.patient_dni,
            accession_number=settings.case_accession_number,
            study_description=settings.case_study_description,
        )
        # Creamos cliente de Idonia
        client = IdoniaClient(
            base_url=settings.idonia_base_url,
            api_key=settings.idonia_api_key.get_secret_value(),
            api_secret=settings.idonia_api_secret.get_secret_value(),
        )

        # Según el manual, la ruta para Magic Link es DICOMPatientID/DICOMAccessionNumber
        route = patient_case.idonia_magic_link_route
        print("[INFO] Test Magic Link Idonia")
        print(f"[INFO] route: {route}")
        print(f"[INFO] magic_link_id configurado: {settings.idonia_magic_link_id}")
        print(f"[INFO] url demo esperada: https://demo.idonia.com/v/{settings.idonia_magic_link_id}")

        existing_before = _run_step(
            name="GET /ml antes de crear",
            action=lambda: client.get_magic_link(route=route, return_expired=True),
            allow_empty=True,
        )
        _print_response("GET /ml antes de crear", existing_before)

        created = _run_step(
            name="PUT /ml crear o recuperar",
            action=lambda: client.create_magic_link(
                route=route,
                expired_creation_mode="create",
            ),
            allow_empty=False,
        )
        _print_response("PUT /ml crear o recuperar", created)

        existing_after = _run_step(
            name="GET /ml despues de crear",
            action=lambda: client.get_magic_link(route=route, return_expired=True),
            allow_empty=False,
        )
        _print_response("GET /ml despues de crear", existing_after)

    except Exception as exc:
        print(f"[ERROR] Test Magic Link fallido: {mask_sensitive_text(str(exc))}")
        return 1

    print("[OK] Test Magic Link completado")
    return 0


def _run_step(
    name: str,
    action: Callable[[], Any],
    allow_empty: bool,
) -> Any:
    print(f"[INFO] Ejecutando: {name}")
    try:
        response = action()
        _validate_magic_link_response(response, allow_empty=allow_empty)
    except Exception as exc:
        print(f"[ERROR] Paso fallido: {name}")
        print(f"[ERROR] {mask_sensitive_text(str(exc))}")
        raise

    print(f"[OK] Paso completado: {name}")
    return response


def _validate_magic_link_response(response: Any, allow_empty: bool) -> None:
    if response is None:
        if allow_empty:
            return
        raise RuntimeError("La respuesta de Magic Link esta vacia y no se esperaba 204.")

    if not isinstance(response, list):
        raise RuntimeError(f"Se esperaba array de Magic Link, response={response}")

    for item in response:
        if not isinstance(item, dict):
            raise RuntimeError(f"Se esperaba objeto Magic Link, item={item}")
        if "URL" not in item or "PIN" not in item:
            raise RuntimeError(
                "Respuesta Magic Link sin campos esperados URL/PIN, "
                f"item={item}"
            )


def _print_response(label: str, response: Any) -> None:
    if response is None:
        print(f"[INFO] {label}: respuesta vacia 204")
        return

    print(f"[INFO] {label}:")
    print(json.dumps(sanitize(response), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
