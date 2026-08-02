## 1. Specification and regressions

- [x] 1.1 Define semantic integrity and rollout requirements
- [x] 1.2 Add failing backend tests for diagram coverage, explicit answer
      binding, LLM-generated answer directives, standalone transitions,
      definitions, complete titles, and recap clauses
- [x] 1.3 Add failing frontend tests for answer mapping, aligned editorial
      groups, and 2x2 recap layout

## 2. Semantic compiler

- [x] 2.1 Preserve all required hierarchy nodes with concise balanced labels
- [x] 2.2 Extend story directives with bounded LLM-generated practice answers
- [x] 2.3 Normalize source, generated, and shared-evidence feedback contracts
- [x] 2.4 Remove standalone micro-transition artifacts
- [x] 2.5 Normalize formal definitions and complete title claims
- [x] 2.6 Build recaps only from complete declarative claims
- [x] 2.7 Normalize provider variance without discarding valid chapter answers
- [x] 2.8 Reconcile fragment-level answers with compound visible prompts

## 3. Rendering and publication gates

- [x] 3.1 Render question-answer pairs by identity in web and PPTX adapters
- [x] 3.2 Align editorial groups and render chapter recaps as 2x2
- [x] 3.3 Add critical V5 and visual-integrity gates
- [x] 3.4 Bump compiler, contract, and visual-policy versions

## 4. Verification and release

- [x] 4.1 Run targeted backend and frontend suites
- [x] 4.2 Generate and inspect a representative thermodynamics deck/PPTX
- [x] 4.3 Run full affected quality, build, dependency-audit, and OpenSpec checks
- [ ] 4.4 Review diff, commit, push, merge to main, and verify production deploy
- [ ] 4.5 Force-rebuild course `d7689f20-94cf-4aaa-9049-d52ad46257c0`
      and verify the published variant
