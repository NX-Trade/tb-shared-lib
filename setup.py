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
    with open(os.path.join("src", "tb_utils", "__init__.py"), encoding="utf-8") as f:
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
    author_email="letspython3.x@gmail.com",
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
        "Programming Language :: Python :: 3.13",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
    packages=find_packages(where="src"),
    python_requires=">=3.13",
    install_requires=[
        "fastapi>=0.135.1",
        "uvicorn>=0.41.0",
        "sqlalchemy>=2.0.48",
        "alembic>=1.18.4",
        "psycopg2-binary>=2.9.11",
        "pydantic>=2.12.5",
        "pydantic-settings>=2.13.1",
        "requests>=2.32.5",
        "urllib3>=2.6.3",
        "pylint>=4.0.5",
    ],
    extras_require={
        "dev": [
            "pytest>=8.3.4",
            "pytest-cov>=5.2.0",
            "black>=26.3.0",
            "flake8>=6.0.0",
            "isort>=8.0.1",
            "pre-commit>=3.0.0",
            "pylint>=4.0.5",
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
