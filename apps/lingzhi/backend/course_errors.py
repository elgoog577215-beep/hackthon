"""Shared course persistence error contracts, independent of repositories."""

class CourseDocumentNotFound(KeyError):
    pass

class CourseDocumentConflict(RuntimeError):
    pass

class CourseMigrationConflict(RuntimeError):
    pass
