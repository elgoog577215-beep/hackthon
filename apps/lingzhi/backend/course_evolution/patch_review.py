"""Whole-body checks for fragment patches; never discard teacher-authored prose."""
import re
from collections import Counter
from collections.abc import Iterator

PATCH_REVIEW_CONTRACT = 'course_content_patch_v2'


class PatchValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def patch_error_detail(error: ValueError) -> dict:
    return {'code': getattr(error, 'code', 'patch_conflict'), 'retryable': False,
            'resolution': 'edit_current_body', 'contract_version': PATCH_REVIEW_CONTRACT}


def markdown_regions(text: str) -> Iterator[tuple[int, int, bool, str]]:
    """Yield line offsets outside/inside fenced code (including tilde fences)."""
    fence = ''
    offset = 0
    for line in text.splitlines(keepends=True):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        inside = bool(fence)
        if marker:
            value = marker[1]
            if not fence:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence) and not line[marker.end():].strip():
                fence = ''
        yield offset, offset + len(line), inside or bool(marker), line
        offset += len(line)


def section_inventory(text: str) -> Counter:
    headings = []
    for _, _, code, line in markdown_regions(text):
        if code:
            continue
        value = line.strip()
        heading = re.match(r'^#{1,6}\s+(.+?)\s*#*$', value)
        label = re.fullmatch(r'\*\*(.+?)\*\*\s*[:：]?', value)
        if not heading and not label:
            continue
        title = (heading or label)[1].strip().rstrip(':：').strip()
        # Different project names within the same source block still need a
        # whole-body review, but this is a suggestion, never an automatic delete.
        if re.match(r'^实践项目\s*[:：]', title):
            title = '实践项目'
        headings.append(title)
    return Counter(headings)


def duplicate_section_warning(before: str, after: str) -> str:
    original, proposed = section_inventory(before), section_inventory(after)
    duplicates = [title for title, count in proposed.items() if count > max(1, original[title])]
    return ('新增内容与原文或其他建议重复设置了“' + '、'.join(duplicates) + '”，请合并同一要求并保留不同的验收条件。') if duplicates else ''


def check_code_splice(original: str, begin: int, end: int, before: str, after: str) -> None:
    # Replacing an entire code example remains allowed. Expanding an anchor
    # *inside* a fence into a new prose section corrupts the surrounding code.
    inside = any(start <= begin < stop and code for start, stop, code, _ in markdown_regions(original))
    starts_at_fence = re.match(r'^ {0,3}(`{3,}|~{3,})', original[begin:])
    if inside and not starts_at_fence and section_inventory(after) and not section_inventory(before):
        raise PatchValidationError('patch_code_boundary', '修改把正文段落插入了代码示例内部，请在本条详情中调整插入位置。')
