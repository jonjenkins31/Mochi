# modules/

Project-local modules. **Anything here shadows an installed module
claiming the same slot.**

This is ROS's workspace overlay. `/opt/ros` holds hundreds of packages
a ROS developer never opens; `~/ws/src` holds the handful they are
actually working on, and `src` wins. Same rule here:

```
installed (site-packages)   the default — shared, versioned, out of sight
modules/<name>/             yours — visible, editable, and it WINS
```

## When to put something here

**Don't, by default.** An installed module is one copy, versioned, and
shared with every other project. Copying it in means you now own a
fork that will drift.

Put a module here when you need to change it *for this project* and
you want that change visible in the project rather than buried in a
venv or a second repo. Debugging an engine, trying a patch, or
carrying a project-specific tweak upstream hasn't taken yet.

## How

```bash
cp -a ../JaegerAnimation/jaeger_animation modules/animation
python3 main.py          # logs: slot 'animation': using LOCAL modules/animation
                         #       (shadows installed jaeger_animation)
```

Delete the folder to go back. No reinstall, no manifest edit — that
reversibility is what makes overriding cheap enough to actually do
instead of forking.

## The rule

Shadowing is per **slot**, not per name. The slot is what
`jaeger.toml` binds, so a local module called `piper_tts` takes the
`tts` slot from an installed `kokoro_tts`. You never have to guess a
vendor's package name to replace their engine.

It is never silent. Every shadow logs which directory won and what it
displaced — an override that takes effect without saying so is exactly
the hidden behaviour this feature exists to remove.

## What is here now

Nothing. Mochi runs entirely on installed modules, which is the
healthy default. `jaeger.toml` names the slots; `pyproject.toml` names
the packages that fill them.
