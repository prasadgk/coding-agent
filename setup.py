"""Setup configuration for Universal AI Coding Agent."""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_file.exists():
    requirements = [
        line.strip() 
        for line in requirements_file.read_text().splitlines() 
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="universal-ai-coding-agent",
    version="1.0.0",
    author="AI Coding Agent Team",
    description="Universal AI Coding Agent - Autonomous code development platform",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/ai-coding-agent",
    packages=find_packages(include=["src", "src.*"]),
    package_dir={"": "."},
    python_requires=">=3.9",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.4.4",
            "pytest-asyncio>=0.23.3",
            "pytest-mock>=3.12.0",
            "pytest-cov>=4.1.0",
            "black>=23.12.1",
            "flake8>=7.0.0",
            "mypy>=1.8.0",
            "pre-commit>=3.6.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "ai-agent=src.main:main",
            "ai-agent-api=src.api.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Code Generators",
        "Topic :: Software Development :: Version Control :: Git",
    ],
    keywords="ai coding automation claude anthropic jira bitbucket github",
)