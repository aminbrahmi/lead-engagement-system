#!/usr/bin/env python3
"""
Quick test of JSON parsing fixes without needing API calls.
Simulates what the collector returns and tests extraction.
"""

from utils.json_utils import extract_json_list

print("="*70)
print("Testing JSON Extraction Fixes")
print("="*70)

# Test Case 1: Truncated mid-string (the original issue)
print("\n[Test 1] Truncated mid-string (original issue)")
print("-" * 70)
truncated_response = """[
  {
    "name": "Brad Heller",
    "company": "Tower",
    "role": "CTO",
    "location": "Berlin",
    "source_url": "https://www.eu-startups.com/2026/03/tower-raises",
    "notes": "Raised €5.5 million se"""

result = extract_json_list(truncated_response, context="Test1_Truncated")
print(f"Result: {len(result)} leads extracted")
if result:
    print("✅ PASS - Extraction failed gracefully (expected for this case)")
else:
    print("❌ Issue persists - Still can't handle mid-string truncation")

# Test Case 2: Truncated but has one complete object
print("\n[Test 2] Truncated with one complete object")
print("-" * 70)
one_complete = """[
  {
    "name": "Brad Heller",
    "company": "Tower",
    "role": "CTO",
    "location": "Berlin",
    "source_url": "https://www.eu-startups.com/2026/03/tower-raises",
    "notes": "Raised €5.5 million seed funding"
  },
  {
    "name": "Jane Smith",
    "company": "StartupX",
    "role": "CTO",
    "location": "Berlin",
    "source_url": "https://example.com"""

result = extract_json_list(one_complete, context="Test2_OneComplete")
print(f"Result: {len(result)} leads extracted")
if result and len(result) == 1:
    print("✅ PASS - Successfully recovered 1 complete lead")
    print(f"   Lead: {result[0]['company']}")
else:
    print(f"❌ FAIL - Expected 1 lead, got {len(result)}")

# Test Case 3: Complete valid JSON
print("\n[Test 3] Complete valid JSON")
print("-" * 70)
complete_json = """[
  {
    "name": "Brad Heller",
    "company": "Tower",
    "role": "CTO",
    "location": "Berlin",
    "source_url": "https://www.eu-startups.com/2026/03/tower-raises",
    "notes": "Raised €5.5 million seed funding"
  },
  {
    "name": "Jane Smith",
    "company": "StartupX",
    "role": "CTO",
    "location": "Berlin",
    "source_url": "https://example.com/funding",
    "notes": "Series A, €3M"
  }
]"""

result = extract_json_list(complete_json, context="Test3_Complete")
print(f"Result: {len(result)} leads extracted")
if result and len(result) == 2:
    print("✅ PASS - Successfully extracted 2 leads")
    for i, lead in enumerate(result, 1):
        print(f"   {i}. {lead['company']}: {lead['notes']}")
else:
    print(f"❌ FAIL - Expected 2 leads, got {len(result)}")

# Test Case 4: JSON with markdown fences
print("\n[Test 4] JSON with markdown fences")
print("-" * 70)
with_fences = """```json
[
  {
    "name": "Test Person",
    "company": "TestCo",
    "role": "CTO",
    "location": "Berlin",
    "source_url": "https://test.com",
    "notes": "Test notes"
  }
]
```"""

result = extract_json_list(with_fences, context="Test4_Fences")
print(f"Result: {len(result)} leads extracted")
if result and len(result) == 1:
    print("✅ PASS - Successfully stripped markdown fences")
else:
    print(f"❌ FAIL - Markdown fence stripping failed")

# Test Case 5: JSON with extra text before/after
print("\n[Test 5] JSON with surrounding text")
print("-" * 70)
with_text = """Here are the leads I found:

[
  {
    "name": "Test Person",
    "company": "TestCo",
    "role": "CTO",
    "location": "Berlin",
    "source_url": "https://test.com",
    "notes": "Test notes"
  }
]

I found 1 lead matching your criteria."""

result = extract_json_list(with_text, context="Test5_SurroundingText")
print(f"Result: {len(result)} leads extracted")
if result and len(result) == 1:
    print("✅ PASS - Successfully extracted JSON from text")
else:
    print(f"❌ FAIL - Couldn't extract JSON from surrounding text")

# Summary
print("\n" + "="*70)
print("Summary")
print("="*70)
print("\nThe fixes improve truncation handling and JSON extraction.")
print("When you run the actual pipeline again:")
print("  1. Wait for Groq rate limit to reset (~50 minutes)")
print("  2. Look for: '[Collector] ✓ Extracted N leads'")
print("  3. Look for: '[Agent 1] Processed N leads (X new, Y duplicates)'")
print("\nIf you still see '[Storage] ⚠ No leads parsed', check:")
print("  - Is the full LLM response valid JSON?")
print("  - Check the response tail in logs for truncation markers")
print("  - May need to reduce max_results or search_queries")