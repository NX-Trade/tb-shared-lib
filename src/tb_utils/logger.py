"""Logging configuration module for tb_utils.

This module provides a flexible logging setup for the library and services with options
for console and file-based logging with rotation. It supports different log levels,
service-wide dual logging (stdout + rotating file), and Celery signal integration.
"""

import importlib
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Optional

# Standard formatter across all services
STANDARD_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DETAILED_FORMAT = (
    "%(asctime)s - %(name)s - %(levelname)s - [%(process)d] - %(pathname)s:%(lineno)d - %(message)s"
)

# Default log file name with date (evaluated at runtime, not at import)
DEFAULT_LOG_FILE = f"TradingBot_{datetime.today().strftime('%Y-%m-%d')}.log"
# Default log directory - uses current directory if not specified
DEFAULT_LOG_DIR = os.getenv("TBUTILSLIB_LOG_DIR", os.getcwd())


def get_console_handler(
    level: int = logging.INFO,
    formatter: Optional[logging.Formatter] = None,
) -> logging.StreamHandler:
    """Create a console handler for logging to stdout.

    Args:
        level: The logging level for the console handler (default: INFO)
        formatter: Custom formatter for log messages (default: None, uses standard formatter)

    Returns:
        A configured StreamHandler for console output
    """
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    if formatter is None:
        formatter = logging.Formatter(STANDARD_FORMAT)

    console_handler.setFormatter(formatter)
    return console_handler


def get_file_handler(
    log_file: Optional[str] = None,
    log_dir: Optional[str] = None,
    level: int = logging.DEBUG,
    formatter: Optional[logging.Formatter] = None,
    max_bytes: int = 10485760,  # 10MB
    backup_count: int = 14,
    rotation_type: str = "timed",  # "timed" or "size"
) -> TimedRotatingFileHandler | RotatingFileHandler:
    """Create a file handler for logging to a file with rotation.

    Args:
        log_file: Name of the log file (default: uses DEFAULT_LOG_FILE)
        log_dir: Directory to store log files (default: uses DEFAULT_LOG_DIR)
        level: The logging level for the file handler (default: DEBUG)
        formatter: Custom formatter for log messages (default: None, uses standard formatter)
        max_bytes: Maximum size in bytes before rotating (for size-based rotation)
        backup_count: Number of backup files to keep (default: 14)
        rotation_type: Type of rotation - "timed" (daily) or "size" (based on file size)

    Returns:
        A configured file handler with rotation
    """
    log_file = log_file or DEFAULT_LOG_FILE
    log_dir = log_dir or DEFAULT_LOG_DIR

    # Ensure log directory exists
    os.makedirs(log_dir, exist_ok=True)

    # Full path to log file
    log_path = os.path.join(log_dir, log_file)

    if rotation_type.lower() == "timed":
        file_handler = TimedRotatingFileHandler(
            log_path, when="midnight", interval=1, backupCount=backup_count, encoding="utf-8"
        )
    else:  # size-based rotation
        file_handler = RotatingFileHandler(
            log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )

    file_handler.setLevel(level)

    if formatter is None:
        formatter = logging.Formatter(STANDARD_FORMAT)

    file_handler.setFormatter(formatter)
    return file_handler


def setup_service_logging(
    service_name: str,
    log_dir: Optional[str] = None,
    log_level: Optional[str] = None,
    console: bool = True,
    backup_count: int = 14,
) -> logging.Logger:
    """Configure root and Celery logging for a service with dual stdout and rotating file output.

    Args:
        service_name: Name of the service (e.g. 'collector', 'signal-bot', 'execution', 'backend').
        log_dir: Directory where log files are stored. Defaults to $LOG_DIR environment variable.
        log_level: Root logging level string (e.g. 'INFO', 'DEBUG'). Defaults to $LOG_LEVEL or 'INFO'.
        console: Whether to attach stdout console handler. Defaults to True.
        backup_count: Number of rotated daily log files to retain. Defaults to 14.

    Returns:
        The configured root logger.
    """
    effective_log_dir = log_dir or os.getenv("LOG_DIR")
    level_str = log_level or os.getenv("LOG_LEVEL", "INFO").upper()
    numeric_level = getattr(logging, level_str, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Clear existing handlers to prevent duplicate lines
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    formatter = logging.Formatter(STANDARD_FORMAT)

    if console:
        c_handler = logging.StreamHandler(sys.stdout)
        c_handler.setLevel(numeric_level)
        c_handler.setFormatter(formatter)
        root_logger.addHandler(c_handler)

    f_handler: Optional[logging.Handler] = None
    if effective_log_dir:
        try:
            os.makedirs(effective_log_dir, exist_ok=True)
            log_filename = f"{service_name}.log"
            f_handler = TimedRotatingFileHandler(
                os.path.join(effective_log_dir, log_filename),
                when="midnight",
                interval=1,
                backupCount=backup_count,
                encoding="utf-8",
            )
            f_handler.setLevel(numeric_level)
            f_handler.setFormatter(formatter)
            root_logger.addHandler(f_handler)
        except Exception:
            root_logger.exception(
                "Failed to initialize persistent file logging in %s", effective_log_dir
            )

    # Hook Celery signals if Celery is available in runtime
    if f_handler is not None:
        try:
            

            celery_signals = importlib.import_module("celery.signals")
            after_setup_logger = getattr(celery_signals, "after_setup_logger", None)
            after_setup_task_logger = getattr(celery_signals, "after_setup_task_logger", None)

            if after_setup_logger is not None:

                def _on_after_setup_logger(logger, **kwargs):
                    if f_handler and f_handler not in logger.handlers:
                        logger.addHandler(f_handler)

                after_setup_logger.connect(_on_after_setup_logger, weak=False)

            if after_setup_task_logger is not None:

                def _on_after_setup_task_logger(logger, **kwargs):
                    if f_handler and f_handler not in logger.handlers:
                        logger.addHandler(f_handler)

                after_setup_task_logger.connect(_on_after_setup_task_logger, weak=False)
        except (ImportError, AttributeError):
            pass

    return root_logger


def get_logger(
    logger_name: str,
    log_file: Optional[str] = None,
    log_dir: Optional[str] = None,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    use_console: bool = True,
    use_file: bool = True,
    propagate: bool = False,
) -> logging.Logger:
    """Configure and get a logger with the specified name and handlers.

    This function creates a logger with optional console and file handlers.
    It's the main entry point for setting up logging in the application.

    Args:
        logger_name: Name of the logger, typically __name__ or module path
        log_file: Name of the log file (default: None, uses DEFAULT_LOG_FILE)
        log_dir: Directory to store log files (default: None, uses DEFAULT_LOG_DIR)
        console_level: Logging level for console output (default: INFO)
        file_level: Logging level for file output (default: DEBUG)
        use_console: Whether to add a console handler (default: True)
        use_file: Whether to add a file handler (default: True)
        propagate: Whether to propagate logs to parent loggers (default: False)

    Returns:
        A configured logger instance
    """
    # Get or create logger
    logger = logging.getLogger(logger_name)

    # Remove existing handlers if any
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Set the logger's level to the minimum of console and file levels
    # to ensure all messages get through to the handlers
    logger.setLevel(min(console_level, file_level))

    # Add console handler if requested
    if use_console:
        logger.addHandler(get_console_handler(level=console_level))

    # Add file handler if requested
    if use_file:
        logger.addHandler(get_file_handler(log_file=log_file, log_dir=log_dir, level=file_level))

    # Control propagation to parent loggers
    logger.propagate = propagate

    return logger
