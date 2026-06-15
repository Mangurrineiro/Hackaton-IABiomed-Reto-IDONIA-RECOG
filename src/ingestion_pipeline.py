"""Pipeline de Fase 1: ingesta de estudio DICOM e informe original en Idonia."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .idonia_client import IdoniaClient
from .models import PatientCase, Phase1Evidence, now_madrid_iso
from .pipeline_utils import (
    build_evidence_path,
    run_step,
    sanitize,
    save_evidence,
)


logger = logging.getLogger(__name__)


DICOM_MULTIPART_FILE_NAME = "estudio.dcm" # Nombre usado en cada parte multipart a la hora de subir el estudio


class Phase1IngestionError(RuntimeError):
    def __init__(self, message: str, evidence: Phase1Evidence) -> None:
        super().__init__(message)
        self.evidence = evidence


def run_phase_1_ingestion(
    client: IdoniaClient,  # Cliente de Idonia para autenticación y subida.
    patient_case: PatientCase,  # Datos DICOM que construyen la ruta técnica.
    dicom_destination: str,  # Endpoint destino del estudio DICOM.
    report_destination: str,  # Endpoint destino del informe original.
    study_path: Path,  # Carpeta local que contiene las instancias DICOM.
    report_path: Path,  # PDF original que se adjunta al caso.
    evidence_dir: Path = Path("evidence/logs"),  # Carpeta de evidencias JSON.
) -> Phase1Evidence:
    """Ejecuta la Fase 1 y genera evidencia técnica."""

    # La evidencia se crea antes de llamar a APIs para que cualquier fallo
    # posterior pueda dejar un JSON útil para auditoría y demo.
    evidence = Phase1Evidence(
        phase="phase_1_idonia_ingestion",
        status="running",
        patient_dni=patient_case.patient_dni,
        accession_number=patient_case.accession_number,
        expected_study_route=patient_case.idonia_case_route,
        expected_magic_link_route=patient_case.idonia_magic_link_route,
        started_at=now_madrid_iso(),
    )

    logger.info("Comenzando Fase 1 de ingesta en Idonia. DICOMPatientID: %s", patient_case.patient_dni)
    logger.info("Ruta esperada para el caso en Idonia: %s", patient_case.idonia_case_route)
    logger.info("Ruta esperada para Magic Link en Idonia: %s", patient_case.idonia_magic_link_route)

    failure: Exception | None = None

    try:
        # Verificamos que el cliente de Idonia funciona correctamente
        run_step(evidence, "whoami", client.whoami, logger)

        # Subimos todas las instancias DICOM de la carpeta al mismo destino.
        # El detalle por fichero queda en study_upload_response.
        study_response = run_step(
            evidence,
            "upload_study",
            lambda: _upload_study(
                client=client,
                dicom_destination=dicom_destination,
                study_path=study_path,
                patient_case=patient_case,
            ),
            logger,
        )
        evidence.study_upload_response = sanitize(study_response)

        # El informe original se sube a la misma ruta técnica del caso.
        report_response = run_step(
            evidence,
            "upload_report",
            lambda: client.upload_file_to_destination(
                report_destination,
                report_path,
                patient_case.patient_dni,
                patient_case.accession_number,
                patient_case.study_description,
            ),
            logger,
        )
        evidence.report_upload_response = sanitize(report_response)
        evidence.status = "ok"
        logger.info("Fase 1 de Idonia completada correctamente.")

    except Exception as exc:
        failure = exc
        evidence.status = "failed"
        logger.exception("Fase 1 de ingesta en Idonia fallida.")

    finally:
        evidence.finished_at = now_madrid_iso()
        try:
            # Guardamos la evidencia aunque el pipeline falle
            evidence_path = build_evidence_path(evidence_dir, "phase1")
            evidence.evidence_path = str(evidence_path)
            save_evidence(evidence, evidence_path)
            logger.info("Evidencia guardada en %s", evidence_path)
        except Exception as save_exc:
            logger.exception("No se pudo guardar el JSON de evidencia de Fase 1.")
            if failure is None:
                failure = save_exc

    if failure is not None:
        path_hint = evidence.evidence_path or str(evidence_dir)
        raise Phase1IngestionError(
            f"Fase 1 fallida. Ruta de evidencia: {path_hint}", evidence
        ) from failure

    return evidence


def _upload_study(
    client: IdoniaClient,
    dicom_destination: str,
    study_path: Path,
    patient_case: PatientCase,
) -> dict[str, Any]:
    study_files = _collect_study_files(study_path)
    upload_results = []

    # Idonia devuelve un array de file_uuid por cada POST. Guardamos todos los
    # UUIDs para poder demostrar cuántas instancias se inyectaron realmente.
    for index, dicom_file in enumerate(study_files, start=1):
        logger.info(
            "Subiendo DICOM %s/%s a Idonia: %s",
            index,
            len(study_files),
            dicom_file,
        )
        file_uuids = client.upload_file_to_destination(
            dicom_destination,
            dicom_file,
            patient_case.patient_dni,
            patient_case.accession_number,
            patient_case.study_description,
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
    """Devuelve los DICOMs a subir en orden estable para ejecuciones reproducibles."""

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
