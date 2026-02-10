import requests
import time
import sys
import uuid
import random
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8000"

def test_generate_course(keyword):
    logger.info(f"Testing generate_course with keyword: {keyword}")
    try:
        response = requests.post(f"{BASE_URL}/generate_course", json={"keyword": keyword})
        if response.status_code == 200:
            data = response.json()
            if "nodes" in data and len(data["nodes"]) > 0:
                logger.info("  Success")
                return data["nodes"][0]["node_id"]
            else:
                logger.error("  Failed: No nodes returned")
        else:
            logger.error(f"  Failed: Status {response.status_code}")
    except Exception as e:
        logger.error(f"  Error: {e}")
    return None

def test_subnodes(node_id):
    logger.info(f"Testing subnodes for node: {node_id}")
    try:
        response = requests.post(f"{BASE_URL}/nodes/{node_id}/subnodes", json={
            "node_id": node_id,
            "node_name": "Test Node",
            "node_level": 1
        })
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                logger.info("  Success")
                return True
            else:
                logger.error("  Failed: Empty list or invalid format")
        else:
            logger.error(f"  Failed: Status {response.status_code}")
    except Exception as e:
        logger.error(f"  Error: {e}")
    return False

def main():
    logger.info("Waiting for server to start...")
    # Wait for server port to be open
    for i in range(30):
        try:
            requests.get(BASE_URL)
            break
        except:
            time.sleep(1)
            print(".", end="", flush=True)
    print("\n")
    logger.info("Server ready.")

    success_count = 0
    total_tests = 10
    
    keywords = ["Python", "Vue", "FastAPI", "Design", "AI", "History", "Math", "Physics", "Art", "Music"]
    
    for i in range(total_tests):
        logger.info(f"--- Test Iteration {i+1}/{total_tests} ---")
        keyword = keywords[i]
        node_id = test_generate_course(keyword)
        if node_id:
            if test_subnodes(node_id):
                success_count += 1
        
        time.sleep(0.5)

    logger.info(f"Total Success: {success_count}/{total_tests}")
    if success_count == total_tests:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
