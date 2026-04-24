# SWRDMCPServer
SWRD MCP Server，support Redfish、IPMI、playwright command forward

1、codebuddy中mcp.json的配置如下：
{
  "mcpServers": {
    "SWRDMCPServer": {
      "url": "http://localhost:8000/mcp",
      "transport": "streamable-http",
      "headers": {
        "Authorization": "Bearer swrd-mcp-server-token-2026"
      },
      "disabled": false
    }
  }
}

2、在.codebuddy/rules/SystemTest.mdc中，修改相关的配置为自己环境的配置。


