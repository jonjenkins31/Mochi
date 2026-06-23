# mochi-v4 GUI imports (quarantine)

PySide6 windows lifted from `archive/mochi-v4/interfaces/` as-is:

| window      | class           | what it is                         |
|-------------|-----------------|------------------------------------|
| `companion` | `CompanionMain` | the 9-page v4 Studio (Home/Library/Packs/Learn/Editors/Diagnostics) |
| `player`    | `PlayerWindow`  | virtual-display media player (Qt)  |

`mochi_health_service.py` is a zmq health subscriber (not a window).

Launch:  `python -m mochi.interfaces.v4.launch <companion|player>`

**Status: imported, not rewired.** They still drive the old zmq control plane +
old transport, so most controls are inert until ported to the new bus. The
tkinter windows (llm_chat_gui, mochi_perf, mochi_gui, mochi_vdisplay*) were NOT
imported — old toolkit; PySide6 + Swift are the path forward.
