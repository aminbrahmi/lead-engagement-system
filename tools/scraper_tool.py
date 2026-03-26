# tools/scraper_tool.py
import asyncio
import nest_asyncio
from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field

nest_asyncio.apply()

class CrawleeInput(BaseModel):
    url: str = Field(description="URL to scrape")

class CrawleeTool(BaseTool):
    name: str = "crawlee_dynamic_scraper"
    description: str = "Scrape dynamic web pages using Playwright"
    args_schema: Type[BaseModel] = CrawleeInput

    def _run(self, url: str) -> str:
        try:
            return asyncio.run(self._scrape(url))
        except Exception as e:
            return f"Scraping failed: {e}"

    async def _scrape(self, url: str) -> str:
        from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext
        result = {"text": ""}

        async def handler(ctx: PlaywrightCrawlingContext):
            await ctx.page.wait_for_load_state("networkidle")
            result["text"] = await ctx.page.inner_text("body")

        crawler = PlaywrightCrawler(max_requests_per_crawl=1)
        crawler.router.default_handler(handler)
        await crawler.run([url])
        return result["text"][:2000] if result["text"] else "No content extracted"