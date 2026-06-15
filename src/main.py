"""CLI principal para ejecutar las tres fases del reto."""

from __future__ import annotations

import argparse

from .config import Settings, get_settings
from .logger import configure_logging
from .models import PatientCase


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        settings = get_settings()
    except Exception as exc:
        print(f"[ERROR] Configuracion invalida: {exc}")
        return 1

    configure_logging()

    if args.command == "phase1":
        return _run_phase1_command(settings)
    if args.command == "phase2":
        return _run_phase2_command(settings)
    if args.command == "phase3":
        return _run_phase3_command(settings)

    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Idonia + Recog Hackathon - Fases 1, 2 y 3"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("phase1", help="Ejecuta la ingesta en Idonia")
    subparsers.add_parser("phase2", help="Ejecuta la humanizacion con Recog")
    subparsers.add_parser("phase3", help="Ejecuta la entrega con Magic Link")
    return parser


def _run_phase1_command(settings: Settings) -> int:
    try:
        from .ingestion_pipeline import Phase1IngestionError, run_phase_1_ingestion

        client = _build_idonia_client(settings)
    except ImportError as exc:
        return _dependency_error(exc)

    patient_case = _build_patient_case(settings)
    try:
        evidence = run_phase_1_ingestion(
            client=client,
            patient_case=patient_case,
            dicom_destination=settings.idonia_dicom_destination,
            report_destination=settings.idonia_report_destination,
            study_path=settings.study_file_path,
            report_path=settings.report_file_path,
        )
    except Phase1IngestionError as exc:
        path_hint = exc.evidence.evidence_path or "evidence/logs/"
        print(f"[ERROR] Fase 1 fallida. Revisa {path_hint}")
        return 1

    print("[OK] Autenticacion con Idonia correcta")
    print(f"[OK] DICOMPatientID: {patient_case.patient_dni}")
    print(f"[OK] Estudio subido a {settings.idonia_dicom_destination}")
    if isinstance(evidence.study_upload_response, dict):
        print(f"[OK] DICOMs subidos: {evidence.study_upload_response.get('uploaded_files')}")
    print(f"[OK] Informe original subido a {settings.idonia_report_destination}")
    print(f"[OK] Evidencia guardada en {evidence.evidence_path}")
    return 0


def _run_phase2_command(settings: Settings) -> int:
    try:
        from .humanization_pipeline import Phase2HumanizationError, run_phase_2_humanization

        idonia_client = _build_idonia_client(settings)
        recog_client = _build_recog_client(settings)
    except ImportError as exc:
        return _dependency_error(exc)
    except RuntimeError as exc:
        print(f"[ERROR] Configuracion invalida para Recog: {exc}")
        return 1

    patient_case = _build_patient_case(settings)

    try:
        evidence = run_phase_2_humanization(
            idonia_client=idonia_client,
            recog_client=recog_client,
            patient_case=patient_case,
            report_destination=settings.idonia_report_destination,
            humanized_report_path=settings.humanized_report_file_path,
            original_report_file_name=settings.report_file_path.name,
        )
    except Phase2HumanizationError as exc:
        path_hint = exc.evidence.evidence_path or "evidence/logs/"
        print(f"[ERROR] Fase 2 fallida. Revisa {path_hint}")
        return 1

    print("[OK] Informe original descargado desde Idonia")
    print("[OK] Informe humanizado generado con Recog")
    print(f"[OK] PDF humanizado guardado en {evidence.humanized_report_path}")
    print(f"[OK] Informe humanizado subido a {settings.idonia_report_destination}")
    print(f"[OK] Evidencia guardada en {evidence.evidence_path}")
    return 0


def _run_phase3_command(settings: Settings) -> int:
    try:
        from .delivery_pipeline import Phase3DeliveryError, run_phase_3_delivery

        idonia_client = _build_idonia_client(settings)
    except ImportError as exc:
        return _dependency_error(exc)

    patient_case = _build_patient_case(settings)
    try:
        result = run_phase_3_delivery(
            client=idonia_client,
            patient_case=patient_case,
            magic_link_password=_get_optional_magic_link_password(settings),
        )
    except Phase3DeliveryError as exc:
        path_hint = exc.evidence.evidence_path or "evidence/logs/"
        print(f"[ERROR] Fase 3 fallida. Revisa {path_hint}")
        return 1

    print("[OK] Autenticacion con Idonia correcta")
    print(f"[OK] Ruta Magic Link: {patient_case.idonia_magic_link_route}")
    print(f"[OK] URL Magic Link: {result.viewer_url}")
    print(f"[OK] PIN: {result.pin}")
    print()
    print(result.qr_ascii)
    print(f"[OK] Evidencia guardada en {result.evidence.evidence_path}")
    return 0


def _build_idonia_client(settings: Settings):
    from .idonia_client import IdoniaClient

    return IdoniaClient(
        base_url=settings.idonia_base_url,
        api_key=settings.idonia_api_key.get_secret_value(),
        api_secret=settings.idonia_api_secret.get_secret_value(),
    )


def _build_recog_client(settings: Settings):
    from .recog_client import RecogClient

    return RecogClient(
        base_url=settings.recog_base_url,
        api_key=settings.recog_api_key.get_secret_value(),
    )


def _get_optional_magic_link_password(settings: Settings) -> str | None:
    if settings.idonia_magic_link_password is None:
        return None
    return settings.idonia_magic_link_password.get_secret_value()


def _build_patient_case(settings: Settings) -> PatientCase:
    return PatientCase(
        patient_dni=settings.patient_dni,
        accession_number=settings.case_accession_number,
        study_description=settings.case_study_description,
    )


def _dependency_error(exc: ImportError) -> int:
    dependency = exc.name or str(exc)
    print(
        "[ERROR] Falta una dependencia para esta fase: "
        f"{dependency}. Ejecuta pip install -r requirements.txt"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
