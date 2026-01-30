"""
Tests for metric mapping LLM decision service.
"""

import json
import pytest
from unittest.mock import AsyncMock


class FakeAIClient:
    """Fake AI client for testing."""
    
    def __init__(self, response_content: str):
        self._content = response_content
        self.calls = 0
        self.last_prompt = None
        self.last_system_prompt = None
    
    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs,
    ) -> dict:
        self.calls += 1
        self.last_prompt = prompt
        self.last_system_prompt = system_prompt
        return {"choices": [{"message": {"content": self._content}}]}


def make_candidates(codes: list[str]) -> list[dict]:
    """Create test candidates."""
    return [
        {
            "code": code,
            "similarity": 0.9 - i * 0.1,
            "name_ru": f"Метрика {code}",
            "indexed_text": f"Test metric {code}",
            "description": None,
        }
        for i, code in enumerate(codes)
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_decision_match_picks_from_candidates(monkeypatch):
    """LLM returns match with valid code → status=mapped."""
    from app.services.metric_mapping_llm_decision import decide_metric_mapping
    
    # Mock prompts
    monkeypatch.setattr(
        "app.services.metric_mapping_llm_decision.get_metric_mapping_decision_system",
        lambda: "system",
    )
    monkeypatch.setattr(
        "app.services.metric_mapping_llm_decision.get_metric_mapping_decision_user_prefix",
        lambda: "Label: {label}\n{candidates}",
    )
    
    ai = FakeAIClient(json.dumps({
        "decision": "match",
        "metric_code": "metric_a",
        "confidence": 0.9,
        "reason": "Exact match",
    }))
    
    candidates = make_candidates(["metric_a", "metric_b"])
    result = await decide_metric_mapping(
        ai_client=ai,
        label="Метрика А",
        candidates=candidates,
        min_confidence=0.6,
    )
    
    assert result["status"] == "mapped"
    assert result["code"] == "metric_a"
    assert result["confidence"] == 0.9
    assert ai.calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_decision_invalid_code_returns_unknown(monkeypatch):
    """LLM returns code not in candidates → guardrail returns unknown."""
    from app.services.metric_mapping_llm_decision import decide_metric_mapping
    
    monkeypatch.setattr(
        "app.services.metric_mapping_llm_decision.get_metric_mapping_decision_system",
        lambda: "system",
    )
    monkeypatch.setattr(
        "app.services.metric_mapping_llm_decision.get_metric_mapping_decision_user_prefix",
        lambda: "Label: {label}\n{candidates}",
    )
    
    # LLM hallucinates a code
    ai = FakeAIClient(json.dumps({
        "decision": "match",
        "metric_code": "invented_code",
        "confidence": 0.95,
        "reason": "I made this up",
    }))
    
    candidates = make_candidates(["metric_a", "metric_b"])
    result = await decide_metric_mapping(
        ai_client=ai,
        label="Test",
        candidates=candidates,
    )
    
    assert result["status"] == "unknown"
    assert result["code"] is None
    assert "invalid code" in result["reason"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_decision_invalid_json_returns_unknown(monkeypatch):
    """Invalid JSON response → unknown."""
    from app.services.metric_mapping_llm_decision import decide_metric_mapping
    
    monkeypatch.setattr(
        "app.services.metric_mapping_llm_decision.get_metric_mapping_decision_system",
        lambda: "system",
    )
    monkeypatch.setattr(
        "app.services.metric_mapping_llm_decision.get_metric_mapping_decision_user_prefix",
        lambda: "Label: {label}\n{candidates}",
    )
    
    ai = FakeAIClient("not valid json at all")
    
    candidates = make_candidates(["metric_a"])
    result = await decide_metric_mapping(
        ai_client=ai,
        label="Test",
        candidates=candidates,
    )
    
    assert result["status"] == "unknown"
    assert "Invalid JSON" in result["reason"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_decision_ambiguous(monkeypatch):
    """LLM returns ambiguous → status=ambiguous."""
    from app.services.metric_mapping_llm_decision import decide_metric_mapping
    
    monkeypatch.setattr(
        "app.services.metric_mapping_llm_decision.get_metric_mapping_decision_system",
        lambda: "system",
    )
    monkeypatch.setattr(
        "app.services.metric_mapping_llm_decision.get_metric_mapping_decision_user_prefix",
        lambda: "Label: {label}\n{candidates}",
    )
    
    ai = FakeAIClient(json.dumps({
        "decision": "ambiguous",
        "metric_code": None,
        "confidence": 0.5,
        "reason": "Multiple candidates match equally",
    }))
    
    candidates = make_candidates(["metric_a", "metric_b"])
    result = await decide_metric_mapping(
        ai_client=ai,
        label="Test",
        candidates=candidates,
    )
    
    assert result["status"] == "ambiguous"
    assert result["code"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_decision_unknown(monkeypatch):
    """LLM returns unknown → status=unknown."""
    from app.services.metric_mapping_llm_decision import decide_metric_mapping
    
    monkeypatch.setattr(
        "app.services.metric_mapping_llm_decision.get_metric_mapping_decision_system",
        lambda: "system",
    )
    monkeypatch.setattr(
        "app.services.metric_mapping_llm_decision.get_metric_mapping_decision_user_prefix",
        lambda: "Label: {label}\n{candidates}",
    )
    
    ai = FakeAIClient(json.dumps({
        "decision": "unknown",
        "metric_code": None,
        "confidence": 0.2,
        "reason": "No candidate matches the label",
    }))
    
    candidates = make_candidates(["metric_a"])
    result = await decide_metric_mapping(
        ai_client=ai,
        label="Unrelated label",
        candidates=candidates,
    )
    
    assert result["status"] == "unknown"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_decision_low_confidence_returns_unknown(monkeypatch):
    """Confidence below threshold → unknown."""
    from app.services.metric_mapping_llm_decision import decide_metric_mapping
    
    monkeypatch.setattr(
        "app.services.metric_mapping_llm_decision.get_metric_mapping_decision_system",
        lambda: "system",
    )
    monkeypatch.setattr(
        "app.services.metric_mapping_llm_decision.get_metric_mapping_decision_user_prefix",
        lambda: "Label: {label}\n{candidates}",
    )
    
    ai = FakeAIClient(json.dumps({
        "decision": "match",
        "metric_code": "metric_a",
        "confidence": 0.4,  # Below 0.6 threshold
        "reason": "Unsure match",
    }))
    
    candidates = make_candidates(["metric_a"])
    result = await decide_metric_mapping(
        ai_client=ai,
        label="Test",
        candidates=candidates,
        min_confidence=0.6,
    )
    
    assert result["status"] == "unknown"
    assert "below threshold" in result["reason"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_decision_empty_candidates():
    """Empty candidates → unknown without calling LLM."""
    from app.services.metric_mapping_llm_decision import decide_metric_mapping
    
    ai = FakeAIClient("{}")
    
    result = await decide_metric_mapping(
        ai_client=ai,
        label="Test",
        candidates=[],
    )
    
    assert result["status"] == "unknown"
    assert ai.calls == 0  # LLM should not be called
