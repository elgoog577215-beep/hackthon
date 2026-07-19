# EVAL: universal-question-generation

## Capability evals

- Ten archetypes are available through a typed registry.
- Math, science, programming, humanities, language and business objectives
  route without topic-specific adapters.
- Every generated public specification has a separately versioned solution.
- Independent-solution disagreement forces teacher review.
- Title-only objectives remain candidates and never auto-publish.
- Student payloads cannot expose private solution or validator fields.

## Regression evals

- Existing deterministic graph, hashing, calculus, thermodynamics, Java and
  C++ adapters remain valid.
- Existing question-bank revisions and practice attempts remain readable.
- Search/model failures keep the current active bundle unchanged.
- Partial publication contains only approved, quality-passed tasks.

## Release metrics

- Capability eval pass@3 >= 0.90.
- Release-critical regression pass^3 = 1.00.
- Deterministic answer verification = 100%.
- Student answer/hidden-test leakage = 0.
- Unsafe auto-publication = 0.
