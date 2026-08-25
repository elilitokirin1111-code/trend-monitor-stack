"""Structured logging: correlation ID injection and optional JSON output.

Keeps the existing colored console formatter as the default; when
``HOTSPOT_STRUCTURED_LOGS=1`` is set, a JSON formatter is used instead so
logs can be shipped to a collector. A logging filter injects the current
correlation ID (from the middleware context variable) into every record.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

from app.config import settings


class CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from app.middleware.correlation import current_correlation_id

            record.correlation_id = current_correlation_id() or "-"
        except Exception:  # noqa: BLE001 - logging must never raise
            record.correlation_id = "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": getattr(record, "correlation_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器"""

    COLORS = {
        "DEBUG": "\033[90m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"
    GRAY = "\033[90m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        time_str = f"{self.GRAY}{self.formatTime(record, '%H:%M:%S')}{self.RESET}"
        message = record.getMessage()
        message = self._format_source_name(message, record.levelname)
        icon = self._get_icon(record.levelname, record.getMessage())
        correlation = getattr(record, "correlation_id", None)
        correlation_part = (
            f"{self.GRAY}[{correlation[:8]}]{self.RESET} "
            if correlation and correlation != "-"
            else ""
        )
        return f"{time_str} {correlation_part}{icon} {message}"

    def _format_source_name(self, message: str, level: str) -> str:
        match = re.match(r"\[([^\]]+)\]\s*(.*)", message)
        if match:
            source_name = match.group(1)
            rest_msg = match.group(2)
            if level == "ERROR":
                return (
                    f"{self.CYAN}[{source_name}]{self.RESET} "
                    f"{self.RED}{rest_msg}{self.RESET}"
                )
            if "成功" in rest_msg:
                return (
                    f"{self.CYAN}[{source_name}]{self.RESET} "
                    f"{self.GREEN}{rest_msg}{self.RESET}"
                )
            return f"{self.CYAN}[{source_name}]{self.RESET} {rest_msg}"
        return message

    def _get_icon(self, level: str, message: str) -> str:
        if "成功" in message:
            return f"{self.GREEN}✓{self.RESET}"
        if "失败" in message or level == "ERROR":
            return f"{self.RED}✗{self.RESET}"
        if level == "WARNING":
            return f"{self.YELLOW}!{self.RESET}"
        if "启动" in message:
            return f"{self.CYAN}→{self.RESET}"
        if "定时" in message or "任务" in message:
            return f"{self.GRAY}⏱{self.RESET}"
        return " "


def setup_logger(name: str = "hotpush") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    level = logging.DEBUG if settings.debug else logging.INFO
    logger.setLevel(level)
    logger.addFilter(CorrelationFilter())

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    structured = os.environ.get("HOTSPOT_STRUCTURED_LOGS") == "1"
    console_handler.setFormatter(JsonFormatter() if structured else ColoredFormatter())
    logger.addHandler(console_handler)
    return logger


logger = setup_logger()
