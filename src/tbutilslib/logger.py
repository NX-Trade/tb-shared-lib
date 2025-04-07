"""Logging configuration module for tbutilslib.

This module provides a flexible logging setup for the library with options for
console and file-based logging with rotation. It supports different log levels
and custom formatting.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Optional, Union

from tbutilslib.utils.common import TODAY

# Default formatter with timestamp, logger name, level, and message
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
# More detailed formatter including process ID and line number for debugging
DETAILED_FORMAT = (
    "%(asctime)s - %(name)s - %(levelname)s - [%(process)d] "
    "- %(pathname)s:%(lineno)d - %(message)s"
)

# Default log file name with date
DEFAULT_LOG_FILE = f"TradingBot_{TODAY}.log"
# Default log directory - uses current directory if not specified
DEFAULT_LOG_DIR = os.getenv("TBUTILSLIB_LOG_DIR", os.getcwd())


def get_console_handler(
    level: int = logging.INFO, formatter: Optional[logging.Formatter] = None
) -> logging.StreamHandler:
    """Create a console handler for logging to stdout.

    Args:
        level: The logging level for the console handler (default: INFO)
        formatter: Custom formatter for log messages (default: None, uses default formatter)

    Returns:
        A configured StreamHandler for console output
    """
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    if formatter is None:
        formatter = logging.Formatter(DEFAULT_FORMAT)

    console_handler.setFormatter(formatter)
    return console_handler


def get_file_handler(
    log_file: Optional[str] = None,
    log_dir: Optional[str] = None,
    level: int = logging.DEBUG,
    formatter: Optional[logging.Formatter] = None,
    max_bytes: int = 10485760,  # 10MB
    backup_count: int = 5,
    rotation_type: str = "timed",  # "timed" or "size"
) -> Union[TimedRotatingFileHandler, RotatingFileHandler]:
    """Create a file handler for logging to a file with rotation.

    Args:
        log_file: Name of the log file (default: uses DEFAULT_LOG_FILE)
        log_dir: Directory to store log files (default: uses DEFAULT_LOG_DIR)
        level: The logging level for the file handler (default: DEBUG)
        formatter: Custom formatter for log messages (default: None, uses default formatter)
        max_bytes: Maximum size in bytes before rotating (for size-based rotation)
        backup_count: Number of backup files to keep
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
            log_path, when="midnight", backupCount=backup_count
        )
    else:  # size-based rotation
        file_handler = RotatingFileHandler(
            log_path, maxBytes=max_bytes, backupCount=backup_count
        )

    file_handler.setLevel(level)

    if formatter is None:
        formatter = logging.Formatter(DETAILED_FORMAT)

    file_handler.setFormatter(formatter)
    return file_handler


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
        logger.addHandler(
            get_file_handler(log_file=log_file, log_dir=log_dir, level=file_level)
        )

    # Control propagation to parent loggers
    logger.propagate = propagate

    return logger
