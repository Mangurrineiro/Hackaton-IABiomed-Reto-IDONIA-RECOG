"""Script de prueba para la subida de estudios a Idonia."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_settings
from src.idonia_client import IdoniaClient
from src.ingestion_pipeline import DICOM_MULTIPART_FILE_NAME
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
        study_path = _resolve_file_path(args.file, settings.study_file_path)

        # Subimos el estudio usando la ruta técnica del caso
        response = _upload_study(
            client=client,
            destination=settings.idonia_dicom_destination,
            study_path=study_path,
            patient_case=patient_case,
        )
    except Exception as exc:
        print(f"[ERROR] Subida de estudio fallida: {mask_sensitive_text(str(exc))}")
        return 1

    print(f"[OK] Subido estudio a {settings.idonia_dicom_destination}")
    print(f"[OK] DICOMPatientID: {patient_case.patient_dni}")
    print(f"[OK] route: {patient_case.idonia_case_route}")
    print(f"[OK] file_path: {study_path}")
    print(f"[OK] response: {response}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prueba aislada de subida de estudio a Idonia."
    )
    parser.add_argument(
        "--file",
        help="Carpeta de DICOMs a subir. Si no se informa, usa STUDY_FILE_PATH.",
    )
    return parser.parse_args()


def _resolve_file_path(value: str | None, fallback: Path) -> Path:
    if value is None:
        return fallback

    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _upload_study(
    client: IdoniaClient,
    destination: str,
    study_path: Path,
    patient_case: PatientCase,
) -> object:
    study_files = _collect_study_files(study_path)
    upload_results = []

    for index, dicom_file in enumerate(study_files, start=1):
        print(f"[INFO] Subiendo DICOM {index}/{len(study_files)}: {dicom_file}")
        file_uuids = client.upload_file_to_destination(
            destination=destination,
            file_path=dicom_file,
            patient_id=patient_case.patient_dni,
            accession_number=patient_case.accession_number,
            study_description=patient_case.study_description,
            upload_file_name=DICOM_MULTIPART_FILE_NAME,
        )
        upload_results.append(
            {
                "local_file": str(dicom_file),
                "request_file_name": DICOM_MULTIPART_FILE_NAME,
                "file_uuids": file_uuids,
            }
        )

    return {
        "uploaded_files": len(upload_results),
        "request_file_name": DICOM_MULTIPART_FILE_NAME,
        "files": upload_results,
    }


def _collect_study_files(study_path: Path) -> list[Path]:
    if not study_path.exists():
        raise FileNotFoundError(f"No existe la carpeta del estudio DICOM: {study_path}")

    if not study_path.is_dir():
        raise NotADirectoryError(f"STUDY_FILE_PATH debe ser una carpeta con DICOMs: {study_path}")

    study_files = sorted(
        path
        for path in study_path.rglob("*")
        if path.is_file() and not path.name.startswith(".")
    )
    if not study_files:
        raise FileNotFoundError(f"No hay archivos DICOM en la carpeta: {study_path}")

    return study_files


if __name__ == "__main__":
    raise SystemExit(main())
