# nodes/

Node code **this project owns**.

Empty, and that is correct for Mochi: every node it currently runs comes from
JaegerOS or an installed module bound in `jaeger.toml`. Run
`python3 main.py --nodes` to see what is actually running and where it
came from.

JP01-CC01's `nodes/` is not empty — it holds `motor.py`,
`videorx_node.py`, `jetson_link.py`, because that project talks to
specific hardware nobody else has. Those are its code; nothing can
install them.

## When something belongs here

A node that only makes sense for THIS project. If two projects would
want it, it belongs in a module instead — that is the whole difference
between the two directories.

Add `__init__.py` alongside your node so `jaeger.toml` can reach it:

```toml
[[node]]
id = "my_node"
factory = "nodes:make_my_node"     # local code: bound by FACTORY
```

versus a capability anyone could fill:

```toml
[[node]]
id = "animation"
slot = "animation"                 # a module: bound by SLOT
```
