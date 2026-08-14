"""Bitmap Man's repertoire — three scenes, each harder than the last.

Deliberately the simplest character in the project: two monochrome eyes
on a 32×32 grid, six expressions, no mouth. If the control layer needs a
rich character to look like a performance, the control layer is doing
the work art should be doing — so this is the honest test.

    idle        a loop. No timing anyone has to get right.
    looking     a scene. Face and voice interleaved on one clock.
    knock_knock a conversation. Stops dead until a person answers.

The third is the one that could not be written before: a motion script
dispatches to one channel and cannot speak, and a timeline pins every
clip to an offset chosen before anyone pressed play. Neither can express
"then wait, however long they take".
"""

from __future__ import annotations

from core.scenes import Scene, face, listen, say, wait

#: Expressions Bitmap Man actually declares. Naming them here means a
#: typo is a missing attribute at import, not a dead step at showtime.
NEUTRAL, HAPPY, CLOSED = "neutral", "happy", "closed"
UP, DOWN, SAD = "look_up", "look_down", "sad"


IDLE = Scene(
    name="idle",
    description="Looks around and blinks. Runs until you stop it.",
    loop=True,
    steps=[
        face(NEUTRAL), wait(1.6),
        face(UP), wait(1.2),
        face(NEUTRAL), wait(0.8),
        face(DOWN), wait(1.2),
        face(CLOSED), wait(0.25),      # a blink is a face held briefly
        face(NEUTRAL), wait(2.0),
    ],
)


LOOKING = Scene(
    name="looking around",
    description="Looks up, down and back, talking the whole way through.",
    steps=[
        face(NEUTRAL), wait(0.4),
        say("Let me have a look around."),
        face(UP),
        say("Up there, the ceiling. Nothing new."),
        wait(0.4),
        face(DOWN),
        say("Down here, the desk. Also nothing new."),
        wait(0.4),
        face(NEUTRAL),
        say("And straight ahead, you. That is the interesting one."),
        face(HAPPY), wait(1.5),
        face(NEUTRAL),
    ],
)


KNOCK_KNOCK = Scene(
    name="knock knock",
    description="Tells a joke, and waits for you to play along.",
    steps=[
        face(HAPPY), wait(0.3),
        say("Knock knock."),
        listen(10.0),                  # "who's there?" — or silence
        face(NEUTRAL),
        say("Bitmap."),
        listen(10.0),                  # "bitmap who?"
        face(HAPPY),
        say("Bitmap Man. And I have only got eyes for you."),
        wait(1.2),
        face(CLOSED), wait(0.3),       # the blink is the rimshot
        face(NEUTRAL),
    ],
)


#: What the Stage offers as buttons, in the order they get harder.
SCENES = (IDLE, LOOKING, KNOCK_KNOCK)

__all__ = ["SCENES", "IDLE", "LOOKING", "KNOCK_KNOCK"]
