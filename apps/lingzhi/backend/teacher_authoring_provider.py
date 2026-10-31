"""One provider for the existing authoring repository."""
_teacher_lesson_authoring_repository=None

def get_teacher_lesson_authoring_repository():
    """Return the teacher-only lesson asset repository lazily.

    Kept out of the student course repository so teacher drafts cannot become
    learner-visible merely by being saved.
    """
    global _teacher_lesson_authoring_repository
    if _teacher_lesson_authoring_repository is None:
        from teacher_lesson_authoring import TeacherLessonAuthoringRepository
        _teacher_lesson_authoring_repository = TeacherLessonAuthoringRepository()
    return _teacher_lesson_authoring_repository
