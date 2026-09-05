from common.config import settings
from common.utils import format_datetime
from infra.db import Resource
from service.course import course_to_detail, unit_to_detail
from service.resource.models import ResourceSummary, ResourceDetail


def resource_to_summary(resource: Resource | None, child_count: int = 0) -> ResourceSummary | None:
    if not resource:
        return None
    return ResourceSummary(
        id=resource.id,
        name=resource.name,
        resource_type=resource.resource_type,
        word_count=resource.word_count or 0,
        editable=resource.editable,
        version_number=resource.version_number or 1,
        parent_resource_id=resource.parent_resource_id,
        child_count=child_count,
        related_course=course_to_detail(resource.related_course),
        related_unit=unit_to_detail(resource.related_unit),
        create_time=format_datetime(resource.create_time),
        update_time=format_datetime(resource.update_time),
    )

def resource_to_detail(resource: Resource | None) -> ResourceDetail | None:
    if not resource:
        return None
    return ResourceDetail(
        id=resource.id,
        name=resource.name,
        path=resource.path.replace(settings.UPLOAD_DIR, "/static") if resource.path else None,
        resource_type=resource.resource_type,
        content=resource.content,
        word_count=resource.word_count or 0,
        ppt_html_url=resource.ppt_html_url,
        ppt_pptx_url=resource.ppt_pptx_url,
        editable=resource.editable,
        version_number=resource.version_number or 1,
        parent_resource_id=resource.parent_resource_id,
        parent_resource_name=resource.parent_resource.name if resource.parent_resource else None,
        related_course=course_to_detail(resource.related_course),
        related_unit=unit_to_detail(resource.related_unit),
        create_time=format_datetime(resource.create_time),
        update_time=format_datetime(resource.update_time),
    )
