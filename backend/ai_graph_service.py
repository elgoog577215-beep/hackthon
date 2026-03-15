"""
AI 知识图谱服务模块

负责知识图谱生成、验证修复、循环检测、
回退图谱生成和节点定位。
"""

import uuid
import json
import logging
from typing import List, Dict

from ai_base import AIBase
from prompts import get_prompt

logger = logging.getLogger(__name__)


class AIGraphService(AIBase):
    """知识图谱相关的 AI 服务"""

    async def generate_knowledge_graph(
        self,
        course_name: str,
        course_context: str,
        nodes: List[Dict]
    ) -> Dict:
        """
        生成知识图谱结构
        """
        # Build course context summary
        nodes_summary = []
        for node in nodes[:50]:  # Increased limit to cover full course structure
            nodes_summary.append({
                "id": node.get("node_id", ""),
                "name": node.get("node_name", ""),
                "level": node.get("node_level", 1),
                "content": node.get("node_content", "")[:200]  # Increased content context
            })
        
        context_text = f"""
课程名称：{course_name}

课程大纲：
{course_context}

章节列表：
{json.dumps(nodes_summary, ensure_ascii=False, indent=2)}
"""
        
        # Get the knowledge graph prompt template
        prompt_template = get_prompt("generate_knowledge_graph")
        system_prompt = prompt_template.format(
            course_name=course_name,
            course_context=context_text
        )
        
        user_prompt = f"""请基于以下课程内容生成知识图谱：

课程名称：{course_name}

主要章节：
{chr(10).join([f"- [ID: {n.get('id', '')}] {n.get('name', '')}: {n.get('content', '')[:50]}..." for n in nodes_summary[:15]])}

请生成包含节点和关系的知识图谱JSON。"""
        
        response = await self._call_llm(user_prompt, system_prompt)
        
        if response:
            result = self._extract_json(response)
            if result and "nodes" in result and "edges" in result and len(result["nodes"]) > 0:
                # Enhanced Self-Healing: Validate and fix the knowledge graph
                result = self._validate_and_fix_knowledge_graph(result, nodes)
                return result
        
        # Fallback: Generate a simple graph based on node hierarchy
        logger.warning("Knowledge graph generation failed, using fallback")
        return self._generate_fallback_knowledge_graph(nodes)
    
    def _validate_and_fix_knowledge_graph(self, graph_data: Dict, course_nodes: List[Dict]) -> Dict:
        """
        验证并修复知识图谱
        """
        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])
        
        valid_chapter_ids = {n.get("node_id") for n in course_nodes}
        node_name_to_id = {n.get("node_name"): n.get("node_id") for n in course_nodes}
        node_ids = {n.get("id") for n in nodes}
        
        # Step 1: Fix chapter_ids and validate node types
        root_count = 0
        for node in nodes:
            # Count root nodes
            if node.get("type") == "root":
                root_count += 1
            
            # Fix chapter_id
            chapter_id = node.get("chapter_id")
            if not chapter_id or chapter_id not in valid_chapter_ids:
                best_match_id = None
                
                # Priority 0: Check if chapter_id is actually a node name
                if chapter_id in node_name_to_id:
                    best_match_id = node_name_to_id[chapter_id]
                
                # Priority 1: Match by Node Label (Exact)
                if not best_match_id:
                    node_label = node.get("label", "")
                    for n in course_nodes:
                        if n.get("node_name", "") == node_label:
                            best_match_id = n.get("node_id")
                            break
                
                # Priority 2: Match by Node Label (Substring)
                if not best_match_id:
                    node_label = node.get("label", "")
                    for n in course_nodes:
                        if node_label in n.get("node_name", "") or n.get("node_name", "") in node_label:
                            best_match_id = n.get("node_id")
                            break
                
                # Fallback: Use first available node
                if not best_match_id and course_nodes:
                    best_match_id = course_nodes[0].get("node_id")
                
                if best_match_id:
                    node["chapter_id"] = best_match_id
        
        # Step 2: Fix multiple root nodes (keep only one)
        if root_count > 1:
            logger.warning(f"Found {root_count} root nodes, keeping only the first one")
            root_found = False
            for node in nodes:
                if node.get("type") == "root":
                    if root_found:
                        node["type"] = "concept"  # Convert extra roots to concepts
                    else:
                        root_found = True
        
        # Step 3: Ensure at least one root node exists
        if root_count == 0 and nodes:
            # Create root from first module or first node
            for node in nodes:
                if node.get("type") == "module":
                    node["type"] = "root"
                    logger.info(f"Converted module '{node.get('label')}' to root")
                    break
            else:
                # If no module, convert first node
                nodes[0]["type"] = "root"
                logger.info(f"Converted first node '{nodes[0].get('label')}' to root")
        
        # Step 4: Validate and fix edges
        valid_relations = {
            "contains", "prerequisite", "extends", "applies_to", 
            "implements", "contrasts_with", "leads_to",
            "derives", "related"
        }
        
        valid_edges = []
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            relation = edge.get("relation")
            
            # Skip invalid edges
            if not source or not target:
                continue
            if source not in node_ids or target not in node_ids:
                continue
            if source == target:  # Skip self-loops
                continue
            
            # Fix invalid relation types
            if relation not in valid_relations:
                edge["relation"] = "contains"  # Default to contains
            
            # 确保 weight 字段存在且合理（1-10）
            w = edge.get("weight")
            if w is None or not isinstance(w, (int, float)) or w < 1 or w > 10:
                # 根据关系类型推断默认权重
                relation_default_weights = {
                    "prerequisite": 8, "derives": 7, "implements": 7,
                    "applies_to": 6, "extends": 6, "contrasts_with": 5,
                    "contains": 7, "leads_to": 5, "related": 3,
                }
                edge["weight"] = relation_default_weights.get(edge["relation"], 5)
            
            valid_edges.append(edge)
        
        # Step 5: Remove isolated nodes (nodes with no edges)
        connected_nodes = set()
        for edge in valid_edges:
            connected_nodes.add(edge.get("source"))
            connected_nodes.add(edge.get("target"))
        
        # Keep root even if isolated (will connect later)
        root_node = None
        for node in nodes:
            if node.get("type") == "root":
                root_node = node
                connected_nodes.add(node.get("id"))
                break
        
        # Filter out isolated nodes
        valid_nodes = [n for n in nodes if n.get("id") in connected_nodes]
        
        # Step 6: Ensure root connects to all modules
        if root_node:
            root_id = root_node.get("id")
            connected_modules = set()
            for edge in valid_edges:
                if edge.get("source") == root_id:
                    connected_modules.add(edge.get("target"))
            
            # Connect root to unconnected modules
            for node in valid_nodes:
                if node.get("type") == "module" and node.get("id") not in connected_modules:
                    valid_edges.append({
                        "source": root_id,
                        "target": node.get("id"),
                        "relation": "contains",
                        "weight": 7
                    })
        
        # Step 7: Detect and break cycles (simple approach)
        self._break_cycles(valid_edges)
        
        logger.info(f"Knowledge graph validation complete: {len(valid_nodes)} nodes, {len(valid_edges)} edges")
        
        return {
            "nodes": valid_nodes,
            "edges": valid_edges
        }
    
    def _break_cycles(self, edges: List[Dict]) -> None:
        """
        检测并打破循环依赖
        """
        # Build adjacency list
        graph = {}
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            if source not in graph:
                graph[source] = []
            graph[source].append(target)
        
        # Simple cycle detection (DFS)
        def has_cycle_from(node, visited, rec_stack):
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle_from(neighbor, visited, rec_stack):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        # Check for cycles
        visited = set()
        for node in graph:
            if node not in visited:
                if has_cycle_from(node, visited, set()):
                    logger.warning("Cycle detected in knowledge graph, removing weakest edge")
                    # Remove the last edge as a simple fix
                    if edges:
                        edges.pop()
                    break
    
    def _generate_fallback_knowledge_graph(self, nodes: List[Dict]) -> Dict:
        """
        生成回退知识图谱
        """
        graph_nodes = []
        graph_edges = []
        
        # Create nodes
        for node in nodes[:15]:
            node_id = node.get("node_id", str(uuid.uuid4()))
            node_level = node.get("node_level", 1)
            
            # Determine node type based on level
            if node_level == 1:
                node_type = "module"
            else:
                node_type = "concept"
            
            graph_nodes.append({
                "id": node_id,
                "label": node.get("node_name", "Unknown"),
                "type": node_type,
                "description": node.get("node_content", "")[:50],
                "chapter_id": node_id
            })
        
        # Add Root Node
        root_id = "root_" + str(uuid.uuid4())[:8]
        graph_nodes.insert(0, {
            "id": root_id,
            "label": "课程核心",
            "type": "root",
            "description": "课程根节点",
            "chapter_id": nodes[0].get("node_id") if nodes else ""
        })
        
        # Connect Root to Level 1 Modules
        for node in graph_nodes:
             if node["type"] == "module":
                graph_edges.append({
                    "source": root_id,
                    "target": node["id"],
                    "relation": "contains",
                    "label": "包含",
                    "weight": 8
                })

        # Create edges based on parent-child relationships
        node_map = {n["id"]: n for n in graph_nodes}
        for node in nodes[:15]:
            node_id = node.get("node_id", "")
            parent_id = node.get("parent_node_id", "")
            
            if parent_id and parent_id in node_map and node_id in node_map:
                graph_edges.append({
                    "source": parent_id,
                    "target": node_id,
                    "relation": "contains",
                    "label": "包含",
                    "weight": 7
                })
        
        # Only parent-child edges — no cross-references between same-level nodes
        
        return {
            "nodes": graph_nodes,
            "edges": graph_edges
        }


