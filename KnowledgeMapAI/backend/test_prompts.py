import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_prompts():
    print("Waiting for server...")
    time.sleep(2)
    
    # 1. Test Generate Course (Skeleton)
    print("\n1. Testing Generate Course Skeleton (Keyword: 'Rust Programming')...")
    start = time.time()
    try:
        res = requests.post(f"{BASE_URL}/generate_course", json={"keyword": "Rust Programming"}, timeout=120)
        print(f"Time taken: {time.time() - start:.2f}s")
        if res.status_code == 200:
            data = res.json()
            nodes = data.get("nodes", [])
            print(f"Total nodes generated: {len(nodes)}")
            
            # Analyze structure
            l2_nodes = [n for n in nodes if n["node_level"] == 2]
            print(f"Level 2 Chapters: {len(l2_nodes)}")
            
            if len(l2_nodes) == 0:
                print("FAILED: No chapters generated.")
                return

            # 2. Test Generate Subnodes
            target_chapter = l2_nodes[0]
            print(f"\n2. Testing Generate Subnodes for: {target_chapter['node_name']}...")
            
            req_data = {
                "node_id": target_chapter["node_id"],
                "node_name": target_chapter["node_name"],
                "node_level": target_chapter["node_level"]
            }
            start = time.time()
            res_sub = requests.post(f"{BASE_URL}/nodes/{target_chapter['node_id']}/subnodes", json=req_data, timeout=120)
            print(f"Time taken: {time.time() - start:.2f}s")
            
            l3_nodes = []
            if res_sub.status_code == 200:
                l3_nodes = res_sub.json()
                print(f"Generated {len(l3_nodes)} subnodes.")
                for n in l3_nodes:
                    print(f"  - {n['node_name']}")
            else:
                print(f"Error generating subnodes: {res_sub.text}")

            # 3. Test Redefine Content
            if l3_nodes:
                target_node = l3_nodes[0]
                print(f"\n3. Testing Redefine Content for: {target_node['node_name']}...")
                req_data = {
                    "node_id": target_node["node_id"],
                    "node_name": target_node["node_name"],
                    "original_content": target_node.get("node_content", ""),
                    "user_requirement": "教科书级详细正文"
                }
                start = time.time()
                res_content = requests.post(f"{BASE_URL}/nodes/{target_node['node_id']}/redefine", json=req_data, timeout=120)
                print(f"Time taken: {time.time() - start:.2f}s")
                
                if res_content.status_code == 200:
                    content = res_content.json().get("node_content", "")
                    print(f"Content length: {len(content)} chars")
                    print("Preview (first 200 chars):")
                    print(content[:200])
                else:
                    print(f"Error redefining: {res_content.text}")
                    
        else:
            print(f"Error generating course: {res.text}")
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_prompts()
