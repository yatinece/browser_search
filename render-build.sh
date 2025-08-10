#!/bin/bash
# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browsers without asking for sudo
python -m playwright install --with-deps chromium
