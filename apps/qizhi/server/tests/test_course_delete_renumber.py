"""
课程删除前资源重编号测试。

使用示例：
    cd server && python tests/test_course_delete_renumber.py

验证场景：
- 无课程作用域已有 outline v1；
- 待删除课程下已有 outline v1 / v2 两个根资源；
- 删除前重编号必须同时避开无课程作用域和当前课程作用域，不能把 v1 改成 v2 撞当前课程内的 v2。
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

BASE_DIR = Path(__file__).resolve().parent.parent


class _Query:
    def where(self, *_args, **_kwargs):
        return self

    def options(self, *_args, **_kwargs):
        return self


class _Column:
    def __eq__(self, _other):
        return object()

    def is_(self, _other):
        return object()

    def contains(self, _other):
        return object()


class _Func:
    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: object()


class _Resource:
    creator_id = _Column()
    related_course_id = _Column()
    resource_type = _Column()
    parent_resource_id = _Column()
    version_number = _Column()


class _Course:
    id = _Column()
    name = _Column()
    managers = SimpleNamespace(any=lambda *_args, **_kwargs: object())


class _User:
    id = _Column()


class _Logger:
    def error(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass

    def info(self, *_args, **_kwargs):
        pass


class _DummyModel:
    pass


def _install_stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _load_course_service_class():
    _install_stub(
        "sqlalchemy",
        func=_Func(),
        or_=lambda *_args, **_kwargs: object(),
        select=lambda *_args, **_kwargs: _Query(),
    )
    _install_stub("sqlalchemy.ext")
    _install_stub("sqlalchemy.ext.asyncio", AsyncSession=object)
    _install_stub("sqlalchemy.orm", selectinload=lambda *_args, **_kwargs: _Query())

    _install_stub("common")
    _install_stub("common.models", SystemException=Exception)
    _install_stub("common.utils")
    _install_stub("common.utils.logger", get_logger=lambda _name: _Logger())

    _install_stub("infra")
    _install_stub("infra.db", Course=_Course, Resource=_Resource, User=_User)

    _install_stub("service")
    _install_stub("service.course")
    _install_stub("service.course.converters", course_to_detail=lambda course: course)
    _install_stub(
        "service.course.models",
        CourseCreateParams=_DummyModel,
        CourseDeleteParams=_DummyModel,
        CourseDetail=_DummyModel,
        CourseUpdateParams=_DummyModel,
    )

    module_path = BASE_DIR / "service" / "course" / "service.py"
    spec = importlib.util.spec_from_file_location("course_service_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.CourseService


CourseService = _load_course_service_class()


class _ScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeExecuteResult:
    def __init__(self, rows=None, scalar_value=None):
        self._rows = rows
        self._scalar_value = scalar_value

    def scalars(self):
        return _ScalarsResult(self._rows)

    def scalar(self):
        return self._scalar_value


class _FakeSession:
    def __init__(self, detaching_rows, unscoped_max):
        self._detaching_rows = detaching_rows
        self._unscoped_max = unscoped_max
        self.calls = 0

    async def execute(self, _statement):
        self.calls += 1
        if self.calls == 1:
            return _FakeExecuteResult(rows=self._detaching_rows)
        return _FakeExecuteResult(scalar_value=self._unscoped_max)


async def test_renumber_detaching_resources_avoids_current_course_versions():
    resources = [
        SimpleNamespace(creator_id="teacher-1", resource_type="outline", version_number=1),
        SimpleNamespace(creator_id="teacher-1", resource_type="outline", version_number=2),
    ]
    service = CourseService(_FakeSession(resources, unscoped_max=1))

    await service._renumber_detaching_resources("course-1")

    versions = [resource.version_number for resource in resources]
    assert versions == [3, 4], f"应避开无课程 v1 与当前课程 v1/v2，实际版本: {versions}"


async def main():
    await test_renumber_detaching_resources_avoids_current_course_versions()
    print("课程删除前资源重编号测试通过")


if __name__ == "__main__":
    asyncio.run(main())
