"""
Unit tests for backend/markdown_parser.py

Run with:
    cd tests && python -m pytest test_markdown_import.py -v
"""

import sys
import os

# Add workspace root to sys.path so we can import from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from backend.markdown_parser import parse_markdown_to_nodes, pretty_print


# ---------------------------------------------------------------------------
# Test 1: Pre-heading text creates synthetic root node named after filename
# ---------------------------------------------------------------------------

class TestPreHeadingText:
    def test_synthetic_node_created_when_text_before_first_heading(self):
        text = "This is some intro text.\nMore intro.\n\n# Chapter One\n\nContent here."
        nodes, _ = parse_markdown_to_nodes(text, "my_doc")
        # First node should be the synthetic root
        assert nodes[0]['node_name'] == 'my_doc'

    def test_synthetic_node_has_level_1(self):
        text = "Intro text.\n\n# Chapter One"
        nodes, _ = parse_markdown_to_nodes(text, "my_doc")
        assert nodes[0]['node_level'] == 1

    def test_synthetic_node_has_parent_root(self):
        text = "Intro text.\n\n# Chapter One"
        nodes, _ = parse_markdown_to_nodes(text, "my_doc")
        assert nodes[0]['parent_node_id'] == 'root'

    def test_synthetic_node_content_is_pre_heading_text(self):
        text = "Intro text.\n\n# Chapter One"
        nodes, _ = parse_markdown_to_nodes(text, "my_doc")
        assert nodes[0]['node_content'] == 'Intro text.'

    def test_no_synthetic_node_when_no_pre_heading_text(self):
        text = "# Chapter One\n\nContent here."
        nodes, _ = parse_markdown_to_nodes(text, "my_doc")
        # First node should be the heading node, not a synthetic one
        assert nodes[0]['node_name'] == 'Chapter One'

    def test_synthetic_node_uses_filename_as_name(self):
        text = "Some preamble.\n\n## Section A"
        nodes, _ = parse_markdown_to_nodes(text, "lecture_notes")
        assert nodes[0]['node_name'] == 'lecture_notes'


# ---------------------------------------------------------------------------
# Test 2: Document with only ## headings maps all to node_level = 1
# ---------------------------------------------------------------------------

class TestOnlyDoubleHashHeadings:
    def test_all_double_hash_map_to_level_1(self):
        text = "## Alpha\n\n## Beta\n\n## Gamma"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        assert all(n['node_level'] == 1 for n in nodes)

    def test_double_hash_nodes_have_parent_root(self):
        text = "## Alpha\n\n## Beta"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        assert all(n['parent_node_id'] == 'root' for n in nodes)

    def test_double_hash_node_count(self):
        text = "## Alpha\n\n## Beta\n\n## Gamma"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        assert len(nodes) == 3

    def test_course_name_from_first_level1_heading(self):
        text = "## Alpha\n\n## Beta"
        _, course_name = parse_markdown_to_nodes(text, "doc")
        assert course_name == 'Alpha'


# ---------------------------------------------------------------------------
# Test 3: #### headings in a #-rooted doc flatten to node_level = 3
# ---------------------------------------------------------------------------

class TestDeepHeadingFlattening:
    def test_four_hash_in_single_hash_doc_maps_to_level_3(self):
        text = "# Root\n\n## Section\n\n### Subsection\n\n#### Deep\n\n##### Deeper"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        # #### → depth 4, min_depth 1 → level = 4, clamped to 3
        # ##### → depth 5, min_depth 1 → level = 5, clamped to 3
        deep_nodes = [n for n in nodes if n['node_name'] in ('Deep', 'Deeper')]
        assert all(n['node_level'] == 3 for n in deep_nodes)

    def test_level_mapping_with_single_hash_root(self):
        text = "# Root\n\n## Section\n\n#### Deep"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        level_map = {n['node_name']: n['node_level'] for n in nodes}
        assert level_map['Root'] == 1
        assert level_map['Section'] == 2
        assert level_map['Deep'] == 3  # clamped from 4

    def test_five_hash_also_flattens_to_level_3(self):
        text = "# Root\n\n##### Very Deep"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        very_deep = next(n for n in nodes if n['node_name'] == 'Very Deep')
        assert very_deep['node_level'] == 3

    def test_flattened_node_parent_is_level_2(self):
        text = "# Root\n\n## Section\n\n#### Deep"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        node_by_id = {n['node_id']: n for n in nodes}
        deep = next(n for n in nodes if n['node_name'] == 'Deep')
        parent = node_by_id[deep['parent_node_id']]
        assert parent['node_level'] == 2


# ---------------------------------------------------------------------------
# Test 4: Local image replaced; external URL preserved; empty alt → [图片]
# ---------------------------------------------------------------------------

class TestImageHandling:
    def test_local_image_replaced_with_placeholder(self):
        text = "# Doc\n\n![screenshot](./images/screenshot.png)"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        assert '[图片: screenshot]' in nodes[0]['node_content']
        assert './images/screenshot.png' not in nodes[0]['node_content']

    def test_external_image_preserved(self):
        text = "# Doc\n\n![logo](https://example.com/logo.png)"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        assert '![logo](https://example.com/logo.png)' in nodes[0]['node_content']

    def test_http_external_image_preserved(self):
        text = "# Doc\n\n![banner](http://example.com/banner.jpg)"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        assert '![banner](http://example.com/banner.jpg)' in nodes[0]['node_content']

    def test_empty_alt_local_image_becomes_placeholder_no_alt(self):
        text = "# Doc\n\n![](./photo.jpg)"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        assert '[图片]' in nodes[0]['node_content']
        assert '[图片: ]' not in nodes[0]['node_content']

    def test_empty_alt_external_image_preserved_as_is(self):
        text = "# Doc\n\n![](https://example.com/img.png)"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        assert '![](https://example.com/img.png)' in nodes[0]['node_content']

    def test_local_image_without_leading_dot_replaced(self):
        text = "# Doc\n\n![chart](images/chart.png)"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        assert '[图片: chart]' in nodes[0]['node_content']
        assert 'images/chart.png' not in nodes[0]['node_content']

    def test_multiple_images_mixed(self):
        text = "# Doc\n\n![local](./local.png) and ![remote](https://cdn.example.com/img.png)"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        content = nodes[0]['node_content']
        assert '[图片: local]' in content
        assert '![remote](https://cdn.example.com/img.png)' in content


# ---------------------------------------------------------------------------
# Test 5: Empty body between consecutive headings → node_content = ""
# ---------------------------------------------------------------------------

class TestEmptyBody:
    def test_empty_body_between_headings_is_empty_string(self):
        text = "# Chapter One\n\n# Chapter Two\n\nSome content."
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        chapter_one = next(n for n in nodes if n['node_name'] == 'Chapter One')
        assert chapter_one['node_content'] == ''

    def test_empty_body_with_only_whitespace_is_empty_string(self):
        text = "# Chapter One\n   \n   \n# Chapter Two"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        chapter_one = next(n for n in nodes if n['node_name'] == 'Chapter One')
        assert chapter_one['node_content'] == ''

    def test_non_empty_body_is_preserved(self):
        text = "# Chapter One\n\nThis is content.\n\n# Chapter Two"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        chapter_one = next(n for n in nodes if n['node_name'] == 'Chapter One')
        assert chapter_one['node_content'] == 'This is content.'

    def test_last_heading_with_no_body_is_empty_string(self):
        text = "# Chapter One\n\nContent.\n\n# Chapter Two"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        chapter_two = next(n for n in nodes if n['node_name'] == 'Chapter Two')
        assert chapter_two['node_content'] == ''

    def test_all_headings_no_body(self):
        text = "# A\n# B\n# C"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        assert all(n['node_content'] == '' for n in nodes)


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_raises_value_error_when_no_headings(self):
        text = "Just some plain text with no headings."
        with pytest.raises(ValueError):
            parse_markdown_to_nodes(text, "doc")

    def test_node_type_is_original(self):
        text = "# Chapter\n\nContent."
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        assert all(n['node_type'] == 'original' for n in nodes)

    def test_all_node_ids_are_unique(self):
        text = "# A\n\n## B\n\n### C\n\n# D"
        nodes, _ = parse_markdown_to_nodes(text, "doc")
        ids = [n['node_id'] for n in nodes]
        assert len(ids) == len(set(ids))
