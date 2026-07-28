# modules/

**One file per module this app uses.** The connection between a
library module and this app.

```
modules/
  common.py       helpers every binding needs
  animation.py    the face   — slot: animation
  tts.py          the voice  — slot: tts
  stt.py          the ears   — slot: stt
```

A binding holds everything about that module that is **Mochi's
business**: which slot it fills, its settings, where its content
lives, and what this app's actions mean as bus messages. The module
stays generic; this is where "how we use it" is written down, in one
obvious place per capability.

This is the same shape as Quantum Codex's `devices/` and ROS's
`*_bringup` packages — layers whose only job is composing and
configuring other people's code.

## Overriding

**Write it in the binding.** That is the whole mechanism. Wrap a call
to add your own defaults, point the content search somewhere else,
ignore a helper you do not want — the binding is your code, so
changing how a module behaves for this app means editing this file.

If you need to change the module's OWN code, put a copy in a
directory here with its `module.yaml`:

```
modules/animation.py     the binding      ← always
modules/animation/       a full copy      ← rare; SHADOWS the installed one
```

Discovery only scans directories for `module.yaml`, so the `.py` file
beside it is invisible to it. One folder, both jobs, no third
concept — and the override logs which copy won.

Delete the directory to go back to the installed module. That
reversibility is what makes overriding cheap enough to do instead of
forking.

## When to override the whole module

Rarely. An installed module is one copy, versioned, shared with every
other project; a directory copy is a fork that will drift. Do it to
debug something, or to carry a patch that has not landed upstream yet
— not as a default.
