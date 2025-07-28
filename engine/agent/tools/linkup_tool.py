"""
Linkup Tool for web search and data connection capabilities.

This tool provides web search functionality and data connection capabilities
using the Linkup platform API.
"""

import logging
import json
from typing import Optional, Dict, Any
import requests

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

from engine.agent.agent import (
    Agent,
    ChatMessage,
    AgentPayload,
    ComponentAttributes,
    ToolDescription,
    SourceChunk,
    SourcedResponse,
)
from engine.trace.trace_manager import TraceManager
from settings import settings

LOGGER = logging.getLogger(__name__)

LINKUP_TOOL_DESCRIPTION = ToolDescription(
    name="linkup_search",
    description="Linkup is a web search API that provides real-time search results and data connection capabilities.",
    tool_properties={
        "query": {
            "type": "string", 
            "description": "The search query to execute."
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of search results to return (default: 10, max: 100).",
            "default": 10
        },
        "include_text": {
            "type": "boolean",
            "description": "Whether to include full text content in results (default: true).",
            "default": True
        },
    },
    required_tool_properties=["query"],
)


class LinkupSearchTool(Agent):
    """
    Linkup Search Tool for web search and data connection.
    
    This tool uses the Linkup API to perform web searches and retrieve
    real-time information from the web.
    """
    
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        tool_description: ToolDescription = LINKUP_TOOL_DESCRIPTION,
        linkup_api_key: str = settings.LINKUP_API_KEY,
        base_url: str = "https://api.linkup.so/v1",
        timeout: int = 30,
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self.linkup_api_key = linkup_api_key
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        
        if self.linkup_api_key:
            self.session.headers.update({
                "Authorization": f"Bearer {self.linkup_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Linkup-Tool/1.0"
            })

    def search_web(self, query: str, max_results: int = 10, include_text: bool = True) -> list[SourceChunk]:
        """
        Perform a web search using the Linkup API.
        
        Args:
            query: The search query
            max_results: Maximum number of results to return
            include_text: Whether to include full text content
            
        Returns:
            List of SourceChunk objects containing search results
        """
        if not self.linkup_api_key:
            LOGGER.warning("Linkup API key not configured, returning empty results")
            return []
            
        try:
            # Construct the API request
            search_params = {
                "q": query,
                "limit": min(max_results, 100),  # Cap at 100
                "include_text": include_text
            }
            
            # Make the API request
            response = self.session.get(
                f"{self.base_url}/search",
                params=search_params,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Parse the response into SourceChunk objects
            results = []
            search_results = data.get("results", [])
            
            for result in search_results:
                source_chunk = SourceChunk(
                    name=result.get("title", "Unknown Title"),
                    document_name=result.get("title", "Unknown Title"),
                    content=result.get("snippet", result.get("text", "")),
                    url=result.get("url", ""),
                    metadata={
                        "url": result.get("url", ""),
                        "source": "linkup",
                        "published_date": result.get("published_date"),
                        "domain": result.get("domain"),
                        "score": result.get("score", 0.0),
                    }
                )
                results.append(source_chunk)
                
            return results
            
        except requests.RequestException as e:
            LOGGER.error(f"Linkup API request failed: {e}")
            return []
        except json.JSONDecodeError as e:
            LOGGER.error(f"Failed to parse Linkup API response: {e}")
            return []
        except Exception as e:
            LOGGER.error(f"Unexpected error in Linkup search: {e}")
            return []

    async def _run_without_trace(
        self,
        *inputs: AgentPayload,
        query: Optional[str] = None,
        max_results: Optional[int] = None,
        include_text: Optional[bool] = None,
    ) -> AgentPayload:
        """Execute the Linkup search tool."""
        
        # Get query from parameters or from the last message
        if query is None:
            if inputs and inputs[0].last_message:
                query = inputs[0].last_message.content
            else:
                return AgentPayload(messages=[
                    ChatMessage(role="assistant", content="Error: No search query provided.")
                ])
        
        # Set defaults
        max_results = max_results or 10
        include_text = include_text if include_text is not None else True
        
        # Perform the search
        search_results = self.search_web(
            query=query,
            max_results=max_results,
            include_text=include_text
        )
        
        if not search_results:
            return AgentPayload(messages=[
                ChatMessage(role="assistant", content=f"No results found for query: {query}")
            ])
        
        # Format the results for response
        response_content = f"Found {len(search_results)} results for '{query}':\n\n"
        
        for i, result in enumerate(search_results, 1):
            response_content += f"{i}. **{result.name}**\n"
            response_content += f"   URL: {result.url}\n"
            if result.content:
                # Truncate content for readability
                content = result.content[:200] + "..." if len(result.content) > 200 else result.content
                response_content += f"   Summary: {content}\n"
            if result.metadata.get("published_date"):
                response_content += f"   Published: {result.metadata['published_date']}\n"
            response_content += "\n"
        
        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=response_content)],
            source_chunks=search_results
        )