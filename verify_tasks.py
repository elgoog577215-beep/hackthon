
import requests
import sys

try:
    response = requests.get("http://localhost:8000/tasks")
    response.raise_for_status()
    tasks = response.json()
    if isinstance(tasks, list):
        print(f"Success: Fetched {len(tasks)} tasks.")
        for t in tasks[:3]:
            print(f" - Task {t.get('id')}: {t.get('status')} ({t.get('course_id')})")
    else:
        print("Error: Response is not a list.")
        sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
