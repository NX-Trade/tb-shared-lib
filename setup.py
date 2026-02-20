"""Trading Bot Utilities Library (tb_utils) setup script.

This module handles the setup and installation of the tb_utils package.
It uses setuptools for package management and distribution.
"""

import os
import re

from setuptools import find_packages, setup


def get_version():
    """Extract version information from the package __init__.py file.

    Returns:
        str: The package version string

    Raises:
        RuntimeError: If version string cannot be found
    """
    with open(
        os.path.join("src", "tb_utils", "__init__.py"), "r", encoding="utf-8"
    ) as f:
        init_py = f.read()
    version_match = re.search(r"__version__ = ['\"]([^'\"]+)['\"]", init_py)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Version string not found in __init__.py")


# Main setup configuration
setup(
    name="tb-utils",
    version=get_version(),
    author="Codams",
    author_email="[EMAIL_ADDRESS]",
    description="Trading Bot Utilities Library",
    long_description_content_type="text/markdown",
    url="https://github.com/NX-Trade/tb-shared-lib",
    project_urls={
        "Bug Tracker": "https://github.com/NX-Trade/tb-shared-lib/issues",
        "Documentation": "https://github.com/NX-Trade/tb-shared-lib/wiki",
        "Source Code": "https://github.com/NX-Trade/tb-shared-lib",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        "fastapi>=0.109.0",
        "uvicorn>=0.27.0",
        "sqlalchemy>=2.0.25",
        "alembic>=1.13.1",
        "psycopg2-binary>=2.9.9",
        "pydantic>=2.5.3",
        "pydantic-settings>=2.1.0",
        "requests>=2.31.0",
        "urllib3>=2.1.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "flake8-docstrings>=1.7.0",
            "pre-commit>=3.0.0",
            "pylint>=2.17.0",
        ],
        "docs": [
            "sphinx>=7.0.0",
            "sphinx-rtd-theme>=1.3.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "tb-utils=tb_utils.cli:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
