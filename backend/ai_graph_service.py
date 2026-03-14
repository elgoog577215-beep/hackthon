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
                
                # Priority 2: Match by similarity score (replaces simple substring)
                if not best_match_id:
                    node_label = node.get("label", "")
                    if node_label:
                        best_score = -1.0
                        for n in course_nodes:
                            name = n.get("node_name", "")
                            if not name:
                                continue
                            # Character overlap ratio: count common chars / max length
                            common = sum(1 for c in node_label if c in name)
                            score = common / max(len(node_label), len(name))
                            if score > best_score:
                                best_score = score
                                best_match_id = n.get("node_id")
                        # Require minimum threshold
                        min_threshold = 0.3
                        if best_score < min_threshold:
                            logger.warning(
                                f"Low similarity score ({best_score:.2f}) for node '{node_label}', "
                                f"rejecting match"
                            )
                            best_match_id = None
                
                # Fallback: Prefer leaf nodes (higher node_level) over root chapters
                if not best_match_id and course_nodes:
                    # Sort by node_level descending to prefer more specific (leaf) nodes
                    sorted_nodes = sorted(
                        course_nodes,
                        key=lambda n: n.get("node_level", 0),
                        reverse=True,
                    )
                    best_match_id = sorted_nodes[0].get("node_id")
                    logger.warning(
                        f"No confident match for node '{node.get('label', '')}', "
                        f"falling back to leaf node '{sorted_nodes[0].get('node_name', '')}'"
                    )
                
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
            "implements", "contrasts_with", "leads_to"
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
                        "relation": "contains"
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
                    "label": "包含"
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
                    "label": "包含"
                })
        
        # Add some cross-references between same-level nodes
        level_groups = {}
        for node in graph_nodes:
            level = node.get("type", "basic")
            if level not in level_groups:
                level_groups[level] = []
            level_groups[level].append(node)
        
        # Connect nodes within same level
        for level, group in level_groups.items():
            for i in range(len(group) - 1):
                if len(graph_edges) < 30:  # Limit total edges
                    graph_edges.append({
                        "source": group[i]["id"],
                        "target": group[i + 1]["id"],
                        "relation": "related",
                        "label": "关联"
                    })
        
        return {
            "nodes": graph_nodes,
            "edges": graph_edges
        }

    def locate_node(self, keyword: str, all_nodes: List[Dict]) -> Dict:
        """
        定位节点
        """
        for node in all_nodes:
            if keyword in node['node_name']:
                return {
                    "match_node_id": node['node_id'],
                    "match_node_name": node['node_name'],
                    "node_path": "Path/To/Node"  # Mock path
                }
        return {}
