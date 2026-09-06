import os
import sys


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from main import app


def test_legacy_learning_routes_are_not_registered():
    paths = app.openapi()["paths"]
    assert "/api/courses/{course_id}/learning_path" not in paths
    assert "/api/courses/{course_id}/knowledge_mastery" not in paths
    assert "/api/courses/{course_id}/learning_stats" not in paths
    assert "/api/learning-os/snapshot" not in paths


def test_formal_runtime_and_learner_model_are_the_registered_replacements():
    paths = app.openapi()["paths"]
    assert "/api/courses/{course_id}/learning-runtime" in paths
    assert "/api/courses/{course_id}/learner-model" in paths
