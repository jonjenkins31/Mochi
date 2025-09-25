# animations/gif_handler.py

"""
GIF Handler: A legacy alias for the Media Handler.

Function:
This handler exists only to provide a specific 'gif_handler' name for playing
GIFs. It is a direct subclass of the MediaHandler and has no unique logic.

NOTE: This handler is redundant and considered a legacy component. The Master
Handler automatically uses the more capable MediaHandler for any .gif files.
There is no need to use this handler directly.

Inputs: See MediaHandler.

Output: See MediaHandler.
"""

from .media_handler import MediaHandler

class GifHandler(MediaHandler):
    """
    A simple handler to expose the MediaHandler for playing GIFs via scripts.
    It registers the 'gif_handler' mode name.
    """
    name = "gif_handler"
