"""
存储层测试
验证 MockStorage 的 CRUD 操作和 Storage 类的核心逻辑。
"""

import pytest
from .conftest import MockStorage, make_course, make_annotation


class TestMockStorageCourses:
    """课程 CRUD 测试"""

    def test_save_and_load_course(self, mock_storage: MockStorage):
        course = make_course(course_id="c1")
        mock_storage.save_course("c1", course)
        loaded = mock_storage.load_course("c1")
        assert loaded is not None
        assert loaded["course_id"] == "c1"
        assert loaded["course_name"] == "测试课程"

    def test_load_nonexistent_course(self, mock_storage: MockStorage):
        assert mock_storage.load_course("nonexistent") is None

    def test_list_courses(self, mock_storage: MockStorage):
        mock_storage.save_course("c1", make_course(course_id="c1", course_name="课程A"))
        mock_storage.save_course("c2", make_course(course_id="c2", course_name="课程B"))
        courses = mock_storage.list_courses()
        assert len(courses) == 2
        names = {c["course_name"] for c in courses}
        assert names == {"课程A", "课程B"}

    def test_delete_course(self, mock_storage: MockStorage):
        mock_storage.save_course("c1", make_course(course_id="c1"))
        mock_storage.delete_course("c1")
        assert mock_storage.load_course("c1") is None
        assert len(mock_storage.list_courses()) == 0

    def test_delete_nonexistent_course_no_error(self, mock_storage: MockStorage):
        mock_storage.delete_course("nonexistent")  # 不应抛异常

    def test_save_course_overwrites(self, mock_storage: MockStorage):
        mock_storage.save_course("c1", make_course(course_id="c1", course_name="V1"))
        mock_storage.save_course("c1", make_course(course_id="c1", course_name="V2"))
        loaded = mock_storage.load_course("c1")
        assert loaded["course_name"] == "V2"

    def test_load_returns_deep_copy(self, mock_storage: MockStorage):
        """确保 load 返回的是副本，修改不影响存储"""
        mock_storage.save_course("c1", make_course(course_id="c1"))
        loaded = mock_storage.load_course("c1")
        loaded["course_name"] = "MODIFIED"
        original = mock_storage.load_course("c1")
        assert original["course_name"] == "测试课程"


class TestMockStorageAnnotations:
    """标注 CRUD 测试"""

    def test_save_and_load_annotations(self, mock_storage: MockStorage):
        anno = make_annotation("node1")
        mock_storage.save_annotation(anno)
        all_annos = mock_storage.load_annotations()
        assert len(all_annos) == 1
        assert all_annos[0]["node_id"] == "node1"

    def test_get_annotations_by_node(self, mock_storage: MockStorage):
        mock_storage.save_annotation(make_annotation("node1", anno_id="a1"))
        mock_storage.save_annotation(make_annotation("node2", anno_id="a2"))
        mock_storage.save_annotation(make_annotation("node1", anno_id="a3"))
        result = mock_storage.get_annotations_by_node("node1")
        assert len(result) == 2

    def test_delete_annotation(self, mock_storage: MockStorage):
        mock_storage.save_annotation(make_annotation("node1", anno_id="a1"))
        mock_storage.save_annotation(make_annotation("node1", anno_id="a2"))
        mock_storage.delete_annotation("a1")
        remaining = mock_storage.load_annotations()
        assert len(remaining) == 1
        assert remaining[0]["anno_id"] == "a2"

    def test_update_annotation_content(self, mock_storage: MockStorage):
        mock_storage.save_annotation(make_annotation("node1", anno_id="a1", content="原始内容"))
        result = mock_storage.update_annotation("a1", "更新后的内容")
        assert result is True
        annos = mock_storage.load_annotations()
        assert annos[0]["answer"] == "更新后的内容"

    def test_update_annotation_field(self, mock_storage: MockStorage):
        mock_storage.save_annotation(make_annotation("node1", anno_id="a1"))
        result = mock_storage.update_annotation_field("a1", "source_type", "ai")
        assert result is True
        annos = mock_storage.load_annotations()
        assert annos[0]["source_type"] == "ai"

    def test_update_nonexistent_annotation(self, mock_storage: MockStorage):
        assert mock_storage.update_annotation("nonexistent", "content") is False
        assert mock_storage.update_annotation_field("nonexistent", "field", "val") is False
