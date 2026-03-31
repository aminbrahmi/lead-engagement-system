# test_llm.py
from agents.llm_factory import get_collector_llm, get_qualifier_llm
from dotenv import load_dotenv
load_dotenv()

llm = get_collector_llm()
print(llm.invoke("Say hello in one word.").content)

llm2 = get_qualifier_llm()
print(llm2.invoke("Say hello in one word.").content)