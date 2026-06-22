"""Physical-hardware nodes — Tier 3 in the JROS daemon-arch.

Nodes whose device is a piece of physical hardware: motors, lights,
cameras. Each owns its wire (serial / ZMQ / etc.) via a thin
adapter; the host-side node is the chassis-supervised Python
object.
"""
