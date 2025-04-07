#!/usr/bin/env python3
"""Command-line interface for tbutilslib.

This module provides command-line utilities for working with the tbutilslib package.
"""

import argparse
import logging
import sys
from typing import List, Optional

from mongoengine import connect

from tbutilslib import __version__
from tbutilslib.config.database import MongoConfig
from tbutilslib.logger import get_logger
from tbutilslib.models.ensure_indexes import ensure_all_indexes

logger = get_logger(__name__)


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

    # Setup database command
    db_parser = subparsers.add_parser("setup-db", help="Setup database indexes")
    db_parser.add_argument("--host", default="0.0.0.0", help="MongoDB host")
    db_parser.add_argument("--port", type=int, default=27017, help="MongoDB port")
    db_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    # Add more commands as needed

    return parser.parse_args(args)


def setup_database(args: argparse.Namespace) -> int:
    """Set up database indexes.

    Args:
        args: Command line arguments

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    try:
        # Configure logging level based on verbosity
        if args.verbose:
            logger.setLevel(logging.DEBUG)
            logger.debug("Debug logging enabled")

        logger.info(f"Connecting to MongoDB at {args.host}:{args.port}")
        connect(MongoConfig.MONGODB_DB, host=args.host, port=args.port)

        logger.info("Creating database indexes...")
        ensure_all_indexes()

        logger.info("Database setup completed successfully")
        return 0
    except Exception as e:
        logger.error(f"Error setting up database: {str(e)}")
        return 1


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
    if not parsed_args.command:
        logger.error("No command specified. Use --help for available commands.")
        return 1

    logger.error(f"Unknown command: {parsed_args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
