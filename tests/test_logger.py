"""Unit tests for tb_utils.logger."""

import logging
import os
import tempfile
from unittest.mock import patch

from tb_utils.logger import (
    get_console_handler,
    get_file_handler,
    get_logger,
    setup_service_logging,
)


def test_get_console_handler():
    handler = get_console_handler(level=logging.WARNING)
    assert handler.level == logging.WARNING
    assert handler.formatter is not None


def test_get_file_handler_timed():
    with tempfile.TemporaryDirectory() as tmpdir:
        handler = get_file_handler(
            log_file="test_timed.log",
            log_dir=tmpdir,
            level=logging.DEBUG,
            rotation_type="timed",
        )
        assert handler.level == logging.DEBUG
        assert os.path.exists(tmpdir)
        handler.close()


def test_get_file_handler_size():
    with tempfile.TemporaryDirectory() as tmpdir:
        handler = get_file_handler(
            log_file="test_size.log",
            log_dir=tmpdir,
            level=logging.INFO,
            rotation_type="size",
            max_bytes=1024,
            backup_count=3,
        )
        assert handler.level == logging.INFO
        handler.close()


def test_get_logger():
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = get_logger(
            logger_name="test_logger_unit",
            log_file="unit.log",
            log_dir=tmpdir,
            console_level=logging.INFO,
            file_level=logging.DEBUG,
        )
        assert logger.name == "test_logger_unit"
        assert len(logger.handlers) == 2
        for h in logger.handlers:
            h.close()


def test_setup_service_logging_with_log_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = setup_service_logging(
            service_name="test_service",
            log_dir=tmpdir,
            log_level="DEBUG",
            console=True,
            backup_count=7,
        )
        assert logger.level == logging.DEBUG
        # Should have console handler and file handler
        assert len(logger.handlers) == 2

        logger.info("Testing persistent service logging message")

        log_path = os.path.join(tmpdir, "test_service.log")
        assert os.path.exists(log_path)

        for h in logger.handlers:
            h.close()

        with open(log_path, encoding="utf-8") as f:
            content = f.read()
        assert "Testing persistent service logging message" in content


def test_setup_service_logging_env_var():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"LOG_DIR": tmpdir, "LOG_LEVEL": "WARNING"}):
            logger = setup_service_logging(service_name="env_service")
            assert logger.level == logging.WARNING
            assert len(logger.handlers) == 2

            logger.warning("Warning message from env service")

            log_path = os.path.join(tmpdir, "env_service.log")
            assert os.path.exists(log_path)

            for h in logger.handlers:
                h.close()

            with open(log_path, encoding="utf-8") as f:
                content = f.read()
            assert "Warning message from env service" in content
