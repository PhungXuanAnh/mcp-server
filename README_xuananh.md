# Debug
## Using Cursor (recommendation)

1. Setup MCP server to write log to a file, for example: /tmp/selenium-mcp.log
2. Setup MCP server in cursor
3. Enable it
4. Check log: tailf /tmp/selenium-mcp.log

## Using MCP inspector

For example, testing selenium mcp

```bash
make selenium-mcp-inspector
```

Check log: tailf /tmp/selenium-mcp.log




