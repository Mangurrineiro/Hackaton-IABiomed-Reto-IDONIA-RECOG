"""Pipeline de Fase 3: entrega mediante Magic Link de Idonia."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from .idonia_client import IdoniaClient
from .models import PatientCase, Phase3Evidence, now_madrid_iso
from .pipeline_utils import (
    build_evidence_path,
    run_step,
    save_evidence,
    summarize_magic_link_response,
)


logger = logging.getLogger(__name__)


class Phase3DeliveryError(RuntimeError):
    def __init__(self, message: str, evidence: Phase3Evidence) -> None:
        super().__init__(message)
        self.evidence = evidence


@dataclass
class Phase3DeliveryResult:
    evidence: Phase3Evidence
    viewer_url: str
    pin: str
    qr_ascii: str


def run_phase_3_delivery(
    client: IdoniaClient,  # Cliente de Idonia para whoami y /ml.
    patient_case: PatientCase,  # Caso sobre el que se genera el enlace.
    magic_link_password: str | None = None,  # Password adicional opcional.
    evidence_dir: Path = Path("evidence/logs"),  # Carpeta de evidencias JSON.
) -> Phase3DeliveryResult:
    """Ejecuta la Fase 3 y genera evidencia técnica."""

    magic_link_route = patient_case.idonia_magic_link_route
    # La evidencia no guarda el PIN ni la password. 
    # Solo guarda la URL final y un resumen técnico sanitizado de la respuesta de Idonia.
    evidence = Phase3Evidence(
        phase="phase_3_magic_link_delivery",
        status="running",
        patient_dni=patient_case.patient_dni,
        accession_number=patient_case.accession_number,
        magic_link_route=magic_link_route,
        viewer_url="",
        started_at=now_madrid_iso(),
    )

    logger.info("Comenzando Fase 3 de entrega con Magic Link.")
    logger.info("Ruta Magic Link en Idonia: %s", magic_link_route)

    failure: Exception | None = None
    result: Phase3DeliveryResult | None = None

    try:
        # Verificamos que el cliente de Idonia funciona correctamente.
        run_step(evidence, "whoami", client.whoami, logger)

        # PUT /ml crea el Magic Link si no existe. 
        created_magic_link = run_step(
            evidence,
            "create_magic_link",
            lambda: client.create_magic_link(
                route=magic_link_route,
                plain_password=magic_link_password,
                expired_creation_mode="create",
            ),
            logger,
        )

        # GET /ml confirma la disponibilidad del enlace tras la creación.
        confirmed_magic_link = run_step(
            evidence,
            "get_magic_link",
            lambda: client.get_magic_link(
                route=magic_link_route,
                return_expired=True,
            ),
            logger,
        )

        magic_link_item = _get_magic_link_item(confirmed_magic_link or created_magic_link)
        # La URL de entrega se compone con el dominio demo.
        viewer_url = f"https://demo.idonia.com/v/{magic_link_item['URL']}"
        pin = str(magic_link_item["PIN"])
        evidence.viewer_url = viewer_url
        evidence.magic_link_response_summary = summarize_magic_link_response(
            confirmed_magic_link or created_magic_link
        )

        # Generamos QR ASCII para mostrar la URL en consola
        qr_ascii = run_step(
            evidence,
            "render_console_qr",
            lambda: _build_console_qr(viewer_url),
            logger,
        )

        evidence.status = "ok"
        result = Phase3DeliveryResult(
            evidence=evidence,
            viewer_url=viewer_url,
            pin=pin,
            qr_ascii=qr_ascii,
        )
        logger.info("Fase 3 de entrega completada correctamente.")

    except Exception as exc:
        failure = exc
        evidence.status = "failed"
        logger.exception("Fase 3 de entrega fallida.")

    finally:
        evidence.finished_at = now_madrid_iso()
        try:
            # Guardamos la evidencia aunque el pipeline falle
            evidence_path = build_evidence_path(evidence_dir, "phase3")
            evidence.evidence_path = str(evidence_path)
            save_evidence(evidence, evidence_path)
            logger.info("Evidencia guardada en %s", evidence_path)
        except Exception as save_exc:
            logger.exception("No se pudo guardar el JSON de evidencia de Fase 3.")
            if failure is None:
                failure = save_exc

    if failure is not None or result is None:
        path_hint = evidence.evidence_path or str(evidence_dir)
        raise Phase3DeliveryError(
            f"Fase 3 fallida. Ruta de evidencia: {path_hint}", evidence
        ) from failure

    return result


def _get_magic_link_item(response: Any) -> dict[str, Any]:
    """Obtiene el primer Magic Link útil de la respuesta de Idonia."""

    if not isinstance(response, list) or not response:
        raise ValueError("Respuesta Magic Link vacia o inesperada.")

    item = response[0]
    if not isinstance(item, dict) or "URL" not in item or "PIN" not in item:
        raise ValueError("Respuesta Magic Link sin campos URL/PIN.")

    return item


def _build_console_qr(viewer_url: str) -> str:
    """Renderiza un QR ASCII para consola sin crear archivos adicionales."""

    try:
        import qrcode
    except ImportError as exc:
        raise RuntimeError(
            "Falta la dependencia qrcode. Ejecuta pip install -r requirements.txt."
        ) from exc

    qr = qrcode.QRCode(border=1)
    qr.add_data(viewer_url)
    qr.make(fit=True)

    buffer = StringIO()
    qr.print_ascii(out=buffer, tty=False, invert=True)
    return buffer.getvalue()
