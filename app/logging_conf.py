import json
import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any, Optional

correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        correlation_id = correlation_id_var.get()
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if correlation_id:
            log_obj["correlation_id"] = correlation_id
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        extra = {k: v for k, v in record.__dict__.items() if k not in (
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs",
            "message", "msg", "name", "pathname", "process",
            "processName", "relativeCreated", "thread", "threadName",
            "exc_info", "exc_text", "stack_info", "getMessage"
        )}
        if extra:
            log_obj["extra"] = extra
        return json.dumps(log_obj, default=str)


def setup_logging(json_format: bool = False, level: int = logging.INFO):
    handler = logging.StreamHandler(sys.stdout)
    if json_format:
        handler.setFormatter(JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def get_correlation_id() -> Optional[str]:
    return correlation_id_var.get()


def set_correlation_id(cid: Optional[str] = None) -> str:
    if cid is None:
        cid = str(uuid.uuid4())[:8]
    correlation_id_var.set(cid)
    return cid


def clear_correlation_id():
    correlation_id_var.set(None)


class CorrelationLogger:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def _log(self, level: int, msg: str, *args, **extra):
        cid = correlation_id_var.get()
        if cid:
            extra["correlation_id"] = cid
        self.logger.log(level, msg, *args, extra=extra)

    def debug(self, msg: str, *args, **extra):
        self._log(logging.DEBUG, msg, *args, **extra)

    def info(self, msg: str, *args, **extra):
        self._log(logging.INFO, msg, *args, **extra)

    def warning(self, msg: str, *args, **extra):
        self._log(logging.WARNING, msg, *args, **extra)

    def error(self, msg: str, *args, **extra):
        self._log(logging.ERROR, msg, *args, **extra)

    def critical(self, msg: str, *args, **extra):
        self._log(logging.CRITICAL, msg, *args, **extra)

    def exception(self, msg: str, *args, **extra):
        self._log(logging.ERROR, msg, *args, **extra)


def get_logger(name: str) -> CorrelationLogger:
    return CorrelationLogger(logging.getLogger(name))