import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))


def test_ai_service_facade_excludes_legacy_course_methods():
    from ai_service import ai_service

    assert not hasattr(ai_service, "generate_course")
    assert not hasattr(ai_service, "generate_node_content")
    assert not hasattr(ai_service, "redefine_content")
    assert not hasattr(ai_service, "extend_content")
    assert not hasattr(ai_service, "locate_node")

    assert hasattr(ai_service, "generate_quiz")
    assert hasattr(ai_service, "answer_question_stream")
    assert hasattr(ai_service, "generate_profile")
