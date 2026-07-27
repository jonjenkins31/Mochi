# docs/ — outward-facing

What someone USING Mochi or authoring content for it needs. This is
the material a published site is built from (`index.html` + `SITE.md`
in the sibling repos, on `gh-pages`).

Working notes, reviews and plans do **not** belong here — they live in
`dev/docs/`. The split is by audience, not by topic:

| | |
|---|---|
| `docs/` | someone using Mochi or making a character |
| `dev/docs/` | someone changing Mochi |

## What is here

- **`learn/`** — how to author each kind of content: sprites,
  mscripts, gifs, video, bitmaps, math scenes. Written against the
  engine's adapters, so it still applies on v5 — the adapters carried
  forward from 3.0 unchanged.
- **`PACK_CONVENTION.md`**, **`SKIN_CONVENTION.md`**,
  **`ASSET_PROPERTIES.md`** — the pack format. This is the contract
  Anima Studio exports against and JaegerAnimation consumes, so it is
  shared vocabulary rather than Mochi's private business.

## Health warning

These predate v5 and have not been re-verified against it. The pack
format in particular is being standardized jointly with Anima Studio
and JaegerAnimation's `character/v1` schema — where they disagree, the
schema in `assets/characters/emotes/character.yaml` is what the code
actually reads.
