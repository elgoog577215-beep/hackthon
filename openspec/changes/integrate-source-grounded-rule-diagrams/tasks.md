## 1. Preserve semantics and add the rule-diagram contract

- [x] 1.1 Preserve fenced-block language and classify Mermaid as a diagram fragment
- [x] 1.2 Add a bounded source-grounded rule-diagram program and deterministic Mermaid subset parser
- [x] 1.3 Compile supported Mermaid fragments into rule-diagram visual anchors
- [x] 1.4 Reject unsupported or unbound diagram programs to `none`

## 2. Improve semantic pagination and local storytelling

- [x] 2.1 Keep authoring-only visual marker headings out of slide content
- [x] 2.2 Keep formulas with adjacent explanation whenever capacity permits
- [x] 2.3 Derive continuation-page claims from local beat fragments instead of the whole chapter episode
- [x] 2.4 Preserve source order while applying keep-together groups

## 3. Render safely and consistently

- [x] 3.1 Render rule diagrams through the frontend native SVG adapter
- [x] 3.2 Render rule diagrams through editable native PPT shapes and connectors
- [x] 3.3 Ensure rejected diagrams produce text-only layouts with no placeholder frame
- [x] 3.4 Keep raster illustration generation disabled unless explicitly enabled

## 4. Add release gates and regressions

- [x] 4.1 Block visible raw Mermaid in publishable slide content
- [x] 4.2 Block invalid/unbound rule diagrams and unresolved required assets
- [x] 4.3 Block contextless formula pages when adjacent explanatory source exists
- [x] 4.4 Add backend and frontend regression tests for supported, unsupported, and fallback paths
- [x] 4.5 Run targeted and complete backend/frontend regression suites

### Verification record

- Affected backend suites: 65 passed.
- Frontend suite: 80 files and 575 tests passed.
- Frontend production build and OpenSpec strict validation passed.
- Full backend suite: 1078 passed; six unrelated environment/fixture failures remain in Windows deployment-script decoding/WSL availability and pre-existing learner-evidence encoding/recency tests.
- Real-course audit for `d7689f20-94cf-4aaa-9049-d52ad46257c0`: zero raw Mermaid slides, zero visual authoring markers, zero formula-only pages, zero generated illustrations with the default flag, six validated native rule diagrams, and no critical visual-integrity issues.
