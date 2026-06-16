from __future__ import annotations

from agent.adapters.registry import build_adapter_registry
from agent.loop.runtime import AgentRuntime
from core.memory import Memory


def _runtime(tmp_path, adapter: str = "mock") -> AgentRuntime:
    return AgentRuntime(
        adapters=build_adapter_registry(active=adapter),
        persona="Mochi-test",
        system_prompt="test prompt",
        memory=Memory(tmp_path / "memory.jsonl"),
    )


def test_mood_tools_emit_animation_tags(tmp_path):
    runtime = _runtime(tmp_path)

    assert '<mode name="happy"/>' in runtime.respond("happy")
    assert '<mode name="sad"/>' in runtime.respond("sad")
    assert "<stop/>" in runtime.respond("off")


def test_memory_tool_and_safety_gate(tmp_path):
    runtime = _runtime(tmp_path)

    assert "Remembered" in runtime.respond("remember tea at five")
    assert "tea at five" in runtime.respond("recall")
    assert "Say 'forget everything force'" in runtime.respond("forget everything")
    assert "tea at five" in runtime.respond("recall")
    assert "Memory cleared" in runtime.respond("forget everything force")
    assert "Nothing remembered" in runtime.respond("recall")


def test_adapter_switching_and_mock_completion(tmp_path):
    runtime = _runtime(tmp_path)

    assert "Active adapter: mock" in runtime.respond("adapter")
    assert "Using adapter: ollama" in runtime.respond("use adapter ollama")
    assert runtime.adapters.active == "ollama"
    assert "Using adapter: mock" in runtime.respond("use adapter mock")
    assert runtime.respond("hello") == 'Hello. <mode name="happy"/>'
