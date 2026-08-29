import tempfile
import unittest
from pathlib import Path

from material_storage import MaterialStorageError
from teacher_course_space import (
    TeacherCourseSpaceRepository,
    classify_document_type,
    normalize_relative_path,
    package_folder_paths,
)


class FakeUpload:
    filename = "教学日历.pdf"

    async def read(self):
        return b"%PDF-1.4 sample"


class TeacherCourseSpaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_package_starts_in_material_preparation_and_can_finish(self):
        repository = TeacherCourseSpaceRepository(Path(tempfile.mkdtemp()))
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "春季")

        self.assertEqual(created["preparation_status"], "pending")

        package = repository.load_owned(created["package_id"], "teacher-a")
        completed = repository.update_preparation_status(package, "completed")

        self.assertEqual(completed["preparation_status"], "completed")
        self.assertEqual(
            repository.load_owned(created["package_id"], "teacher-a")["preparation_status"],
            "completed",
        )

    async def test_legacy_package_without_preparation_state_stays_completed(self):
        repository = TeacherCourseSpaceRepository(Path(tempfile.mkdtemp()))
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "春季")
        package = repository.load_owned(created["package_id"], "teacher-a")
        package.pop("preparation_status")

        self.assertEqual(repository.public(package)["preparation_status"], "completed")

    async def test_import_is_owned_classified_and_path_safe(self):
        repository = TeacherCourseSpaceRepository(Path(tempfile.mkdtemp()))
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "春季")
        package = repository.load_owned(created["package_id"], "teacher-a")

        asset = await repository.import_file(package, FakeUpload(), "课程资料/教学日历.pdf", "batch-1")
        repository.save(package)

        self.assertEqual(asset["category"], "school_materials")
        self.assertEqual(asset["document_type"], "school_material")
        self.assertEqual(len(repository.list_owned("teacher-a")), 1)
        self.assertEqual(repository.list_owned("teacher-b"), [])
        self.assertTrue((repository.root / created["package_id"] / "content" / "课程资料" / "教学日历.pdf").is_file())
        with self.assertRaises(MaterialStorageError):
            normalize_relative_path("../private.docx")

    async def test_document_type_is_explainable_and_teacher_correctable(self):
        repository = TeacherCourseSpaceRepository(Path(tempfile.mkdtemp()))
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "春季")
        package = repository.load_owned(created["package_id"], "teacher-a")

        self.assertEqual(classify_document_type("已有资料/第一讲课件.pptx")[0], "ppt")
        asset = await repository.import_file(
            package, FakeUpload(), "已有资料/第一讲教案.pdf", "batch-1"
        )
        self.assertEqual(asset["document_type"], "lesson_plan")

        updated = repository.update_asset_classification(
            package, asset["asset_id"], document_type="script"
        )

        self.assertEqual(updated["document_type"], "script")
        self.assertEqual(updated["document_type_reason"], "教师确认")
        self.assertEqual(updated["classification_source"], "teacher")

    async def test_understanding_persists_four_dimensions_without_overwriting_teacher(self):
        repository = TeacherCourseSpaceRepository(Path(tempfile.mkdtemp()))
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "春季")
        package = repository.load_owned(created["package_id"], "teacher-a")
        asset = await repository.import_file(package, FakeUpload(), "第一讲教案.pdf", "batch-1")
        repository.update_asset_classification(package, asset["asset_id"], document_type="script")

        public = repository.apply_material_understanding(package, {
            "schema_version": "course_material_understanding_v1",
            "engine_version": "hybrid_classifier_v1",
            "status": "ai_completed",
            "analyzed_at": "2026-08-27T00:00:00+00:00",
            "assets": [{
                "asset_id": asset["asset_id"],
                "document_type": "lesson_plan",
                "confidence": 0.91,
                "reason": "AI判断为教案",
                "analysis_source": "ai",
                "course_alignment": {"match": "matched", "confidence": 0.9, "reason": "属于当前课程"},
                "structure_matches": [{"node_id": "lesson-1", "title": "第一讲", "confidence": 0.9}],
                "version_role": "current",
                "version_reason": "当前版本",
                "related_asset_ids": [],
            }],
            "relationships": [],
            "missing_document_types": ["outline"],
            "low_confidence_asset_ids": [],
        })

        saved = public["assets"][0]
        self.assertEqual(saved["document_type"], "script")
        self.assertEqual(saved["classification_source"], "teacher")
        self.assertEqual(saved["course_alignment"]["match"], "matched")
        self.assertEqual(saved["structure_matches"][0]["node_id"], "lesson-1")
        self.assertEqual(saved["version_role"], "current")
        self.assertEqual(public["material_understanding"]["status"], "ai_completed")

    async def test_material_absorption_decision_and_partial_execution_are_idempotent(self):
        repository = TeacherCourseSpaceRepository(Path(tempfile.mkdtemp()))
        created = repository.create_package(
            "teacher-a", "数据结构", "2026-2027", "秋季", course_id="course-1"
        )
        package = repository.load_owned(created["package_id"], "teacher-a")
        first = await repository.import_file(package, FakeUpload(), "第一讲教案.pdf", "batch-1")
        second = await repository.import_file(package, FakeUpload(), "第一讲讲稿.pdf", "batch-1")
        repository.update_asset_absorption_decision(
            package,
            first["asset_id"],
            role="primary",
            target_scope_id="lesson-1",
            version_role="current",
        )
        self.assertEqual(package["assets"][0]["absorption_decision"]["role"], "primary")

        plan = {
            "package_id": created["package_id"],
            "course_id": "course-1",
            "plan_id": "plan-1",
            "status": "ready",
            "targets": [
                {"target_id": "lesson-plan:lesson-1"},
                {"target_id": "script:lesson-1"},
            ],
        }
        repository.apply_material_absorption_plan(package, plan)
        first_bundle = {
            "bundle_id": "bundle-plan",
            "plan_id": "plan-1",
            "course_id": "course-1",
            "targets": [{
                "target_id": "lesson-plan:lesson-1",
                "target_type": "lesson_plan",
                "title": "第一讲教案",
                "sources": [{"asset_id": first["asset_id"], "role": "primary", "action": "absorb"}],
            }],
        }
        receipt = repository.execute_material_absorption(package, first_bundle)
        duplicate = repository.execute_material_absorption(package, first_bundle)

        self.assertEqual(receipt, duplicate)
        self.assertEqual(package["material_absorption"]["status"], "partially_executed")
        self.assertEqual(
            package["material_absorption"]["execution"]["executed_target_ids"],
            ["lesson-plan:lesson-1"],
        )

        second_bundle = {
            "bundle_id": "bundle-script",
            "plan_id": "plan-1",
            "course_id": "course-1",
            "targets": [{
                "target_id": "script:lesson-1",
                "target_type": "script",
                "title": "第一讲讲稿",
                "sources": [{"asset_id": second["asset_id"], "role": "primary", "action": "absorb"}],
            }],
        }
        repository.execute_material_absorption(package, second_bundle)

        self.assertEqual(package["material_absorption"]["status"], "executed")
        self.assertEqual(len(package["material_absorption"]["execution"]["receipts"]), 2)
        self.assertEqual(package["preparation_status"], "completed")

    async def test_course_binding_uses_stable_id_and_preserves_legacy_packages(self):
        repository = TeacherCourseSpaceRepository(Path(tempfile.mkdtemp()))
        bound = repository.create_package(
            "teacher-a", "数据结构", "2025-2026", "春季", course_id="course-1"
        )
        legacy = repository.create_package("teacher-a", "数据结构", "2024-2025", "秋季")

        self.assertEqual(repository.list_owned("teacher-a", "course-1"), [bound])
        self.assertEqual(repository.load_owned(legacy["package_id"], "teacher-a").get("course_id"), "")
        with self.assertRaises(MaterialStorageError):
            repository.bind_course(
                repository.load_owned(legacy["package_id"], "teacher-a"), "course-1"
            )

        migrated = repository.bind_course(
            repository.load_owned(legacy["package_id"], "teacher-a"), "course-legacy"
        )
        self.assertEqual(migrated["package_id"], legacy["package_id"])
        self.assertEqual(migrated["course_id"], "course-legacy")

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

    async def test_assets_can_be_renamed_moved_and_batched_without_changing_source_bytes(self):
        root = Path(tempfile.mkdtemp())
        repository = TeacherCourseSpaceRepository(root)
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "春季")
        package = repository.load_owned(created["package_id"], "teacher-a")
        first = await repository.import_file(package, FakeUpload(), "辅助资料/其他资料/旧教案.pdf", "batch-1")
        second = await repository.import_file(package, FakeUpload(), "辅助资料/其他资料/课堂案例.pdf", "batch-1")
        repository.save(package)

        renamed = repository.relocate_asset(package, first["asset_id"], filename="第一讲教案.pdf")
        moved = repository.relocate_assets(package, [first["asset_id"], second["asset_id"]], "辅助资料/老师题库")

        self.assertEqual(renamed["filename"], "第一讲教案.pdf")
        self.assertEqual(
            {item["relative_path"] for item in moved},
            {"辅助资料/老师题库/第一讲教案.pdf", "辅助资料/老师题库/课堂案例.pdf"},
        )
        self.assertTrue((root / created["package_id"] / "content" / "辅助资料" / "老师题库" / "第一讲教案.pdf").is_file())
        self.assertTrue((root / created["package_id"] / "files" / first["stored_name"]).is_file())
        with self.assertRaisesRegex(MaterialStorageError, "不能改变文件类型"):
            repository.relocate_asset(package, first["asset_id"], filename="第一讲教案.docx")

    async def test_custom_folder_can_be_renamed_and_moved_with_nested_contents(self):
        root = Path(tempfile.mkdtemp())
        repository = TeacherCourseSpaceRepository(root)
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "春季")
        package = repository.load_owned(created["package_id"], "teacher-a")
        repository.import_folders(package, ["辅助资料/其他资料/第一讲/空目录"])
        asset = await repository.import_file(package, FakeUpload(), "辅助资料/其他资料/第一讲/教学日历.pdf", "batch-1")
        repository.save(package)

        repository.relocate_folder(package, "辅助资料/其他资料/第一讲", name="第一讲资料")

        moved_asset = next(item for item in package["assets"] if item["asset_id"] == asset["asset_id"])
        self.assertEqual(moved_asset["relative_path"], "辅助资料/其他资料/第一讲资料/教学日历.pdf")
        self.assertIn("辅助资料/其他资料/第一讲资料/空目录", package_folder_paths(package))
        self.assertTrue((root / created["package_id"] / "content" / "辅助资料" / "其他资料" / "第一讲资料" / "教学日历.pdf").is_file())
        with self.assertRaisesRegex(MaterialStorageError, "系统目录"):
            repository.relocate_folder(package, "辅助资料/其他资料", name="全部资料")

    async def test_recycle_bin_restores_assets_and_only_purge_removes_source(self):
        root = Path(tempfile.mkdtemp())
        repository = TeacherCourseSpaceRepository(root)
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "春季")
        package = repository.load_owned(created["package_id"], "teacher-a")
        asset = await repository.import_file(package, FakeUpload(), "辅助资料/其他资料/第一讲教案.pdf", "batch-1")
        repository.save(package)
        source = root / created["package_id"] / "files" / asset["stored_name"]
        materialized = root / created["package_id"] / "content" / "辅助资料" / "其他资料" / "第一讲教案.pdf"

        trashed = repository.trash_assets(package, [asset["asset_id"]])[0]

        self.assertTrue(source.is_file())
        self.assertFalse(materialized.exists())
        self.assertEqual(repository.public(package)["trash_count"], 1)
        self.assertEqual(repository.public(package)["assets"], [])

        repository.restore_trash(package, [trashed["trash_id"]])
        self.assertTrue(materialized.is_file())
        self.assertEqual([item["asset_id"] for item in package["assets"]], [asset["asset_id"]])

        trashed_again = repository.trash_assets(package, [asset["asset_id"]])[0]
        repository.purge_trash(package, [trashed_again["trash_id"]])
        self.assertFalse(source.exists())
        self.assertEqual(repository.public(package)["trash_count"], 0)

    async def test_recycle_bin_restores_custom_folder_as_one_item(self):
        root = Path(tempfile.mkdtemp())
        repository = TeacherCourseSpaceRepository(root)
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "春季")
        package = repository.load_owned(created["package_id"], "teacher-a")
        repository.import_folders(package, ["辅助资料/其他资料/第一讲/空目录"])
        asset = await repository.import_file(package, FakeUpload(), "辅助资料/其他资料/第一讲/教学日历.pdf", "batch-1")
        repository.save(package)

        trashed = repository.trash_folder(package, "辅助资料/其他资料/第一讲")
        self.assertEqual(repository.public(package)["trash"][0]["kind"], "folder")
        self.assertNotIn(asset["asset_id"], [item["asset_id"] for item in package["assets"]])

        repository.restore_trash(package, [trashed["trash_id"]])
        self.assertIn("辅助资料/其他资料/第一讲/空目录", package_folder_paths(package))
        self.assertTrue((root / created["package_id"] / "content" / "辅助资料" / "其他资料" / "第一讲" / "教学日历.pdf").is_file())

    async def test_formal_file_relationships_are_bidirectional_and_replaceable(self):
        repository = TeacherCourseSpaceRepository(Path(tempfile.mkdtemp()))
        created = repository.create_package(
            "teacher-a", "数据结构", "2025-2026", "春季", course_id="course-1"
        )
        package = repository.load_owned(created["package_id"], "teacher-a")
        primary = await repository.import_file(
            package, FakeUpload(), "原始资料/旧教案.pdf", "batch-1"
        )
        reference = await repository.import_file(
            package, FakeUpload(), "原始资料/课堂案例.pdf", "batch-1"
        )
        repository.save(package)

        links = repository.replace_formal_relationships(
            package,
            target_id="lesson-plan:lesson-1",
            target_type="lesson_plan",
            target_label="第 1 讲教案",
            sources=[
                {"source_asset_id": primary["asset_id"], "role": "primary"},
                {"source_asset_id": reference["asset_id"], "role": "reference"},
            ],
        )

        self.assertEqual(len(links), 2)
        self.assertEqual(
            repository.relationships_for_target(package, "lesson-plan:lesson-1"),
            links,
        )
        self.assertEqual(
            repository.relationships_for_source(package, primary["asset_id"])[0]["target_label"],
            "第 1 讲教案",
        )
        self.assertIn(
            "lesson-plan:lesson-1",
            repository.public(package)["configured_source_target_ids"],
        )

        replaced = repository.replace_formal_relationships(
            package,
            target_id="lesson-plan:lesson-1",
            target_type="lesson_plan",
            target_label="第 1 讲教案",
            sources=[{"source_asset_id": reference["asset_id"], "role": "primary"}],
        )

        self.assertEqual(len(replaced), 1)
        self.assertEqual(
            repository.relationships_for_source(package, primary["asset_id"]), []
        )

        repository.replace_formal_relationships(
            package,
            target_id="lesson-plan:lesson-1",
            target_type="lesson_plan",
            target_label="第 1 讲教案",
            sources=[],
        )
        public = repository.public(package)
        self.assertIn("lesson-plan:lesson-1", public["configured_source_target_ids"])
        self.assertEqual(repository.relationships_for_target(package, "lesson-plan:lesson-1"), [])

    async def test_formal_file_cannot_be_used_as_another_formal_files_source(self):
        repository = TeacherCourseSpaceRepository(Path(tempfile.mkdtemp()))
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "春季")
        package = repository.load_owned(created["package_id"], "teacher-a")

        with self.assertRaises(FileNotFoundError):
            repository.replace_formal_relationships(
                package,
                target_id="ppt:lesson-1",
                target_type="ppt",
                target_label="第 1 讲 PPT",
                sources=[{
                    "source_asset_id": "lesson-plan:lesson-1",
                    "role": "primary",
                }],
            )

    async def test_deleting_referenced_source_asset_is_blocked(self):
        repository = TeacherCourseSpaceRepository(Path(tempfile.mkdtemp()))
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "春季")
        package = repository.load_owned(created["package_id"], "teacher-a")
        source = await repository.import_file(
            package, FakeUpload(), "原始资料/旧教案.pdf", "batch-1"
        )
        repository.save(package)
        repository.replace_formal_relationships(
            package,
            target_id="managed:outline",
            target_type="outline",
            target_label="课程大纲",
            sources=[{"source_asset_id": source["asset_id"], "role": "primary"}],
        )

        with self.assertRaisesRegex(MaterialStorageError, "仍被正式文件引用"):
            repository.delete_asset(package, source["asset_id"])

        loaded = repository.load_owned(created["package_id"], "teacher-a")
        self.assertEqual(len(loaded["relationships"]), 1)
        self.assertEqual([item["asset_id"] for item in loaded["assets"]], [source["asset_id"]])

    async def test_deleting_folder_with_referenced_source_asset_is_blocked(self):
        repository = TeacherCourseSpaceRepository(Path(tempfile.mkdtemp()))
        created = repository.create_package("teacher-a", "数据结构", "2025-2026", "春季")
        package = repository.load_owned(created["package_id"], "teacher-a")
        source = await repository.import_file(
            package, FakeUpload(), "辅助资料/试卷/期末真题.pdf", "batch-1"
        )
        repository.save(package)
        repository.replace_formal_relationships(
            package,
            target_id="managed:question-bank",
            target_type="question_bank",
            target_label="课程题库",
            sources=[{"source_asset_id": source["asset_id"], "role": "question_source"}],
        )

        with self.assertRaisesRegex(MaterialStorageError, "文件夹中有原件仍被正式文件引用"):
            repository.delete_folder(package, "辅助资料/试卷")

        loaded = repository.load_owned(created["package_id"], "teacher-a")
        self.assertEqual(len(loaded["relationships"]), 1)
        self.assertEqual([item["asset_id"] for item in loaded["assets"]], [source["asset_id"]])

    async def test_question_sources_have_a_dedicated_question_bank_role(self):
        repository = TeacherCourseSpaceRepository(Path(tempfile.mkdtemp()))
        created = repository.create_package(
            "teacher-a", "数据结构", "2025-2026", "春季", course_id="course-1"
        )
        package = repository.load_owned(created["package_id"], "teacher-a")
        source = await repository.import_file(
            package, FakeUpload(), "实际考卷/2025年期末真题.pdf", "batch-1"
        )
        repository.save(package)

        links = repository.replace_formal_relationships(
            package,
            target_id="managed:question-bank",
            target_type="question_bank",
            target_label="课程题库",
            sources=[{
                "source_asset_id": source["asset_id"],
                "role": "question_source",
            }],
        )

        self.assertEqual(links[0]["role"], "question_source")
        with self.assertRaises(MaterialStorageError):
            repository.replace_formal_relationships(
                package,
                target_id="lesson-plan:lesson-1",
                target_type="lesson_plan",
                target_label="第 1 讲教案",
                sources=[{
                    "source_asset_id": source["asset_id"],
                    "role": "question_source",
                }],
            )
