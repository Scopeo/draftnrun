import logging

from fastmcp import FastMCP

logger = logging.getLogger(__name__)


def register_all_tools(mcp: FastMCP) -> None:
    from mcp_server.tools import (
        agent_config,
        agents,
        api_keys,
        components,
        context_tools,
        crons,
        graphs,
        knowledge,
        monitoring,
        oauth_connections,
        projects,
        qa,
        runs,
        variables,
    )

    modules = [
        context_tools,
        projects,
        agents,
        agent_config,
        graphs,
        components,
        runs,
        api_keys,
        variables,
        knowledge,
        qa,
        monitoring,
        crons,
        oauth_connections,
    ]
    for module in modules:
        try:
            module.register(mcp)
        except Exception as exc:
            logger.exception("Failed to register MCP tool module '%s'", module.__name__)
            raise RuntimeError(f"Failed to register MCP tool module '{module.__name__}': {exc}") from exc
