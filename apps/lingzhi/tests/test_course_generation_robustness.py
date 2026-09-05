
import sys
import os
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from ai_service import AIService

# Mock response with sub_nodes
MOCK_RESPONSE_WITH_SUB_NODES = """
```json
{
  "course_name": "Test Course",
  "nodes": [
    {
      "node_name": "Chapter 1",
      "node_content": "",
      "sub_nodes": [
        {"node_name": "1.1 Section 1", "node_content": ""},
        {"node_name": "1.2 Section 2", "node_content": ""}
      ]
    },
    {
      "node_name": "Chapter 2",
      "node_content": "",
      "sub_nodes": []
    }
  ]
}
```
"""

# Mock response without sub_nodes (simulating failure case)
MOCK_RESPONSE_WITHOUT_SUB_NODES = """
```json
{
  "course_name": "Test Course 2",
  "nodes": [
    {
      "node_name": "Chapter 1",
      "node_content": ""
    },
    {
      "node_name": "Chapter 2",
      "node_content": ""
    }
  ]
}
```
"""

# Mock response for sub_nodes generation
MOCK_SUB_NODES_RESPONSE = """
```json
{
  "sub_nodes": [
    {"node_name": "X.1 Generated SubNode 1", "node_content": ""},
    {"node_name": "X.2 Generated SubNode 2", "node_content": ""}
  ]
}
```
"""

class MockAIService(AIService):
    def __init__(self, main_response):
        # Skip super().__init__ to avoid loading API keys
        self.api_key = "test_key"
        self.api_base = "http://test"
        self.model_smart = "test_model"
        self.model_fast = "test_model_fast"
        self.client = MagicMock()
        self.main_response = main_response

    async def _call_llm(self, prompt, system_prompt, use_fast_model=False):
        # Detect which prompt is being used
        if "generate_course" in system_prompt or "generate_course" in prompt or "生成一份专业且系统的课程大纲" in prompt:
            print(f"Mocking Course Generation LLM call")
            return self.main_response
        elif "generate_sub_nodes" in system_prompt or "当前节点信息" in prompt:
            print(f"Mocking Sub-nodes Generation LLM call for prompt: {prompt[:30]}...")
            return MOCK_SUB_NODES_RESPONSE
        else:
            print(f"Unknown prompt: {prompt[:50]}...")
            return "{}"

async def run_test():
    print("--- Test 1: Response with sub_nodes (Mixed) ---")
    # Chapter 1 has sub-nodes, Chapter 2 has empty sub-nodes (should trigger fallback)
    service1 = MockAIService(MOCK_RESPONSE_WITH_SUB_NODES)
    result1 = await service1.generate_course("Test Keyword")
    
    nodes = result1.get("nodes", [])
    print(f"Total nodes: {len(nodes)}")
    l1_nodes = [n for n in nodes if n["node_level"] == 1]
    l2_nodes = [n for n in nodes if n["node_level"] == 2]
    print(f"L1 nodes: {len(l1_nodes)}")
    print(f"L2 nodes: {len(l2_nodes)}")

    # We expect Chapter 2 to trigger fallback and generate 2 sub-nodes
    # Chapter 1 has 2 sub-nodes.
    # Total L2 nodes should be 4.
    if len(l2_nodes) == 4:
        print("PASS: Fallback triggered and merged correctly.")
    else:
        print(f"FAIL: Expected 4 L2 nodes, got {len(l2_nodes)}.")

    print("\n--- Test 2: Response without sub_nodes (All missing) ---")
    service2 = MockAIService(MOCK_RESPONSE_WITHOUT_SUB_NODES)
    result2 = await service2.generate_course("Test Keyword 2")

    nodes2 = result2.get("nodes", [])
    l1_nodes2 = [n for n in nodes2 if n["node_level"] == 1]
    l2_nodes2 = [n for n in nodes2 if n["node_level"] == 2]
    print(f"L1 nodes: {len(l1_nodes2)}")
    print(f"L2 nodes: {len(l2_nodes2)}")
    
    # We expect 2 chapters * 2 sub-nodes = 4 L2 nodes
    if len(l2_nodes2) == 4:
        print("PASS: Fallback triggered for all chapters.")
    else:
        print(f"FAIL: Expected 4 L2 nodes, got {len(l2_nodes2)}.")

if __name__ == "__main__":
    asyncio.run(run_test())
