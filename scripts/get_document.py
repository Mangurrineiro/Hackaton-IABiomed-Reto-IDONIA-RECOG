"""Script de prueba para obtener un documento desde Idonia."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_settings
from src.idonia_client import IdoniaClient
from src.logger import configure_logging
from src.models import PatientCase
from src.pipeline_utils import mask_sensitive_text


def main() -> int:
    args = _parse_args()

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
        # Obtenemos el documento asociado a la ruta técnica del caso
        route = _build_route(patient_case, route=args.route, suffix=args.suffix)
        response = client.get_file(route)
        output_path = _save_document(response.content, args.output)
    except Exception as exc:
        print(f"[ERROR] Obtencion de documento fallida: {mask_sensitive_text(str(exc))}")
        return 1

    print("[OK] Documento obtenido desde Idonia")
    print(f"[OK] route: {route}")
    print(f"[OK] status_code: {response.status_code}")
    print(f"[OK] content-type: {response.headers.get('content-type', '<empty>')}")
    print(f"[OK] content-disposition: {response.headers.get('content-disposition', '<empty>')}")
    print(f"[OK] bytes: {len(response.content)}")
    if output_path is not None:
        print(f"[OK] saved_to: {output_path}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prueba aislada de GET /file en Idonia."
    )
    parser.add_argument(
        "--route",
        help="Ruta exacta a consultar. Si se informa, reemplaza la ruta del caso.",
    )
    parser.add_argument(
        "--suffix",
        help="Sufijo a anadir a la ruta del caso, por ejemplo informe_rm_rodilla.",
    )
    parser.add_argument(
        "--output",
        help="Ruta local donde guardar el documento descargado.",
    )
    return parser.parse_args()


def _build_route(
    patient_case: PatientCase,
    route: str | None,
    suffix: str | None,
) -> str:
    if route and route.strip(" /"):
        return route.strip(" /")

    base_route = patient_case.idonia_case_route
    if suffix and suffix.strip(" /"):
        return f"{base_route}/{suffix.strip(' /')}"

    return base_route


def _save_document(content: bytes, output: str | None) -> Path | None:
    if output is None:
        return None

    output_path = Path(output).expanduser()
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    return output_path


if __name__ == "__main__":
    raise SystemExit(main())
