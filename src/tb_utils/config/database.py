# pylint: disable=W0603
"""Database Configuration."""

import os

from pydantic_settings import BaseSettings


class DatabaseConfig(BaseSettings):
    """Configuration for PostgreSQL Database."""

    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "postgres")
    DB_NAME: str = os.getenv("DB_NAME", "trading_db")

    @property
    def get_database_url(self) -> str:
        """Get standard synchronous PostgreSQL URL for SQLAlchemy."""
        return (
            f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


# Define global settings instance
db_settings = DatabaseConfig()
