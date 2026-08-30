from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import logging
import traceback


HERE = Path(__file__).resolve()

PORTAL = HERE.parents[2]
PROJECT = PORTAL.parent

LOG_ROOT = PROJECT / "logs"


LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def _log_file(component: str) -> Path:
    component = (
        str(component or "pipeline")
        .strip()
        .lower()
        .replace(" ", "_")
    )

    folder = LOG_ROOT / component
    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    day = datetime.now().strftime(
        "%Y-%m-%d"
    )

    return folder / f"{component}_{day}.log"


def get_logger(
    component: str,
    level: str = "DEBUG",
) -> logging.Logger:

    name = f"GIL.{component}"

    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(
        LEVELS.get(
            level.upper(),
            logging.DEBUG,
        )
    )

    formatter = logging.Formatter(
        "%(asctime)s | "
        "%(levelname)-8s | "
        "%(name)s | "
        "%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(
        _log_file(component),
        encoding="utf-8",
    )

    file_handler.setFormatter(
        formatter
    )

    logger.addHandler(
        file_handler
    )

    return logger


def log_event(
    component: str,
    level: str,
    event: str,
    **data,
) -> None:

    logger = get_logger(component)

    payload = {
        "event": event,
        **data,
    }

    message = json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
    )

    log_method = getattr(
        logger,
        level.lower()
        if level.lower() != "warn"
        else "warning",
        logger.info,
    )

    log_method(message)


def log_exception(
    component: str,
    event: str,
    exc: BaseException,
    **data,
) -> None:

    log_event(
        component,
        "ERROR",
        event,
        error=str(exc),
        traceback=traceback.format_exc(),
        **data,
    )
