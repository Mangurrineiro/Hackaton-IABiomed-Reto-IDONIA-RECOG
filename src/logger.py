"""Configuración centralizada de logs para scripts y pipelines."""

from __future__ import annotations

import logging
import sys


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging() -> logging.Logger:
    """Configura logs por consola siempre en nivel INFO."""

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Usamos el root logger para que todos los módulos compartan formato y nivel.
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Si ya había handlers configurados, solo actualizamos formato/nivel.
    if root_logger.handlers:
        for handler in root_logger.handlers:
            handler.setLevel(logging.INFO)
            handler.setFormatter(formatter)
    else:
        # Los logs salen por consola; las evidencias técnicas se guardan aparte en JSON.
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    # Evita ruido interno de requests/urllib3 en la demo.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    return logging.getLogger("idonia_recog_hackathon")
