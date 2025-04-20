#!/bin/bash

# Add the module path to PYTHONPATH to ensure it can be found
export PYTHONPATH="/home/xuananh/Downloads/servers/src/git/src:$PYTHONPATH"

# Change to the fetch source directory
cd /home/xuananh/Downloads/servers/src/git/src

# Activate the virtual environment and run the module
source /home/xuananh/Downloads/servers/.venv/bin/activate
/home/xuananh/Downloads/servers/.venv/bin/python -m mcp_server_git "$@"