import requests
import json
import time

COURSE_ID = "183738db-6fcd-47fd-97d9-938b9e60ebbd"
BASE_URL = "http://localhost:8000"

def verify():
    print(f"1. Starting Auto Generation for Course {COURSE_ID}...")
    try:
        res = requests.post(f"{BASE_URL}/courses/{COURSE_ID}/auto_generate")
        if res.status_code == 200:
            data = res.json()
            task_id = data["task_id"]
            status = data["status"]
            print(f"   Task Started: ID={task_id}, Status={status}")
        else:
            print(f"   Error: {res.text}")
            return
    except Exception as e:
        print(f"   Connection Failed: {e}")
        return

    print("\n2. Polling Task Status...")
    for _ in range(3):
        res = requests.get(f"{BASE_URL}/courses/{COURSE_ID}/task")
        if res.status_code == 200:
            task = res.json()
            print(f"   Status: {task.get('status')}, Msg: {task.get('message')}")
        else:
            print(f"   Error fetching task: {res.text}")
        time.sleep(1)

    print("\n3. Pausing Task...")
    res = requests.post(f"{BASE_URL}/tasks/{task_id}/pause")
    if res.status_code == 200:
        print("   Paused successfully.")
    else:
        print(f"   Error pausing: {res.text}")

    print("   Checking status after pause...")
    time.sleep(1)
    res = requests.get(f"{BASE_URL}/courses/{COURSE_ID}/task")
    print(f"   Status: {res.json().get('status')}")

    print("\n4. Resuming Task...")
    res = requests.post(f"{BASE_URL}/tasks/{task_id}/resume")
    if res.status_code == 200:
        print("   Resumed successfully.")
    else:
        print(f"   Error resuming: {res.text}")

    print("   Checking status after resume...")
    time.sleep(1)
    res = requests.get(f"{BASE_URL}/courses/{COURSE_ID}/task")
    print(f"   Status: {res.json().get('status')}")

if __name__ == "__main__":
    verify()