# Diagrams

Interactive, self-contained HTML diagrams generated with [archify](https://github.com/tt-a1i/archify) (MIT).

| Artifact | Source | What it shows |
|---|---|---|
| [campaignforge-architecture.html](campaignforge-architecture.html) | [campaignforge.architecture.json](campaignforge.architecture.json) | Whole system — frontend, API, pipeline, LLM providers, Neon, Stripe, publishing |
| [campaignforge-pipeline.html](campaignforge-pipeline.html) | [campaignforge.workflow.json](campaignforge.workflow.json) | The LangGraph agent pipeline, its human review gate, and both revision loops |

Open either `.html` directly in a browser. No server, no build step, no network — everything is inlined. Each has dark/light themes, guided views, and PNG/SVG/WebM export.

## Regenerating

The skill is **not vendored into git** (~7.5MB of upstream examples and tests). It is pinned by hash in [`skills-lock.json`](../../skills-lock.json). Install it:

```bash
npx skills add tt-a1i/archify --skill archify --agent claude-code --copy --yes
```

Then, from `.claude/skills/archify/`:

```bash
# Architecture — --repo-root verifies every component's `sources` paths exist
node bin/archify.mjs deliver architecture \
  ../../../docs/diagrams/campaignforge.architecture.json \
  ../../../docs/diagrams/campaignforge-architecture.html \
  --quality showcase --repo-root ../../..

# Pipeline
node bin/archify.mjs deliver workflow \
  ../../../docs/diagrams/campaignforge.workflow.json \
  ../../../docs/diagrams/campaignforge-pipeline.html \
  --quality showcase
```

`deliver` refuses to write on a failed validation, so a non-zero exit means the previous HTML is still in place — never treat it as success.

Optional desktop-fit check (writes `*.visual-check.*` sidecars, which are gitignored):

```bash
node bin/archify.mjs visual-check ../../../docs/diagrams/campaignforge-architecture.html --json
```

## Editing

Edit the **JSON**, never the HTML — the HTML is compiled output and is overwritten on every deliver.

Both sources pass `--quality showcase`: 9/9 artifact checks, 0 composition errors, 0 warnings, and no viewport overflow at 1440×900, 1600×1000, 1920×1080, or 2048×1320.

## Two things to know before editing

**The architecture source pins a commit.** `meta.repository.revision` is a 40-char SHA, and every component's `sources` paths are checked against the working tree when `--repo-root` is passed. If you move a file the diagram references, the render fails rather than shipping a stale link. Update the revision when you refresh the diagram.

**Layout is solved, not authored.** Workflow v2 computes its own geometry from `lane` + `col`; the `viewBox` only sizes the canvas. Fix a geometry complaint by changing spacing, removing a low-value edge, or using a route preset — not by pinning coordinates. Authored `via` / `channelX` / `channelY` are hard pins in v2 and fail loudly when infeasible.

## Known simplifications

Recorded here because the diagrams are deliberately not exhaustive:

- **`seo → ad copy` is not drawn** in the pipeline diagram. Ad Copy really does consume SEO output, but that edge collided with the `revise_content` return corridor and no routing control resolved it. The fact is preserved in the "Model tiers and fan-in" card instead of being silently dropped.
- **Node sublabels were removed** from the pipeline diagram. At a 1400-wide viewBox they projected below the 6px readability floor on a 1440px desktop. The tier and temperature they carried moved into the same card.
- **Clerk has no brand badge.** Archify has no built-in mark for it, and the skill forbids inferring one, so it renders as a plain security node.
