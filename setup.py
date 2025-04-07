"""Trading Bot Utilities Library (tbutilslib) setup script.

This module handles the setup and installation of the tbutilslib package.
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
        os.path.join("src", "tbutilslib", "__init__.py"), "r", encoding="utf-8"
    ) as f:
        init_py = f.read()
    version_match = re.search(r"__version__ = ['\"]([^'\"]+)['\"]", init_py)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Version string not found in __init__.py")


# Read long description from README.md
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Main setup configuration
setup(
    name="tbutilslib",
    version=get_version(),
    author="Abhishake Gupta",
    author_email="letspython3.x@gmail.com",
    description="Trading Bot Utilities Library",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/letspython3x/tbutilslib",
    project_urls={
        "Bug Tracker": "https://github.com/letspython3x/tbutilslib/issues",
        "Documentation": "https://github.com/letspython3x/tbutilslib/wiki",
        "Source Code": "https://github.com/letspython3x/tbutilslib",
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
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        "Flask-RESTful>=0.3.9",
        "flask-mongoengine>=1.0.0",
        "marshmallow>=3.13.0",
        "marshmallow-mongoengine>=0.9.1",
        "pymongo>=3.12.0",
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
            "tbutilslib=tbutilslib.cli:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
