from setuptools import setup, find_packages
from setuptools.command.install import install as _install
import subprocess
import sys

class PostInstallCommand(_install):
    """Post-installation for installation mode: installs Playwright browsers."""
    def run(self):
        # Run standard install
        _install.run(self)
        # Install Playwright browser binaries
        try:
            subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        except subprocess.CalledProcessError as e:
            print(f"Error during Playwright install: {e}", file=sys.stderr)

setup(
    name="mcp_browser_api",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.100.0",
        "uvicorn>=0.22.0",
        "selenium>=4.10.0",
        "webdriver-manager>=3.8.6",
        "pydantic>=2.0.0",
        "playwright",
        "playwright-stealth",
        "pymupdf",
        "aiohttp",
    ],
    cmdclass={
        'install': PostInstallCommand,
    },
    author="MCP Browser API Developer",
    author_email="yatinece@gmail.com",
    description="Multi-Context Processing API using Chrome browser",
    keywords="mcp, api, browser, chrome, search",
    python_requires=">=3.8",
)
