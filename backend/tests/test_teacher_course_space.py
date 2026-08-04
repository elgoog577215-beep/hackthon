import tempfile
import unittest
from pathlib import Path

from material_storage import MaterialStorageError
from teacher_course_space import TeacherCourseSpaceRepository, normalize_relative_path, package_folder_paths


class FakeUpload:
    filename = "教学日历.pdf"

    async def read(self):
        return b"%PDF-1.4 sample"


class TeacherCourseSpaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_import_is_owned_classified_and_path_safe(self):
        repository = TeacherCourseSpaceRepository(Path(tempfile.mkdtemp()))
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "春季")
        package = repository.load_owned(created["package_id"], "teacher-a")

        asset = await repository.import_file(package, FakeUpload(), "课程资料/教学日历.pdf", "batch-1")
        repository.save(package)

        self.assertEqual(asset["category"], "school_materials")
        self.assertEqual(len(repository.list_owned("teacher-a")), 1)
        self.assertEqual(repository.list_owned("teacher-b"), [])
        self.assertTrue((repository.root / created["package_id"] / "content" / "课程资料" / "教学日历.pdf").is_file())
        with self.assertRaises(MaterialStorageError):
            normalize_relative_path("../private.docx")

    async def test_school_template_and_custom_folder_exist_on_disk(self):
        root = Path(tempfile.mkdtemp())
        repository = TeacherCourseSpaceRepository(root)
        package = repository.create_package("teacher-a", "数据结构", "2025-2026", "秋季", "school_course_materials")
        package_path = root / package["package_id"]
        self.assertTrue((package_path / "content" / "0、教学大纲").is_dir())
        self.assertTrue((package_path / "files").is_dir())
        loaded = repository.load_owned(package["package_id"], "teacher-a")
        self.assertTrue(all(entry["kind"] == "folder" for entry in loaded["entries"]))
        self.assertNotIn("3、A卷竖版.docx", [entry["name"] for entry in loaded["entries"]])
        self.assertEqual(
            [entry["name"] for entry in loaded["entries"]],
            ["0、教学大纲", "1、教案", "2、PPT", "3、大作业或实验报告", "4、考场记录单、学生签到单", "5、实际考卷"],
        )
        repository.add_folder(loaded, "第 1 讲")
        self.assertTrue((package_path / "content" / "第 1 讲").is_dir())

    async def test_public_package_hides_legacy_file_slots(self):
        repository = TeacherCourseSpaceRepository(Path(tempfile.mkdtemp()))
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "秋季", "school_course_materials")
        package = repository.load_owned(created["package_id"], "teacher-a")
        package["entries"].append({"name": "旧占位.docx", "path": "旧占位.docx", "kind": "slot"})

        public = repository.public(package)

        self.assertNotIn("旧占位.docx", [entry["name"] for entry in public["entries"]])

    async def test_legacy_template_folder_numbers_migrate_on_load(self):
        root = Path(tempfile.mkdtemp())
        repository = TeacherCourseSpaceRepository(root)
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "秋季", "school_course_materials")
        package = repository.load_owned(created["package_id"], "teacher-a")
        entry = next(item for item in package["entries"] if item["name"] == "3、大作业或实验报告")
        entry.update({"name": "12、大作业或实验报告", "path": "12、大作业或实验报告"})
        new_folder = root / created["package_id"] / "content" / "3、大作业或实验报告"
        old_folder = root / created["package_id"] / "content" / "12、大作业或实验报告"
        new_folder.replace(old_folder)
        repository.save(package)

        migrated = repository.load_owned(created["package_id"], "teacher-a")

        self.assertTrue(new_folder.is_dir())
        self.assertFalse(old_folder.exists())
        self.assertIn("3、大作业或实验报告", [item["name"] for item in migrated["entries"]])

    async def test_import_folders_preserves_nested_and_empty_directories(self):
        root = Path(tempfile.mkdtemp())
        repository = TeacherCourseSpaceRepository(root)
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "秋季")
        package = repository.load_owned(created["package_id"], "teacher-a")

        created_folders = repository.import_folders(package, ["整课资料/第一讲/空目录", "整课资料/第二讲"])
        repository.save(package)

        self.assertEqual(len(created_folders), 4)
        self.assertTrue((root / created["package_id"] / "content" / "整课资料" / "第一讲" / "空目录").is_dir())
        self.assertTrue((root / created["package_id"] / "content" / "整课资料" / "第二讲").is_dir())
        self.assertEqual(
            package_folder_paths(package),
            ["整课资料", "整课资料/第一讲", "整课资料/第二讲", "整课资料/第一讲/空目录"],
        )

    async def test_delete_asset_removes_source_and_materialized_copy(self):
        root = Path(tempfile.mkdtemp())
        repository = TeacherCourseSpaceRepository(root)
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "春季")
        package = repository.load_owned(created["package_id"], "teacher-a")
        asset = await repository.import_file(package, FakeUpload(), "第一讲/教学日历.pdf", "batch-1")
        repository.save(package)

        repository.delete_asset(package, asset["asset_id"])

        self.assertFalse((root / created["package_id"] / "files" / asset["stored_name"]).exists())
        self.assertFalse((root / created["package_id"] / "content" / "第一讲" / "教学日历.pdf").exists())
        self.assertEqual(repository.load_owned(created["package_id"], "teacher-a")["assets"], [])

    async def test_delete_folder_cascades_assets_but_not_siblings(self):
        root = Path(tempfile.mkdtemp())
        repository = TeacherCourseSpaceRepository(root)
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "春季")
        package = repository.load_owned(created["package_id"], "teacher-a")
        repository.import_folders(package, ["整课资料/第一讲", "整课资料/第二讲"])
        first = await repository.import_file(package, FakeUpload(), "整课资料/第一讲/教学日历.pdf", "batch-1")
        second = await repository.import_file(package, FakeUpload(), "整课资料/第二讲/教学日历.pdf", "batch-1")
        repository.save(package)

        result = repository.delete_folder(package, "整课资料/第一讲")

        self.assertEqual(result["deleted_assets"], 1)
        self.assertFalse((root / created["package_id"] / "content" / "整课资料" / "第一讲").exists())
        self.assertTrue((root / created["package_id"] / "content" / "整课资料" / "第二讲" / "教学日历.pdf").is_file())
        remaining = repository.load_owned(created["package_id"], "teacher-a")["assets"]
        self.assertEqual([item["asset_id"] for item in remaining], [second["asset_id"]])
        self.assertNotEqual(first["asset_id"], second["asset_id"])
