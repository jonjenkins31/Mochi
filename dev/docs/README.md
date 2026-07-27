# dev/docs/ — internal

Working notes for someone CHANGING Mochi. Reviews, plans, and the
record of why things are the way they are.

Matches the ecosystem: JaegerOS, Jaeger-Template and JaegerAnimation
all keep internal docs under `dev/docs/` and reserve root `docs/` for
the published site.

## What is here

- **`20260726_mochi_3.0_review.md`** — the review of the 3.0 player
  that v5 is descended from. Still the reference for what "3.0 parity"
  means.
- **`studio/`** — Mochi Studio and AI Studio notes (was `docs/dev/`,
  which nested a dev folder inside the public one).
- **`v4-era/`** — plans and reviews written for v4. Kept for their
  reasoning, **not accurate for v5**: v4 is archived under
  `archive/mochi-v4/` and v5 shares none of its code.

## The rule

Anything here describing behaviour that does not exist is labelled
`(planned)`. A doc describing a phantom feature costs someone a
debugging session before they find out it was fiction.
