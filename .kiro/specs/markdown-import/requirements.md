# Requirements Document

## Introduction

This feature allows users to import a Markdown file and have it automatically parsed into the JSON node tree structure that the Knowledge Map AI frontend renders. Instead of generating a course outline via LLM, users can supply their own Markdown document and have it converted into the same hierarchical `Node` structure (Chapters → Sections → Subsections) used throughout the platform. The imported course is stored in `backend/data/courses/` and becomes immediately accessible in the frontend like any AI-generated course.

## Glossary

- **Markdown_Parser**: The backend component responsible for reading a Markdown file and converting it into a list of `Node` objects.
- **Node**: A single unit in the course tree with fields `node_id`, `parent_node_id`, `node_name`, `node_level`, `node_content`, `node_type`, `is_read`, `quiz_score`, and `create_time`.
- **Course_Tree**: The top-level JSON object stored per course, containing `course_id`, `course_name`, `keyword`, `nodes`, and metadata fields.
- **Heading_Level**: The ATX heading depth in Markdown (`#`, `##`, `###`, etc.), mapped to logical levels relative to the minimum heading level present in the document.
- **Minimum_Heading_Level**: The smallest ATX heading depth found in a given document (e.g., `##` = depth 2). The Markdown_Parser treats this as logical level 1.
- **Body_Content**: All Markdown text between two consecutive headings, assigned as `node_content` of the preceding heading's node.
- **Import_Endpoint**: The FastAPI route that accepts a Markdown file upload and returns a newly created course.
- **Import_UI**: The Vue 3 frontend component that lets users select and upload a Markdown file.
- **Pretty_Printer**: The component that serializes a `Course_Tree` back to a well-formed Markdown document.

---

## Requirements

### Requirement 1: Parse Markdown Headings into Node Hierarchy

**User Story:** As a learner, I want to upload a Markdown file and have its headings automatically mapped to course chapters and sections, so that I can navigate my own content using the platform's knowledge graph interface.

#### Acceptance Criteria

1. WHEN a Markdown file is uploaded, THE Markdown_Parser SHALL detect the Minimum_Heading_Level by scanning all ATX headings in the document and recording the smallest depth value present.
2. WHEN a Markdown file is uploaded, THE Markdown_Parser SHALL assign `node_level = 1` to every heading whose ATX depth equals the Minimum_Heading_Level, and `parent_node_id = "root"` to those nodes.
3. WHEN a Markdown file is uploaded, THE Markdown_Parser SHALL assign `node_level = (depth - Minimum_Heading_Level + 1)` to each heading, so that relative depth differences are preserved regardless of the absolute heading depths used in the source document.
4. WHEN a Markdown file is uploaded, THE Markdown_Parser SHALL set `parent_node_id` of each node to the `node_id` of the most recently encountered node whose `node_level` is exactly one less.
5. WHEN a Markdown file contains headings whose computed `node_level` exceeds 3, THE Markdown_Parser SHALL flatten those headings to `node_level = 3` and attach them to the nearest valid ancestor at `node_level = 2`.
6. THE Markdown_Parser SHALL assign each `Node` a unique UUID as `node_id`.
7. THE Markdown_Parser SHALL set `node_type = "original"` for all imported nodes.

### Requirement 2: Assign Body Content to Nodes

**User Story:** As a learner, I want the text content under each heading to be preserved as the node's content, so that I can read my original material within the platform's content viewer.

#### Acceptance Criteria

1. WHEN a Markdown file is parsed, THE Markdown_Parser SHALL assign all Markdown text between a heading and the next heading of equal or higher level as the `node_content` of that heading's node.
2. WHEN a Markdown file contains text before the first heading, THE Markdown_Parser SHALL create a root-level node named after the filename (without extension) with `node_level = 1` and assign that text as its `node_content`.
3. WHEN a node has no body content between its heading and the next heading, THE Markdown_Parser SHALL set `node_content` to an empty string `""`.
4. THE Markdown_Parser SHALL preserve the following inline formatting spans within `node_content` without modification: bold (`**text**`), italic (`*text*` and `_text_`), inline code (`` `code` ``), strikethrough (`~~text~~`), Obsidian-style highlights (`==text==`), and standard Markdown links (`[label](url)`).

### Requirement 3: Image Handling

**User Story:** As a learner, I want images from my Markdown file to appear in the imported course where supported, so that visual content is not silently lost.

#### Acceptance Criteria

1. WHEN a Markdown file contains an image with an external URL (e.g., `![alt](https://...)`), THE Markdown_Parser SHALL preserve the image syntax as-is within the `node_content` of the enclosing node.
2. WHEN a Markdown file contains an image with a local file path (e.g., `![alt](./images/photo.png)` or `![alt](images/photo.png)`), THE Markdown_Parser SHALL replace the image syntax with the placeholder text `[图片: {alt_text}]`, where `{alt_text}` is the original alt text, or `[图片]` if no alt text is present.
3. WHEN an image (external or local) is immediately followed on the next line by a plain-text caption, or by an HTML `<figcaption>` element, THE Markdown_Parser SHALL preserve that caption as plain text immediately after the image or placeholder in `node_content`.

### Requirement 4: Build and Persist the Course Tree

**User Story:** As a learner, I want my imported Markdown file to be saved as a course, so that I can access it later alongside my AI-generated courses.

#### Acceptance Criteria

1. WHEN parsing succeeds, THE Import_Endpoint SHALL construct a `Course_Tree` with a new UUID as `course_id`, `course_name` derived from the first heading at the Minimum_Heading_Level or the filename, and `keyword` set to the same value as `course_name`.
2. WHEN parsing succeeds, THE Import_Endpoint SHALL persist the `Course_Tree` to `backend/data/courses/{course_id}.json` using the existing `Storage.save_course` method.
3. WHEN parsing succeeds, THE Import_Endpoint SHALL return the `course_id` and `course_name` to the caller in the response body.
4. IF the uploaded file is empty, THEN THE Import_Endpoint SHALL return HTTP 400 with a descriptive error message.
5. IF the uploaded file exceeds 20 MB, THEN THE Import_Endpoint SHALL return HTTP 413 with a descriptive error message.

### Requirement 5: Validate Markdown Input

**User Story:** As a learner, I want clear error messages when my Markdown file cannot be parsed, so that I can fix the problem and retry.

#### Acceptance Criteria

1. IF the uploaded file is not valid UTF-8 text, THEN THE Import_Endpoint SHALL return HTTP 422 with the message "文件编码不支持，请使用 UTF-8 编码的 Markdown 文件".
2. IF the uploaded file contains no ATX headings (`#`), THEN THE Import_Endpoint SHALL return HTTP 422 with the message "未检测到 Markdown 标题，请确保文件包含至少一个 # 标题".
3. IF the uploaded file has a MIME type other than `text/markdown`, `text/plain`, or `application/octet-stream`, THEN THE Import_Endpoint SHALL return HTTP 415 with a descriptive error message.

### Requirement 6: Frontend Import UI

**User Story:** As a learner, I want a clearly visible import button in the course list area, so that I can upload a Markdown file without leaving the main interface.

#### Acceptance Criteria

1. THE Import_UI SHALL provide a file input that accepts `.md` and `.txt` files.
2. WHEN a user selects a file, THE Import_UI SHALL display the filename and file size before upload.
3. WHEN the user confirms the upload, THE Import_UI SHALL show a loading indicator while the request is in progress.
4. WHEN the Import_Endpoint returns success, THE Import_UI SHALL navigate to the newly created course without requiring a page reload.
5. WHEN the Import_Endpoint returns an error, THE Import_UI SHALL display the error message returned by the server using an Element Plus notification.
6. WHILE an upload is in progress, THE Import_UI SHALL disable the upload button to prevent duplicate submissions.

### Requirement 7: Round-Trip Fidelity (Parser ↔ Pretty Printer)

**User Story:** As a developer, I want the Markdown parser and pretty printer to be inverses of each other, so that exported content can be re-imported without data loss.

#### Acceptance Criteria

1. THE Pretty_Printer SHALL serialize a `Course_Tree` back into a Markdown document where each `node_level = 1` node becomes a `#` heading, `node_level = 2` becomes `##`, and `node_level = 3` becomes `###`.
2. THE Pretty_Printer SHALL place each node's `node_content` immediately after its heading, separated by a blank line.
3. FOR ALL valid Markdown documents that contain only ATX headings at levels 1–3, parsing then printing then parsing SHALL produce a `Course_Tree` with identical `node_name`, `node_content`, `node_level`, and `parent_node_id` values (round-trip property).
