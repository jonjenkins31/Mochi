# docs/ — Mochi's GitHub Pages site

`index.html` is the ecosystem's shared page, cloned from
[Jaeger-Template](https://github.com/JenkinsRobotics/Jaeger-Template)
with every `{{PLACEHOLDER}}` filled for Mochi. Same CSS design system
as every other Jaeger repo — the point of cloning it is that each page
looks like a family member rather than a one-off.

Everything is inline (all CSS and JS) or a stable external link the
JROS site already uses. Nothing to bundle, no build step.

## Deploying

Two methods exist in this ecosystem and Mochi uses the branch one:

- **`gh-pages` branch** — what JaegerOS and Jaeger-Template use, and
  what Mochi now has. `SITE.md` + `index.html` at the branch root.
- **`/docs` folder on the default branch** — simpler, ships the site
  atomically with the code, and what module repos standardize on.

GitHub → Settings → Pages → Source: **Deploy from a branch** →
Branch: `gh-pages`, Folder: `/` → Save. Live in ~1 minute at
`https://jenkinsrobotics.github.io/Mochi/`.

## Keeping the branch in sync

The branch is a mirror of this directory, not a separate source:

```bash
git checkout gh-pages
git checkout mochi-v5 -- docs/
mv docs/* . && rmdir docs
git commit -am "site: sync from mochi-v5"
git checkout mochi-v5
```

Edit `docs/index.html` here, never on `gh-pages` — two copies drifting
is exactly the failure the repo's own conventions warn about.

## What it claims

Every claim on the page is verifiable in this repo, deliberately:

| Claim | Where |
|---|---|
| plays a character pack | `assets/characters/emotes/` |
| 25 of 26 procedural scenes render | `archive/mochi-3.0/assets/math/` |
| modules/ shadows installed | `modules/README.md` |
| v5.1 needs no code change | the disabled nodes in `jaeger.toml` |

If a claim stops being true, the page is wrong and needs editing —
same rule as `(planned)` labelling everywhere else.
