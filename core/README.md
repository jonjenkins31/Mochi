# core/

This app's own logic — what is neither a module binding nor a screen.

**Empty today, and that is honest.** Everything Mochi does is either
"how it uses a module" (`modules/`) or "what an operator looks at"
(`interfaces/`). Pack reading lived here until the binding layer
existed; it belongs in `modules/animation.py`, next to everything else
about the face.

## What belongs here

Logic with no home in either of the others:

- turning a conversation into an expression choice (v5.2, when there
  is a mind to have conversations)
- a scheduler, a state machine, a persistence layer
- anything two different screens would both need

## What does not

- **How to use a module** → `modules/<name>.py`. If it imports a
  module or publishes that module's topics, it is a binding.
- **Anything a user looks at** → `interfaces/`.
- **A node this project owns** → `nodes/`.

The test: could a second app want this code? If yes, it is a module,
not core. If it only makes sense for Mochi, it is core.
