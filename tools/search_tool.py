# tools/search_tool.py
import os
import requests
from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field

class TavilySearchInput(BaseModel):
    query: str = Field(description="Search query")

class TavilySearchTool(BaseTool):
    name: str = "tavily_web_search"
    description: str = "Search the web for real people and companies"
    args_schema: Type[BaseModel] = TavilySearchInput

    def _run(self, query: str) -> str:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return "Error: No TAVILY_API_KEY"
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": query,
                      "max_results": 5, "include_answer": False},
                timeout=10
            )
            data    = resp.json()
            results = data.get("results", [])
            output  = []
            for r in results:
                title   = r.get("title", "")
                url     = r.get("url", "")
                content = r.get("content", "")[:150]
                output.append(f"- [{title}] {url}: {content}")
            return "\n".join(output) if output else "No results found"
        except Exception as e:
            return f"Search error: {e}"