#!/bin/bash

# Get the script's directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"

cd /home/xuananh/repo/mcp-server/src/selenium/src

"${SCRIPT_DIR}/.venv/bin/python" -m mcp_server_selenium "$@"
