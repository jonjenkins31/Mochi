# Base class every animation must implement
class Animation:
    name = "unnamed"  # public handle
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h

    def on_enter(self, **kwargs):  # called when activated
        pass

    def on_event(self, event: str, **kwargs):  # optional external nudges
        pass

    def frame(self, t: float) -> bytes:
        """Return raw RGB bytes (w*h*3) for time t."""
        raise NotImplementedError