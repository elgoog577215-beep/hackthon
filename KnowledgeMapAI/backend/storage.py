import json
import os
import uuid
import shutil
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

DATA_DIR = "data"
COURSES_DIR = os.path.join(DATA_DIR, "courses")
ANNOTATIONS_FILE = os.path.join(DATA_DIR, "annotations.json")
# Legacy file for migration
LEGACY_COURSE_FILE = os.path.join(DATA_DIR, "course_tree.json")

class Storage:
    def __init__(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        if not os.path.exists(COURSES_DIR):
            os.makedirs(COURSES_DIR)
        
        # Initialize Cache
        self.courses_cache: Dict[str, dict] = {}
        self.annotations_cache: Optional[List[dict]] = None
        self._cache_initialized = False

        # Migrate legacy course if exists
        if os.path.exists(LEGACY_COURSE_FILE):
            try:
                with open(LEGACY_COURSE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data and "nodes" in data and len(data["nodes"]) > 0:
                        course_id = str(uuid.uuid4())
                        new_path = os.path.join(COURSES_DIR, f"{course_id}.json")
                        with open(new_path, 'w', encoding='utf-8') as nf:
                            json.dump(data, nf, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.warning(f"Migration failed: {e}")
            # Rename legacy file to avoid re-migration
            try:
                os.rename(LEGACY_COURSE_FILE, LEGACY_COURSE_FILE + ".bak")
            except Exception:
                pass

        if not os.path.exists(ANNOTATIONS_FILE):
            with open(ANNOTATIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump([], f)
    
    def _ensure_cache(self):
        """Load all courses into cache if not initialized"""
        if self._cache_initialized:
            return

        if os.path.exists(COURSES_DIR):
            for filename in os.listdir(COURSES_DIR):
                if filename.endswith(".json"):
                    course_id = filename.replace(".json", "")
                    filepath = os.path.join(COURSES_DIR, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            self.courses_cache[course_id] = data
                    except Exception as e:
                        logger.warning(f"Failed to load course {filename}: {e}")
                        continue
        self._cache_initialized = True

    def list_courses(self) -> List[Dict]:
        self._ensure_cache()
        courses = []
        for course_id, data in self.courses_cache.items():
            courses.append({
                "course_id": course_id,
                "course_name": data.get("course_name", "未命名课程"),
                "node_count": len(data.get("nodes", []))
            })
        return courses

    def save_course(self, course_id: str, tree: dict):
        # Update Cache
        self._ensure_cache()
        self.courses_cache[course_id] = tree
        
        # Write to Disk
        filepath = os.path.join(COURSES_DIR, f"{course_id}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(tree, f, ensure_ascii=False, indent=2)

    def load_course(self, course_id: str) -> dict:
        self._ensure_cache()
        return self.courses_cache.get(course_id, {})
    
    def delete_course(self, course_id: str):
        self._ensure_cache()
        if course_id in self.courses_cache:
            del self.courses_cache[course_id]
            
        filepath = os.path.join(COURSES_DIR, f"{course_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)

    def save_annotation(self, annotation: dict):
        annotations = self.load_annotations()
        
        # Check if exists and update
        existing_index = next((i for i, a in enumerate(annotations) if a.get('anno_id') == annotation.get('anno_id')), -1)
        
        if existing_index >= 0:
            annotations[existing_index] = annotation
        else:
            annotations.append(annotation)
            
        # Cache is updated by reference since load_annotations returns the list object
        # But to be safe and explicit:
        self.annotations_cache = annotations
        
        with open(ANNOTATIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(annotations, f, ensure_ascii=False, indent=2)

    def load_annotations(self) -> List[dict]:
        if self.annotations_cache is not None:
            return self.annotations_cache

        try:
            with open(ANNOTATIONS_FILE, 'r', encoding='utf-8') as f:
                self.annotations_cache = json.load(f)
        except json.JSONDecodeError:
            self.annotations_cache = []
            
        return self.annotations_cache
    
    def get_annotations_by_node(self, node_id: str) -> List[dict]:
        annotations = self.load_annotations()
        return [a for a in annotations if a.get('node_id') == node_id]

    def delete_annotation(self, anno_id: str):
        annotations = self.load_annotations()
        new_annotations = [a for a in annotations if a.get('anno_id') != anno_id]
        self.annotations_cache = new_annotations
        
        with open(ANNOTATIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(new_annotations, f, ensure_ascii=False, indent=2)

    def update_annotation(self, anno_id: str, content: str):
        annotations = self.load_annotations()
        updated = False
        for anno in annotations:
            if anno.get('anno_id') == anno_id:
                anno['answer'] = content
                # Update summary
                anno['anno_summary'] = content[:50] + '...' if len(content) > 50 else content
                updated = True
                break
        
        if updated:
            self.annotations_cache = annotations
            with open(ANNOTATIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(annotations, f, ensure_ascii=False, indent=2)

storage = Storage()
