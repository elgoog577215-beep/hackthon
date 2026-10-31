"""Course persistence errors independent of repositories."""
class CourseDocumentNotFound(KeyError):
    pass


class CourseDocumentConflict(RuntimeError):
    pass


class CourseMigrationConflict(RuntimeError):
    pass
