# mochi-v4 archive (trimmed)

Only the old **ZMQ node transport** is kept here — `transport/` (`zmq_manager`,
`node_base`, `node_template`). Reference for **cross-machine** data transfer
(sending bus data from one computer to another) down the line.

**The working ZMQ bus is already live**, no need to resurrect this one:
- `mochi/transport/zmq_bus.py` — the ZMQ pub/sub Bus
- `mochi/app/bus/zmq.py` + `mochi/transport/broker.py` — broker / XPUB-XSUB

The app runs the **in-process** bus today (`mochi/nodes/runtime.py` → `InProcBus`);
flip to the ZMQ bus when streaming between computers/devices.

Everything else from mochi-v4 was mined into the live tree (characters, assets,
docs, the GUI windows, the animation engine) and removed — git history has it if
you ever need to look back.
