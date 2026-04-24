# SWRDMCPServer
SWRD MCP Server，support Redfish、IPMI、playwright command forward

1、codebuddy中mcp.json的配置如下：<br>
{<br>
&emsp;&emsp;"mcpServers": {<br>
&emsp;&emsp;&emsp;&emsp;"SWRDMCPServer": {<br>
&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;"url": "http://localhost:8000/mcp",<br>
&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;"transport": "streamable-http",<br>
&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;"headers": {<br>
&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;"Authorization": "Basic YWRtaW46YWRtaW4xMjM="<br>
&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;},<br>
&emsp;&emsp;&emsp;&emsp;"disabled": false<br>
&emsp;&emsp;&emsp;&emsp;}<br>
&emsp;&emsp;}<br>
}<br>
<br>
<br>
2、在.codebuddy/rules/SystemTest.mdc中，修改相关的配置为自己环境的配置。<br>
<br>
<br>
3、修改MCPServer.py的代码时，需注意引用MCPServer.mdc的rules文件。

