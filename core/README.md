# core/

This app's own logic — what is neither an imported module nor a screen.

**Empty today, and that is honest.** Everything Mochi does is either
"how it uses an imported module" (`modules/`) or "what an operator looks at"
(`interfaces/`). Pack reading belongs in `modules/jaeger_animation.py`, beside everything else
about the face.

## What belongs here

Logic with no home in either of the others:

- turning a conversation into an expression choice (after an LLM module
  contract exists)
- a scheduler, a state machine, a persistence layer
- anything two different screens would both need

## What does not

- **How Mochi uses an imported module** → `modules/<provider_name>.py`.
- **Anything a user looks at** → `interfaces/`.
- **A node this project owns** → `nodes/`.

The test: could a second app want this code? If yes, it is a module,
not core. If it only makes sense for Mochi, it is core.
