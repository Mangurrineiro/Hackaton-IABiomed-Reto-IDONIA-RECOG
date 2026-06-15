"""Utilidades para ejecutar fases del pipeline desde la demo Streamlit."""

from __future__ import annotations

import io
import json
import logging
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pypdf import PdfReader  # noqa: E402

from src.config import Settings, get_settings  # noqa: E402
from src.delivery_pipeline import Phase3DeliveryError, run_phase_3_delivery  # noqa: E402
from src.humanization_pipeline import (  # noqa: E402
    Phase2HumanizationError,
    run_phase_2_humanization,
)
from src.idonia_client import IdoniaClient  # noqa: E402
from src.ingestion_pipeline import Phase1IngestionError, run_phase_1_ingestion  # noqa: E402
from src.models import MADRID_TIMEZONE, PatientCase  # noqa: E402
from src.recog_client import RecogClient  # noqa: E402


EVIDENCE_DIR = PROJECT_ROOT / "evidence" / "logs"
CONNECTION_ERROR_BASE_URL = "http://127.0.0.1:9"
MISSING_REPORT_FILE_NAME = "informe_inventado_no_existe.pdf"
MISSING_STUDY_PATIENT_DNI = "PACIENTE-DEMO-INEXISTENTE"
MISSING_STUDY_ACCESSION_NUMBER = "ESTUDIO-DEMO-INEXISTENTE"
MISSING_STUDY_DESCRIPTION = "RM Demo Inexistente"
PHASE_PREFIXES = {
    "phase1": "phase1",
    "phase2": "phase2",
    "phase3": "phase3",
}


@dataclass
class PhaseRunResult:
    phase_name: str
    success: bool
    return_code: int
    stdout: str
    stderr: str
    logs: str
    evidence_path: Path | None
    evidence_json: dict[str, Any] | None
    error_message: str | None = None
    viewer_url: str | None = None
    pin: str | None = None
    qr_ascii: str | None = None


def run_phase(
    phase_name: str,
    idonia_base_url_override: str | None = None,
    recog_base_url_override: str | None = None,
    original_report_file_name_override: str | None = None,
    patient_dni_override: str | None = None,
    accession_number_override: str | None = None,
    study_description_override: str | None = None,
) -> PhaseRunResult:
    """Ejecuta una fase y devuelve una salida sanitizada para la UI."""

    if phase_name not in PHASE_PREFIXES:
        raise ValueError(f"Fase no soportada: {phase_name}")

    started_at = datetime.now(MADRID_TIMEZONE)
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    log_buffer = io.StringIO()
    log_handler = logging.StreamHandler(log_buffer)
    log_handler.setLevel(logging.INFO)
    log_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root_logger = logging.getLogger()
    previous_level = root_logger.level
    root_logger.addHandler(log_handler)
    root_logger.setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    evidence_obj: Any = None
    viewer_url: str | None = None
    pin: str | None = None
    qr_ascii: str | None = None
    error_message: str | None = None
    success = False

    settings: Settings | None = None
    try:
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            settings = get_settings()
            if idonia_base_url_override is not None:
                settings = settings.model_copy(
                    update={"idonia_base_url": idonia_base_url_override.rstrip("/")}
                )
            if recog_base_url_override is not None:
                settings = settings.model_copy(
                    update={"recog_base_url": recog_base_url_override.rstrip("/")}
                )
            evidence_obj, viewer_url, pin, qr_ascii = _execute_phase(
                phase_name=phase_name,
                settings=settings,
                original_report_file_name_override=original_report_file_name_override,
                patient_dni_override=patient_dni_override,
                accession_number_override=accession_number_override,
                study_description_override=study_description_override,
            )
            success = True
    except (Phase1IngestionError, Phase2HumanizationError, Phase3DeliveryError) as exc:
        evidence_obj = getattr(exc, "evidence", None)
        error_message = str(exc)
    except Exception as exc:  # Streamlit debe mostrar el fallo, no romper la demo.
        error_message = str(exc)
    finally:
        root_logger.removeHandler(log_handler)
        root_logger.setLevel(previous_level)

    evidence_path = _evidence_path_from_obj(evidence_obj)
    evidence_json = _evidence_json_from_obj(evidence_obj)

    if evidence_path is None:
        evidence_path = find_latest_evidence(PHASE_PREFIXES[phase_name], since=started_at)

    if evidence_json is None and evidence_path is not None:
        evidence_json = load_json(evidence_path)

    sanitizer_settings = settings or _try_get_settings()
    stdout_text = sanitize_text(stdout_buffer.getvalue(), sanitizer_settings)
    stderr_text = sanitize_text(stderr_buffer.getvalue(), sanitizer_settings)
    logs_text = sanitize_text(log_buffer.getvalue(), sanitizer_settings)
    error_text = sanitize_text(error_message, sanitizer_settings) if error_message else None

    return PhaseRunResult(
        phase_name=phase_name,
        success=success,
        return_code=0 if success else 1,
        stdout=stdout_text,
        stderr=stderr_text,
        logs=logs_text,
        evidence_path=evidence_path,
        evidence_json=evidence_json,
        error_message=error_text,
        viewer_url=viewer_url,
        pin=pin,
        qr_ascii=qr_ascii,
    )


def _execute_phase(
    phase_name: str,
    settings: Settings,
    original_report_file_name_override: str | None = None,
    patient_dni_override: str | None = None,
    accession_number_override: str | None = None,
    study_description_override: str | None = None,
) -> tuple[Any, str | None, str | None, str | None]:
    idonia_client = _build_idonia_client(settings)
    patient_case = _build_patient_case(
        settings=settings,
        patient_dni_override=patient_dni_override,
        accession_number_override=accession_number_override,
        study_description_override=study_description_override,
    )

    if phase_name == "phase1":
        evidence = run_phase_1_ingestion(
            client=idonia_client,
            patient_case=patient_case,
            dicom_destination=settings.idonia_dicom_destination,
            report_destination=settings.idonia_report_destination,
            study_path=settings.study_file_path,
            report_path=settings.report_file_path,
            evidence_dir=EVIDENCE_DIR,
        )
        return evidence, None, None, None

    if phase_name == "phase2":
        recog_client = _build_recog_client(settings)
        evidence = run_phase_2_humanization(
            idonia_client=idonia_client,
            recog_client=recog_client,
            patient_case=patient_case,
            report_destination=settings.idonia_report_destination,
            humanized_report_path=settings.humanized_report_file_path,
            original_report_file_name=(
                original_report_file_name_override or settings.report_file_path.name
            ),
            evidence_dir=EVIDENCE_DIR,
        )
        return evidence, None, None, None

    result = run_phase_3_delivery(
        client=idonia_client,
        patient_case=patient_case,
        magic_link_password=_get_optional_magic_link_password(settings),
        evidence_dir=EVIDENCE_DIR,
    )
    return result.evidence, result.viewer_url, result.pin, result.qr_ascii


def _build_idonia_client(settings: Settings) -> IdoniaClient:
    return IdoniaClient(
        base_url=settings.idonia_base_url,
        api_key=settings.idonia_api_key.get_secret_value(),
        api_secret=settings.idonia_api_secret.get_secret_value(),
    )


def _build_recog_client(settings: Settings) -> RecogClient:
    return RecogClient(
        base_url=settings.recog_base_url,
        api_key=settings.recog_api_key.get_secret_value(),
    )


def _build_patient_case(
    settings: Settings,
    patient_dni_override: str | None = None,
    accession_number_override: str | None = None,
    study_description_override: str | None = None,
) -> PatientCase:
    return PatientCase(
        patient_dni=patient_dni_override or settings.patient_dni,
        accession_number=accession_number_override or settings.case_accession_number,
        study_description=study_description_override or settings.case_study_description,
    )


def _get_optional_magic_link_password(settings: Settings) -> str | None:
    if settings.idonia_magic_link_password is None:
        return None
    return settings.idonia_magic_link_password.get_secret_value()


def find_latest_evidence(
    phase_prefix: str,
    since: datetime | None = None,
) -> Path | None:
    files = sorted(
        EVIDENCE_DIR.glob(f"{phase_prefix}_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not files:
        return None

    if since is not None:
        recent_files = [
            path
            for path in files
            if datetime.fromtimestamp(path.stat().st_mtime, MADRID_TIMEZONE) >= since
        ]
        if recent_files:
            return recent_files[0]
        return None

    return files[0]


def latest_evidence_for_phase(phase_name: str) -> Path | None:
    prefix = PHASE_PREFIXES.get(phase_name)
    if prefix is None:
        return None
    return find_latest_evidence(prefix)


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as file_handle:
            data = json.load(file_handle)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else {"value": data}


def safe_read_file(path: Path, max_chars: int = 4000) -> str:
    try:
        return path.read_text(encoding="utf-8")[:max_chars]
    except OSError as exc:
        return f"No se pudo leer el archivo: {exc}"


def extract_pdf_preview(path: Path, max_chars: int = 800) -> dict[str, Any]:
    preview: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else None,
        "pages": None,
        "text_preview": "",
        "error": None,
    }
    if not path.exists():
        preview["error"] = "El archivo no existe todavia."
        return preview

    try:
        reader = PdfReader(str(path))
        page_texts = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(page_texts).strip()
        preview["pages"] = len(reader.pages)
        preview["text_preview"] = text[:max_chars]
    except Exception as exc:
        preview["error"] = f"No se pudo extraer preview del PDF: {exc}"

    return preview


def generate_qr_svg_data_uri(url: str) -> str | None:
    try:
        import base64

        import qrcode
        import qrcode.image.svg
    except ImportError:
        return None

    qr = qrcode.QRCode(border=2)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buffer = io.BytesIO()
    image.save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def sanitize_text(value: str | None, settings: Settings | None = None) -> str:
    if not value:
        return ""

    sanitized = value
    for secret_value in _secret_values(settings):
        sanitized = sanitized.replace(secret_value, "***")

    sanitized = re.sub(
        r"(Bearer\s+)[A-Za-z0-9._~+/=-]+",
        r"\1***",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
        "***",
        sanitized,
    )
    sanitized = re.sub(
        r"(X-API-Key\s*[:=]\s*)[^\s,;]+",
        r"\1***",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"((?:api[_-]?key|api[_-]?secret|password)\s*[:=]\s*)[^\s,;]+",
        r"\1***",
        sanitized,
        flags=re.IGNORECASE,
    )
    return _compact_project_paths_in_text(sanitized)


def _compact_project_paths_in_text(value: str) -> str:
    root_backslash = str(PROJECT_ROOT)
    root_slash = PROJECT_ROOT.as_posix()
    compacted = value.replace(root_backslash + "\\", "")
    compacted = compacted.replace(root_backslash + "/", "")
    compacted = compacted.replace(root_slash + "/", "")
    compacted = compacted.replace(root_backslash, ".")
    compacted = compacted.replace(root_slash, ".")
    return compacted.replace("\\", "/")


def _secret_values(settings: Settings | None) -> list[str]:
    if settings is None:
        return []

    values = [
        settings.idonia_api_key.get_secret_value(),
        settings.idonia_api_secret.get_secret_value(),
        settings.recog_api_key.get_secret_value(),
    ]
    if settings.idonia_magic_link_password is not None:
        values.append(settings.idonia_magic_link_password.get_secret_value())
    return [value for value in values if value]


def _try_get_settings() -> Settings | None:
    try:
        return get_settings()
    except Exception:
        return None


def _evidence_path_from_obj(evidence_obj: Any) -> Path | None:
    evidence_path = getattr(evidence_obj, "evidence_path", None)
    if not evidence_path:
        return None
    path = Path(evidence_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _evidence_json_from_obj(evidence_obj: Any) -> dict[str, Any] | None:
    if evidence_obj is None:
        return None
    if hasattr(evidence_obj, "model_dump"):
        return evidence_obj.model_dump(mode="json", exclude_none=True)
    if isinstance(evidence_obj, dict):
        return evidence_obj
    return None
