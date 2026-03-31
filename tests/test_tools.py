# test_tools.py

from tools.email_finder import EmailFinderTool
from tools.name_enricher import NameEnricherTool
from tools.search_tool import TavilySearchTool
from dotenv import load_dotenv
load_dotenv()

# Should return web results
print(TavilySearchTool()._run("AI startup Berlin CTO 2024"))

# Should return an email or "Contact not found"
print(EmailFinderTool()._run("Alexander Matthey | Parloa"))

# Should return "Found: First Last" or "Name not found"
print(NameEnricherTool()._run("Parloa | CTO | Berlin"))