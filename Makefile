selenium-mcp-inspector:
	.venv/bin/mcp dev src/selenium/control_already_open_chrome_sync_server.py

selenium-mcp-log:
	tail -f /tmp/selenium-mcp.log
