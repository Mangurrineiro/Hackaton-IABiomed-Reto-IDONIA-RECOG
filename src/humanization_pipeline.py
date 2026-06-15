"""Pipeline de Fase 2: humanizacion de informe con Recog y subida a Idonia."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from .idonia_client import IdoniaClient
from .models import PatientCase, Phase2Evidence, now_madrid_iso
from .pipeline_utils import build_evidence_path, run_step, sanitize, save_evidence
from .recog_client import RecogClient


logger = logging.getLogger(__name__)


class Phase2HumanizationError(RuntimeError):
    def __init__(self, message: str, evidence: Phase2Evidence) -> None:
        super().__init__(message)
        self.evidence = evidence


def run_phase_2_humanization(
    idonia_client: IdoniaClient,
    recog_client: RecogClient,
    patient_case: PatientCase,
    report_destination: str,
    humanized_report_path: Path,
    original_report_file_name: str,
    evidence_dir: Path = Path("evidence/logs"),
) -> Phase2Evidence:
    """Ejecuta la Fase 2 y genera evidencia técnica."""

    # GET /file requiere la ruta exacta del documento. 
    # Se compone de la ruta del caso más el nombre del PDF original que fue subido en Fase 1.
    source_route = f"{patient_case.idonia_case_route}/{original_report_file_name}"
    expected_humanized_route = patient_case.idonia_case_route

    # La evidencia registra rutas, tamaños y resultados técnicos, pero evita guardar texto clínico extraído del informe.
    evidence = Phase2Evidence(
        phase="phase_2_recog_humanization",
        status="running",
        patient_dni=patient_case.patient_dni,
        accession_number=patient_case.accession_number,
        source_report_route=source_route,
        dicom_study_description=patient_case.study_description,
        expected_humanized_report_route=expected_humanized_route,
        humanized_report_path=str(humanized_report_path),
        started_at=now_madrid_iso(),
    )

    logger.info("Comenzando Fase 2 de humanizacion con Recog.")
    logger.info("Ruta origen del informe en Idonia: %s", source_route)
    logger.info("Ruta esperada del informe humanizado en Idonia: %s", expected_humanized_route)

    failure: Exception | None = None

    try:
        # Verificamos que el cliente de Idonia funciona correctamente
        run_step(evidence, "whoami", idonia_client.whoami, logger)

        # Descargamos desde Idonia el informe original asociado a la ruta completa del documento
        original_report = run_step(
            evidence,
            "download_original_report",
            lambda: _download_original_report(idonia_client, source_route),
            logger,
        )

        # Extraemos texto del PDF original para enviarlo a Recog
        original_report_text = run_step(
            evidence,
            "extract_report_text",
            lambda: _extract_pdf_text(original_report),
            logger,
        )

        # Invocamos Recog y obtenemos el PDF humanizado. 
        # Solo persistimos el tamaño del PDF devuelto, no el contenido clínico ni el texto fuente.
        humanized_report = run_step(
            evidence,
            "process_with_recog",
            lambda: recog_client.humanize_text(original_report_text),
            logger,
        )
        evidence.recog_response_summary = {"pdf_bytes": len(humanized_report)}

        # Validamos que Recog haya devuelto un PDF con texto extraíble antes de subirlo a Idonia
        run_step(
            evidence,
            "validate_humanized_report",
            lambda: _validate_pdf_with_text(humanized_report, "PDF humanizado de Recog"),
            logger,
        )

        # Guardamos localmente el PDF humanizado devuelto por Recog
        run_step(
            evidence,
            "save_humanized_report",
            lambda: _save_pdf(humanized_report, humanized_report_path),
            logger,
        )

        # Subimos a Idonia el informe humanizado dentro del mismo caso técnico.
        upload_response = run_step(
            evidence,
            "upload_humanized_report",
            lambda: idonia_client.upload_file_to_destination(
                report_destination,
                humanized_report_path,
                patient_case.patient_dni,
                patient_case.accession_number,
                patient_case.study_description,
            ),
            logger,
        )
        evidence.humanized_upload_response = sanitize(upload_response)
        evidence.status = "ok"
        logger.info("Fase 2 de humanizacion completada correctamente.")

    except Exception as exc:
        failure = exc
        evidence.status = "failed"
        logger.exception("Fase 2 de humanizacion fallida.")

    finally:
        evidence.finished_at = now_madrid_iso()
        try:
            # Guardamos la evidencia aunque el pipeline falle
            evidence_path = build_evidence_path(evidence_dir, "phase2")
            evidence.evidence_path = str(evidence_path)
            save_evidence(evidence, evidence_path)
            logger.info("Evidencia guardada en %s", evidence_path)
        except Exception as save_exc:
            logger.exception("No se pudo guardar el JSON de evidencia de Fase 2.")
            if failure is None:
                failure = save_exc

    if failure is not None:
        path_hint = evidence.evidence_path or str(evidence_dir)
        raise Phase2HumanizationError(
            f"Fase 2 fallida. Ruta de evidencia: {path_hint}", evidence
        ) from failure

    return evidence


def _download_original_report(idonia_client: IdoniaClient, source_route: str) -> bytes:
    """Descarga el PDF original desde Idonia y falla si no hay contenido."""

    try:
        response = idonia_client.get_file(source_route)
    except Exception as exc:
        raise RuntimeError(
            f"No se pudo obtener el informe original desde Idonia en la ruta {source_route}: {exc}"
        ) from exc

    if not response.content:
        raise RuntimeError(
            f"Idonia devolvio el informe original sin contenido en la ruta {source_route}."
        )

    return response.content


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extrae texto del PDF original."""

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        page_texts = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise ValueError(f"No se pudo leer el PDF original descargado de Idonia: {exc}") from exc

    text = "\n\n".join(page_texts).strip()
    if not text:
        raise ValueError("No se pudo extraer texto del PDF original.")
    return text


def _validate_pdf_with_text(pdf_bytes: bytes, label: str) -> dict[str, int]:
    """Verifica que el PDF generado por Recog sea legible antes de subirlo."""

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        page_texts = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise ValueError(f"No se pudo leer {label}: {exc}") from exc

    text = "\n\n".join(page_texts).strip()
    pages = len(reader.pages)
    if pages == 0:
        raise ValueError(f"{label} no contiene paginas.")
    if not text:
        raise ValueError(
            f"{label} no contiene texto extraible. "
            "No se subira a Idonia para evitar inyectar un informe no legible."
        )

    return {"pages": pages, "characters": len(text)}


def _save_pdf(pdf_bytes: bytes, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(pdf_bytes)
    return output_path
