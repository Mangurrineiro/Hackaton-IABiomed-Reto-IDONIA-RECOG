"""Prueba manual de subida de informe a Idonia."""

from __future__ import annotations

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
        # Subimos el informe
        response = client.upload_file_to_destination(
            destination=settings.idonia_report_destination,
            file_path=settings.report_file_path,
            patient_id=patient_case.patient_dni,
            accession_number=patient_case.accession_number,
            study_description=patient_case.study_description,
        )
    except Exception as exc:
        print(f"[ERROR] Subida de informe fallida: {mask_sensitive_text(str(exc))}")
        return 1

    print(f"[OK] Informe subido a {settings.idonia_report_destination}")
    print(f"[OK] DICOMPatientID: {patient_case.patient_dni}")
    print(f"[OK] file_uuid(s): {response}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
