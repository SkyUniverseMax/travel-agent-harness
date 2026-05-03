"""
MCP (Model Context Protocol) 客户端管理。

支持通过 stdio / sse / http 协议连接外部 MCP Server，
将远程工具加载为 LangChain 兼容工具。如果未配置 MCP Server 或连接失败，
自动降级为空工具列表，不影响系统正常运行。

使用方式：
    1. 在 .env 中配置 MCP_SERVERS JSON 列表
    2. 调用 get_mcp_tools() 获取所有远程工具
    3. 将返回的工具合并到 primary_assistant_tools 中
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional, Literal

from graph_chat.log_utils import log
from config import config


@dataclass
class MCPServerConfig:
    """单个 MCP Server 的配置。"""
    name: str
    transport: Literal["stdio", "sse", "http"] = "stdio"
    command: Optional[str] = None
    args: list[str] = field(default_factory=list)
    url: Optional[str] = None
    headers: dict = field(default_factory=dict)


class MCPClientManager:
    """管理多个 MCP Server 连接和工具加载。"""

    def __init__(self, server_configs: list[dict] | None = None):
        self._servers: list[MCPServerConfig] = []
        self._tools: list = []
        self._connected = False

        raw = server_configs if server_configs is not None else config.MCP_SERVERS
        for s in raw:
            try:
                self._servers.append(MCPServerConfig(
                    name=s["name"],
                    transport=s.get("transport", "stdio"),
                    command=s.get("command"),
                    args=s.get("args", []),
                    url=s.get("url"),
                    headers=s.get("headers", {}),
                ))
            except KeyError as e:
                log.warning(f"MCP Server 配置缺少必要字段 {e}，已跳过")

    def load_tools(self) -> list:
        """从所有 MCP Server 加载工具。失败时返回空列表并记录警告。"""
        if self._connected:
            return self._tools

        if not self._servers:
            log.info("未配置 MCP Server，跳过 MCP 工具加载")
            return []

        all_tools = []
        for server in self._servers:
            try:
                server_tools = asyncio.run(self._connect_and_load(server))
                all_tools.extend(server_tools)
                log.info(f"MCP Server [{server.name}] 加载了 {len(server_tools)} 个工具")
            except Exception as e:
                log.warning(f"MCP Server [{server.name}] 连接失败: {e}，已跳过")

        self._tools = all_tools
        self._connected = True
        return all_tools

    async def _connect_and_load(self, server: MCPServerConfig) -> list:
        """连接到单个 MCP Server 并加载工具。使用 langchain-mcp-adapters。"""
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
        except ImportError:
            log.warning("langchain-mcp-adapters 未安装，无法连接 MCP Server")
            return []

        if server.transport == "stdio":
            if not server.command:
                log.warning(f"MCP Server [{server.name}] 缺少 command，跳过")
                return []
            # 将相对路径的 args 解析为绝对路径（基于项目根目录）
            from pathlib import Path
            resolved_args = []
            for arg in server.args:
                arg_path = Path(arg)
                if arg_path.is_absolute():
                    resolved_args.append(arg)
                else:
                    resolved_args.append(str(Path(config.PROJECT_ROOT) / arg))
            client = MultiServerMCPClient({
                server.name: {
                    "transport": "stdio",
                    "command": server.command,
                    "args": resolved_args,
                }
            })
        elif server.transport in ("sse", "http"):
            if not server.url:
                log.warning(f"MCP Server [{server.name}] 缺少 url，跳过")
                return []
            client = MultiServerMCPClient({
                server.name: {
                    "transport": server.transport,
                    "url": server.url,
                    "headers": server.headers,
                }
            })
        else:
            log.warning(f"MCP Server [{server.name}] 不支持的传输协议: {server.transport}")
            return []

        return await client.get_tools()


# 全局单例
_mcp_manager: Optional[MCPClientManager] = None


def get_mcp_tools() -> list:
    """获取所有 MCP 远程工具（懒加载，失败自动降级）。"""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPClientManager()
    return _mcp_manager.load_tools()
