"""Compute-tier nodes — render loops, audio sessions, ML stages.

Nodes whose "device" is software work: animation rendering, the
Whisper STT pipeline, Kokoro TTS, the audio_session that owns the
system mic + speakers. Same lifecycle as hardware nodes, no
physical wire.
"""
