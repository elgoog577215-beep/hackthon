## Context

The current pipeline has enough structured information to build trustworthy diagrams, but loses it at two boundaries. First, fenced Markdown language is discarded, turning Mermaid into ordinary code. Second, the visual plan is created after page allocation, so the allocator cannot keep the prose, formula, and visual intent that form one teaching unit on the same page.

The change must work without a raster image model and across unrelated courses. It must also make “no visual” a first-class successful result.

## Goals / Non-Goals

**Goals:**

- Preserve source semantics from parsing through rendering.
- Let a language model choose only from typed, bounded diagram programs.
- Render the same rule-diagram program in web preview and editable PPT primitives.
- Prefer no visual over an unsupported, misleading, empty, or low-confidence visual.
- Prevent raw Mermaid, orphan formulas, and fake visual placeholders from reaching publishable output.
- Keep the core course-agnostic and add subject behavior through declarative template packs.

**Non-Goals:**

- Generate photorealistic, artistic, anatomical, geographic, or historically reconstructed images.
- Execute arbitrary Mermaid, SVG, HTML, or model-generated drawing code in the PPT production path.
- Guarantee that every source passage receives a diagram.
- Replace the existing Markdown Mermaid renderer used for ordinary document reading.

## Target AI Chain

```text
source blocks
  -> typed fragments
  -> semantic teaching groups
  -> per-group visual intent
  -> rule-diagram contract validation
  -> capacity-aware page allocation
  -> deterministic web/PPT rendering
  -> publish integrity gate
```

The language model is responsible for classification and constrained extraction:

- `visual_decision`: `rule_diagram | source_image | chart | formula | none`
- `template`: an allow-listed template identifier
- `source_fragment_ids`: evidence provenance
- node and edge labels copied or conservatively compressed from those fragments
- `confidence` and a short rejection reason when it selects `none`

The language model is not responsible for coordinates, font sizes, colors, SVG, Mermaid code, or arbitrary drawing instructions.

## Decisions

### Decision: Compile Mermaid into a typed rule diagram

Mermaid fences are classified as `diagram` fragments. A deterministic parser accepts a bounded subset of graph/flowchart syntax and emits the same typed rule-diagram contract used by model-selected diagrams. Unsupported syntax returns no diagram.

The production slide renderer never displays Mermaid source and never executes Mermaid in the PPT path.

### Decision: Use a generic core with declarative template packs

The generic core supports:

- `relation_graph`
- `process_flow`
- `cycle`
- `system_boundary`
- `apparatus`
- `energy_balance`
- `qualitative_plot`

Template packs may define vocabulary hints and eligibility rules for a subject, but cannot bypass source binding, capacity limits, or publish gates. Unknown courses therefore receive safe generic behavior rather than a course-specific failure.

### Decision: Keep rule diagrams source-bound and bounded

Every visible node and edge label must be attributable to declared source fragments. Initial limits are eight nodes, twelve edges, and short labels suitable for classroom projection. Unsupported or oversized programs fail closed to `none`.

No renderer may synthesize a placeholder panel when a diagram program is rejected.

### Decision: Make `none` a successful visual outcome

Visual selection follows this order:

1. verified source image,
2. validated rule diagram/chart/formula that materially improves teaching,
3. text-only layout.

Raster illustration generation is disabled by default and requires an explicit deployment flag plus a configured provider. Provider absence, timeout, rejection, or quality failure resolves to text-only content without retry loops or fake image frames.

### Decision: Paginate semantic groups, not isolated atoms

The allocator treats these as keep-together relationships whenever capacity permits:

- heading with its first explanatory block,
- explanation with an immediately following formula,
- formula with the next interpretation or consequence,
- diagram with its caption or teaching takeaway.

If a group exceeds page capacity, it is split at semantic boundaries and each child page receives a locally derived title. A formula cannot be emitted as a contextless continuation when adjacent source explanation exists.

### Decision: Render one contract through two deterministic adapters

The web adapter emits accessible SVG with visible labels and keyboard-readable text. The PPT adapter uses native shapes and connectors so the result remains editable. Both adapters consume the same validated rule-diagram contract and apply the same node/edge limits.

Raster assets are not created for rule diagrams.

### Decision: Block publication on visual integrity failures

The deck is not publishable when any slide contains:

- visible Mermaid source such as `graph TD`, `flowchart`, or `sequenceDiagram`,
- an invalid or unbound rule diagram,
- a visual placeholder or empty visual frame,
- a formula-only page while adjacent explanatory source was allocated elsewhere,
- a required raster visual whose asset is unresolved.

Warnings may still be used for optional visual opportunities, but these integrity failures are critical.

## Rollout

1. Preserve Mermaid type and compile the supported subset into rule diagrams.
2. Render rule diagrams in existing relational-diagram adapters.
3. remove formula/code pagination assumptions that force singleton pages and derive titles per local beat.
4. enforce default-off raster generation and publish blockers.
5. move visual intent before final allocation once the compatibility path is stable.
6. add domain packs only after the generic evaluation set passes.

## Evaluation

The regression set must include:

- source prose followed by Mermaid,
- prose → formula → interpretation,
- a long section that spans multiple pages,
- malformed or unsupported Mermaid,
- configured image provider with raster generation disabled,
- representative material from at least one quantitative and one non-quantitative course.

Pass criteria:

- zero raw Mermaid source in publishable slides,
- zero empty visual placeholders,
- zero contextless formula pages when adjacent explanation exists,
- every rendered rule-diagram label is source-bound,
- unsupported visuals deterministically become text-only,
- web and PPT renderers accept the same contract.

## Risks / Trade-offs

- The supported Mermaid subset is intentionally smaller than Mermaid itself. This is acceptable because unsupported diagrams degrade to prose instead of arbitrary execution.
- Text-only fallback reduces visual density, but preserves teaching correctness and avoids misleading output.
- Semantic grouping may produce fewer slides. This is a desired consequence when previous pages existed only because of artificial fragment boundaries.
- Domain packs can drift into hidden course-specific logic. They must remain declarative and pass the same generic validation suite.
