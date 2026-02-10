import requests
import json
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8000"

def test_prompts():
    logger.info("Waiting for server...")
    time.sleep(2)
    
    # 1. Test Generate Course (Skeleton)
    logger.info("1. Testing Generate Course Skeleton (Keyword: 'Rust Programming')...")
    start = time.time()
    try:
        res = requests.post(f"{BASE_URL}/generate_course", json={"keyword": "Rust Programming"}, timeout=120)
        logger.info(f"Time taken: {time.time() - start:.2f}s")
        if res.status_code == 200:
            data = res.json()
            nodes = data.get("nodes", [])
            logger.info(f"Total nodes generated: {len(nodes)}")
            
            # Analyze structure
            l2_nodes = [n for n in nodes if n["node_level"] == 2]
            logger.info(f"Level 2 Chapters: {len(l2_nodes)}")
            
            if len(l2_nodes) == 0:
                logger.error("FAILED: No chapters generated.")
                return

            # 2. Test Generate Subnodes
            target_chapter = l2_nodes[0]
            logger.info(f"2. Testing Generate Subnodes for: {target_chapter['node_name']}...")
            
            req_data = {
                "node_id": target_chapter["node_id"],
                "node_name": target_chapter["node_name"],
                "node_level": target_chapter["node_level"]
            }
            start = time.time()
            res_sub = requests.post(f"{BASE_URL}/nodes/{target_chapter['node_id']}/subnodes", json=req_data, timeout=120)
            logger.info(f"Time taken: {time.time() - start:.2f}s")
            
            l3_nodes = []
            if res_sub.status_code == 200:
                l3_nodes = res_sub.json()
                logger.info(f"Generated {len(l3_nodes)} subnodes.")
                for n in l3_nodes:
                    logger.info(f"  - {n['node_name']}")
            else:
                logger.error(f"Error generating subnodes: {res_sub.text}")

            # 3. Test Redefine Content
            if l3_nodes:
                target_node = l3_nodes[0]
                logger.info(f"3. Testing Redefine Content for: {target_node['node_name']}...")
                req_data = {
                    "node_id": target_node["node_id"],
                    "node_name": target_node["node_name"],
                    "original_content": target_node.get("node_content", ""),
                    "user_requirement": "教科书级详细正文"
                }
                start = time.time()
                res_content = requests.post(f"{BASE_URL}/nodes/{target_node['node_id']}/redefine", json=req_data, timeout=120)
                logger.info(f"Time taken: {time.time() - start:.2f}s")
                
                if res_content.status_code == 200:
                    content = res_content.json().get("node_content", "")
                    logger.info(f"Content length: {len(content)} chars")
                    logger.info("Preview (first 200 chars):")
                    logger.info(content[:200])
                else:
                    logger.error(f"Error redefining: {res_content.text}")
                    
        else:
            logger.error(f"Error generating course: {res.text}")
            
    except Exception as e:
        logger.error(f"Exception: {e}")

if __name__ == "__main__":
    test_prompts()
