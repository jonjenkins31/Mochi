# modules/

The imported Jaeger modules Mochi uses are named explicitly here:

```text
modules/
  jaeger_animation.py
  jaeger_kokoro_tts.py
  jaeger_whisper_stt.py
```

The filename tells an operator which package is being integrated. Each file
contains Mochi's commands and observations for that imported module; it does
not hide the provider behind a generic `animation.py`, `tts.py`, or `stt.py`.

JaegerOS discovers engines for stable slots (`animation`, `tts`, and `stt`)
declared in `jaeger.toml`. The Interface's Modules tab shows the exact imported
provider that won discovery, including import package, module version, factory,
source path, and runtime state.

JaegerAI is not listed because it is not currently packaged as this kind of
Mochi module. The Chat tab remains disabled scaffolding until that contract is
implemented.

## Local module overrides

A complete local implementation can also be placed in a provider-named child
directory carrying `module.yaml`:

```text
modules/
  jaeger_animation.py       Mochi's imported-module integration
  jaeger_animation/         optional local implementation override
    module.yaml
    ...
```

JaegerOS discovery scans directories, not these `.py` integration files. A
local directory shadows an installed provider for the same slot. Delete the
directory to return to the installed package.
