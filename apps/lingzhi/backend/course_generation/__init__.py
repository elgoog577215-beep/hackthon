"""Course planning and generation compiler package.

The package owns generation semantics and artifacts; task lifecycle remains in
the jobs layer and formal publication remains in the course repository.
"""

from .workflow import PIPELINE_VERSION, build_course_generation_artifacts

__all__ = ["PIPELINE_VERSION", "build_course_generation_artifacts"]
