"""The face follows the FUNCTION — what the agent is doing, shown.

Every character so far has a vocabulary of looks: happy, sad, neutral.
Those describe a picture. `Orbs` has a vocabulary of VERBS — working,
searching, listening — and that difference is what this module exists
to use: when a pack can show what the mind is doing, it should, without
anyone driving it by hand.

    /sense/agent_state  thinking ──▶ working
    /act/speaker/state  playing  ──▶ composing
    /sense/stt/transcript        ──▶ listening
    (nothing happening)          ──▶ the pack's default — its idle

MOOD IS COLOUR, not shape. A verb says what it is doing; a colour says
how it is going. Splitting them means the orb can be `working` and
`worried` at once, which one vocabulary could not express without nine
more words. A pack opts in by declaring a `moods:` block:

    moods:
      calm:    "#8A85A6"
      curious: "#43E08A"

and the model reaches them the way it reaches expressions — a leading
`[curious]` on a reply, parsed by core/expressive.py. A pack that
declares none never changes colour and nothing here does anything.

WHY IT IS SAFE ON EVERY OTHER PACK. Nothing is played unless the pack
declares that exact word. Bitmap Man has no `working` expression, so
Bitmap Man is left alone — this is a capability packs opt into by
having the vocabulary, not a behaviour imposed on all of them.
"""

from __future__ import annotations

import pathlib
from typing import Any

import yaml

from modules import jaeger_agent as mind
from modules import jaeger_kokoro_tts as tts
from modules import jaeger_whisper_stt as stt

#: What the agent is doing -> the word a pack would use for it. Order
#: matters: the first of these that is TRUE wins, so speaking beats
#: thinking and both beat the resting state.
FUNCTION = (
    ("speaking", "composing"),
    ("hearing", "listening"),
    ("thinking", "working"),
    ("failed", "solving"),
)

#: The fallback mood colours, for when the agent's state is the only
#: thing we know about how it is going. A pack's own `moods:` block
#: overrides any of these by name.
MOOD = {
    "calm": "#8A85A6",
    "busy": "#6C5CE7",
    "listening": "#43E08A",
    "trouble": "#E06C75",
}

#: Which mood each state implies when the model has not named one.
MOOD_FOR = {"thinking": "busy", "hearing": "listening",
            "failed": "trouble", "": "calm"}


def moods(root: Any) -> dict:
    """A pack's declared mood colours, merged over the defaults."""
    try:
        sheet = yaml.safe_load(
            (pathlib.Path(root) / "character.yaml").read_text(
                encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — a pack with no sheet has no moods
        return dict(MOOD)
    declared = sheet.get("moods")
    return {**MOOD, **declared} if isinstance(declared, dict) else dict(MOOD)


def speaks_function(character: Any) -> bool:
    """True when this pack has words for what the mind is doing.

    One word is enough to opt in — a pack that only knows `listening`
    still gets to show it, and falls back to its default for the rest.
    """
    words = set(getattr(character, "expressions", ()) or ())
    return any(word in words for _state, word in FUNCTION)


def show(bus: Any, character: Any, expression: str, colour: str = "") -> None:
    """Play one look — a shape and, if the pack takes one, a colour.

    A module function because a SCENE needs exactly this too, and a
    second copy of "how to show a look" is a second place for colour to
    go missing.
    """
    from jaeger_os import topics

    from modules import jaeger_animation as animation

    spec = dict((getattr(character, "expressions", {}) or {}).get(
        expression) or {})
    params = dict(spec.get("params") or {})
    if colour:
        params["color"] = colour
    params.setdefault("loop", bool(spec.get("loop", True)))
    params.setdefault("fit", "contain")
    # `asset_root` rides INSIDE params, the same way jaeger_animation
    # puts it there — DisplayCommand has no field of its own for it.
    params.setdefault("asset_root", str(animation.project_root()))
    asset = str(spec.get("asset", character.render["asset"]))
    try:
        bus.publish(topics.DisplayCommand(
            adapter=str(spec.get("adapter", character.adapter)),
            asset_path=str(pathlib.Path(character.root) / asset),
            params=params))
    except Exception:  # noqa: BLE001 — a face is never worth raising
        pass


class AgentFace:
    """Drive one character's face from what the agent is doing.

    Owns no timer and no widget: every input is a topic, and the only
    output is a play command. That is why it can live outside any tab
    and keep working while the operator window is shut, which is the
    normal case now.
    """

    def __init__(self, app: Any, character_of: Any) -> None:
        self.app = app
        self.bus = app.bus
        self.character_of = character_of
        self.mood = ""            # named by the model, wins while set
        #: True while a SCENE is driving the face. A script that says
        #: "this is what searching looks like" must not be overwritten
        #: two seconds later by the mind going idle.
        self.held = False
        self._flags = {"thinking": False, "speaking": False, "hearing": False,
                       "failed": False}
        self._showing: tuple[str, str] | None = None

        self._watching = (
            (mind.WATCH[1], self._on_reply),
            (mind.WATCH[2], self._on_state),
            (tts.SPEAKER, self._on_speaker),
            (stt.TRANSCRIPT, self._on_heard),
        )
        for topic, handler in self._watching:
            self.bus.subscribe(topic, handler)

    # ── what is happening ────────────────────────────────────────

    def _on_state(self, msg: Any) -> None:
        state = str(getattr(msg, "state", ""))
        self._flags["thinking"] = state == "thinking"
        self._flags["failed"] = state == "error"
        self.refresh()

    def _on_speaker(self, msg: Any) -> None:
        self._flags["speaking"] = str(getattr(msg, "state", "")) == "playing"
        # Hearing and speaking are exclusive by definition: the ears are
        # deliberately shut while the voice plays.
        if self._flags["speaking"]:
            self._flags["hearing"] = False
        self.refresh()

    def _on_heard(self, msg: Any) -> None:
        """A transcript means someone just spoke. It is an EVENT, not a
        state — there is no "stopped talking" message — so it lights the
        flag and the next thing that happens clears it."""
        if getattr(msg, "text", ""):
            self._flags["hearing"] = True
            self.refresh()

    def _on_reply(self, msg: Any) -> None:
        """A reply may open with `[curious]`. Read here rather than in a
        chat tab because the colour is the CHARACTER's, not a view's —
        and the tab may not even be built."""
        from core import expressive

        character = self._character()
        if character is None:
            return
        word, _text = expressive.split(
            str(getattr(msg, "text", "")),
            tuple(moods(getattr(character, "root", ""))))
        if word:
            self.set_mood(word)

    def _character(self) -> Any:
        try:
            return self.character_of()
        except Exception:  # noqa: BLE001
            return None

    def set_mood(self, mood: str) -> None:
        """Named by the model, via a leading `[mood]` on a reply."""
        self.mood = mood or ""
        self.refresh()

    # ── what to show ─────────────────────────────────────────────

    def doing(self) -> str:
        for state, _word in FUNCTION:
            if self._flags.get(state):
                return state
        return ""

    def look(self, character: Any) -> tuple[str, str]:
        """(expression, colour) for right now.

        The expression falls back to the pack's default, which is how
        "nothing is happening" becomes the character's own idle rather
        than a state this module had to invent.
        """
        state = self.doing()
        words = set(getattr(character, "expressions", ()) or ())
        expression = getattr(character, "default_expression", "")
        for candidate, word in FUNCTION:
            if candidate == state and word in words:
                expression = word
                break
        palette = moods(getattr(character, "root", ""))
        name = self.mood or MOOD_FOR.get(state, "calm")
        return expression, palette.get(name, palette.get("calm", "#FFFFFF"))

    def refresh(self) -> None:
        """Show it, if it changed. Bus thread — this publishes a command
        and touches nothing else, which is the only reason that is fine.
        """
        character = self._character()
        if self.held or character is None or not speaks_function(character):
            return
        look = self.look(character)
        if look == self._showing:
            return          # replaying would restart the clock, visibly
        self._showing = look
        self.play(character, *look)

    def play(self, character: Any, expression: str, colour: str) -> None:
        show(self.bus, character, expression, colour)

    def hold(self, held: bool) -> None:
        """Hand the face to something else, and take it back. Taking it
        back repaints at once, so the agent's real state returns rather
        than leaving whatever the scene left behind."""
        self.held = bool(held)
        if not self.held:
            self._showing = None
            self.refresh()

    def close(self) -> None:
        for topic, handler in self._watching:
            try:
                self.bus.unsubscribe(topic, handler)
            except Exception:  # noqa: BLE001
                pass


__all__ = ["AgentFace", "FUNCTION", "MOOD", "MOOD_FOR", "moods", "show",
           "speaks_function"]
