#!/usr/bin/env python3
"""Command-line interface for tb_utils.

This module provides command-line utilities for working with the tb_utils package,
including database setup and configuration validation.
"""

import argparse
import logging
import sys
from typing import List, Optional

from tb_utils import __version__
from tb_utils.logger import get_logger

logger = get_logger(__name__, use_file=False)


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments.

    Args:
        args: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Trading Bot Utilities Library CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # setup-db: create all SQLAlchemy tables
    db_parser = subparsers.add_parser(
        "setup-db",
        help="Create all database tables defined by the SQLAlchemy models",
    )
    db_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    # check-config: validate env vars without making a DB connection
    subparsers.add_parser(
        "check-config",
        help="Print resolved database configuration (no connection made)",
    )

    return parser.parse_args(args)


def setup_database(args: argparse.Namespace) -> int:
    """Create all SQLAlchemy tables using the configured PostgreSQL database.

    Args:
        args: Command line arguments

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")

    try:
        from tb_utils.config.db_session import get_engine
        from tb_utils.models import Base

        engine = get_engine()
        logger.info(
            "Connected to database at: %s",
            engine.url.render_as_string(hide_password=True),
        )

        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database setup completed successfully.")
        return 0
    except Exception as exc:
        logger.error("Error setting up database: %s", exc, exc_info=args.verbose)
        return 1


def check_config() -> int:
    """Print the resolved database configuration without connecting.

    Returns:
        Exit code (0 always)
    """
    from tb_utils.config.database import db_settings

    url = db_settings.get_database_url
    # Mask the password in output
    masked = (
        url.replace(db_settings.POSTGRES_PASSWORD, "****")
        if db_settings.POSTGRES_PASSWORD
        else url
    )
    print(f"Database URL : {masked}")
    print(f"Host         : {db_settings.POSTGRES_HOST}")
    print(f"Port         : {db_settings.POSTGRES_PORT}")
    print(f"Database     : {db_settings.POSTGRES_DB}")
    print(f"User         : {db_settings.POSTGRES_USER}")
    return 0


def main(args: Optional[List[str]] = None) -> int:
    """Main entry point for the CLI.

    Args:
        args: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    parsed_args = parse_args(args)

    if parsed_args.command == "setup-db":
        return setup_database(parsed_args)
    if parsed_args.command == "check-config":
        return check_config()
    if not parsed_args.command:
        logger.error("No command specified. Use --help for available commands.")
        return 1

    logger.error("Unknown command: %s", parsed_args.command)
    return 1


if __name__ == "__main__":
    sys.exit(main())
