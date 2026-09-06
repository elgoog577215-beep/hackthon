## 1. Backend

- [x] 1.1 Add content block helpers for fallback parsing and Markdown rendering.
- [x] 1.2 Store generated node content as `content_blocks` plus compatible `node_content`.
- [x] 1.3 Add block regeneration endpoint that updates one block and rebuilds `node_content`.
- [x] 1.4 Keep old node update and redefine endpoints compatible.

## 2. Frontend

- [x] 2.1 Add `ContentBlock` type.
- [x] 2.2 Render content blocks with collapse state and a local regenerate action.
- [x] 2.3 Keep old Markdown rendering path for legacy nodes.

## 3. Validation

- [x] 3.1 Add focused tests for block fallback/rendering and block regeneration.
- [x] 3.2 Run targeted backend tests and OpenSpec validation.
