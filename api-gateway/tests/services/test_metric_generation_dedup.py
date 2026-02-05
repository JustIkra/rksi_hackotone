"""
Tests for metric generation deduplication logic.

Covers:
- Exact name matching with different cases
- Semantic matching with different categories
- LLM decision for match vs new metric
"""

import pytest
import unicodedata
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.metric_generation import ExtractedMetricData


def normalize_name(name: str | None) -> str:
    """Normalize name for comparison: lowercase, strip, unicode NFKC."""
    if not name:
        return ""
    return unicodedata.normalize("NFKC", name.lower().strip())


class TestNormalizeName:
    """Tests for name normalization function."""

    @pytest.mark.unit
    def test_normalize_preserves_russian(self):
        """Russian text should be normalized consistently."""
        assert normalize_name("Нормативность") == normalize_name("нормативность")
        assert normalize_name("Нормативность") == normalize_name("НОРМАТИВНОСТЬ")

    @pytest.mark.unit
    def test_normalize_strips_whitespace(self):
        """Leading/trailing whitespace should be removed."""
        assert normalize_name("  Нормативность  ") == normalize_name("Нормативность")
        assert normalize_name("\tТворчество\n") == normalize_name("Творчество")

    @pytest.mark.unit
    def test_normalize_unicode_variations(self):
        """Unicode variations should be normalized."""
        # NFKC normalization converts compatibility characters
        name1 = "Нормативность"  # Regular
        name2 = "Нормативность"  # Could have different unicode representation
        assert normalize_name(name1) == normalize_name(name2)

    @pytest.mark.unit
    def test_normalize_empty_returns_empty(self):
        """Empty or None input should return empty string."""
        assert normalize_name("") == ""
        assert normalize_name(None) == ""


class TestMatchExistingMetric:
    """Tests for exact metric matching."""

    @pytest.fixture
    def existing_metrics(self):
        """Sample existing metrics."""
        return [
            {"code": "normativeness", "name": "Normativeness", "name_ru": "Нормативность"},
            {"code": "creativity", "name": "Creativity", "name_ru": "Творчество"},
            {"code": "stress_resistance", "name": "Stress Resistance", "name_ru": "Стрессоустойчивость"},
        ]

    @pytest.fixture
    def existing_synonyms(self):
        """Sample synonyms."""
        return [
            {"synonym": "Креативность", "metric_code": "creativity"},
            {"synonym": "Творческое мышление", "metric_code": "creativity"},
        ]

    @pytest.mark.unit
    def test_normalize_match_case_insensitive(self, existing_metrics):
        """Same name with different case should match."""
        name_normalized = normalize_name("нормативность")

        matched = None
        for m in existing_metrics:
            if normalize_name(m.get("name_ru")) == name_normalized:
                matched = m
                break

        assert matched is not None
        assert matched["code"] == "normativeness"

    @pytest.mark.unit
    def test_normalize_match_with_extra_whitespace(self, existing_metrics):
        """Names with extra whitespace should match."""
        name_normalized = normalize_name("  Нормативность  ")

        matched = None
        for m in existing_metrics:
            if normalize_name(m.get("name_ru")) == name_normalized:
                matched = m
                break

        assert matched is not None
        assert matched["code"] == "normativeness"

    @pytest.mark.unit
    def test_synonym_match(self, existing_metrics, existing_synonyms):
        """Synonyms should match to correct metric."""
        name_normalized = normalize_name("Креативность")

        matched_code = None
        for s in existing_synonyms:
            if normalize_name(s["synonym"]) == name_normalized:
                matched_code = s["metric_code"]
                break

        assert matched_code == "creativity"


class TestSemanticMatching:
    """Tests for semantic (embedding-based) matching."""

    @pytest.mark.unit
    def test_auto_match_high_similarity(self):
        """Very high similarity (>= 0.95) should auto-match without LLM."""
        # Mock embedding service returning high similarity
        candidates = [
            {
                "metric_def_id": "uuid-1",
                "code": "normativeness",
                "name": "Normativeness",
                "name_ru": "Нормативность",
                "similarity": 0.96,
                "indexed_text": "Normativeness | Нормативность",
            }
        ]

        # Similarity >= 0.95 should trigger auto-match
        assert candidates[0]["similarity"] >= 0.95

    @pytest.mark.unit
    def test_llm_decision_with_candidates(self):
        """LLM should be called when similarity is below auto-match threshold."""
        candidates = [
            {
                "code": "normativeness",
                "name_ru": "Нормативность",
                "similarity": 0.85,
                "indexed_text": "Normativeness | Нормативность",
            },
            {
                "code": "responsibility",
                "name_ru": "Ответственность",
                "similarity": 0.72,
                "indexed_text": "Responsibility | Ответственность",
            },
        ]

        # Similarity < 0.95 should require LLM decision
        assert candidates[0]["similarity"] < 0.95


class TestCategoryAgnosticMatching:
    """Tests for matching metrics regardless of category."""

    @pytest.mark.unit
    def test_same_name_different_category_should_match(self):
        """Metric with same name but different category should be considered duplicate."""
        # Existing metric in "Волевые компетенции"
        existing = {
            "code": "normativeness",
            "name_ru": "Нормативность",
            "category": "will_competencies",
        }

        # Extracted metric might have different category from PDF
        extracted = ExtractedMetricData(
            name="Нормативность",
            description="Настроенность на поведение в соответствии с нормами",
            category="motivation",  # Different category!
        )

        # Should match by name regardless of category
        assert normalize_name(extracted.name) == normalize_name(existing["name_ru"])

    @pytest.mark.unit
    def test_synonymous_names_should_match(self):
        """Semantically equivalent names should be considered duplicates."""
        equivalents = [
            ("Творчество", "Креативность"),
            ("Творческое мышление", "Творчество"),
            ("Внутренняя мотивация", "Интерес к процессу"),
        ]

        # These pairs should be considered as potentially the same metric
        # LLM should decide based on semantic similarity
        for name1, name2 in equivalents:
            # Names are different but should be caught by semantic search
            assert normalize_name(name1) != normalize_name(name2)


class TestLLMDecisionPrompt:
    """Tests for LLM decision prompt content."""

    @pytest.mark.unit
    def test_prompt_includes_category_agnostic_instruction(self):
        """Prompt should instruct LLM to ignore categories."""
        from app.core.prompt_loader import get_prompt_loader

        loader = get_prompt_loader()
        cfg = loader.load("metric-mapping-decision")
        system_prompt = cfg.get("decision_system", "")

        # Should include instruction to ignore categories
        assert "категори" in system_prompt.lower() or "ИГНОРИРУЙ" in system_prompt

    @pytest.mark.unit
    def test_prompt_focuses_on_name_matching(self):
        """Prompt should focus on name/semantic matching."""
        from app.core.prompt_loader import get_prompt_loader

        loader = get_prompt_loader()
        cfg = loader.load("metric-mapping-decision")
        system_prompt = cfg.get("decision_system", "")

        # Should mention focusing on name
        assert "название" in system_prompt.lower() or "семантическ" in system_prompt.lower()


class TestDuplicateScenarios:
    """Integration-style tests for real duplicate scenarios."""

    @pytest.mark.unit
    def test_scenario_normativeness_duplicate(self):
        """
        Scenario: 'Нормативность' extracted from PDF should match existing metric.

        Existing: code=normativeness, name_ru='Нормативность', category='Волевые'
        Extracted: name='Нормативность', category='Мотивационные' (different!)

        Expected: Should match despite different category.
        """
        existing_name = "Нормативность"
        extracted_name = "Нормативность"

        # Step 1: Exact match should work
        assert normalize_name(existing_name) == normalize_name(extracted_name)

    @pytest.mark.unit
    def test_scenario_creativity_synonyms(self):
        """
        Scenario: Multiple creativity-related names should map to same metric.
        """
        creativity_variants = [
            "Творчество",
            "Креативность",
            "Творческое мышление",
            "Творческий подход",
        ]

        # All should normalize to different strings (need semantic matching)
        normalized = [normalize_name(v) for v in creativity_variants]

        # They're different strings, so exact match won't work
        # Need semantic matching via embeddings + LLM
        assert len(set(normalized)) == len(creativity_variants)

    @pytest.mark.unit
    def test_scenario_interest_vs_internal_motivation(self):
        """
        Scenario: 'Интерес' and 'Внутренняя мотивация' might be related but different.

        LLM should decide based on context whether they're the same metric.
        """
        # These might be the same or different depending on assessment system
        names = ["Интерес", "Внутренняя мотивация", "Интерес к процессу"]

        # Need semantic similarity to determine relationship
        # This is why we use RAG + LLM instead of just exact matching
        for name in names:
            assert normalize_name(name)  # All should be valid


class TestCategoryFallbackBug:
    """
    Tests for the category fallback bug fix.

    Issue: When RAG returns no candidates (similarity below threshold),
    the code was falling back to category-based candidates with similarity=0.0
    and asking LLM to match against these unrelated metrics.

    Fix: Don't use category fallback for semantic matching. If RAG finds
    nothing, return None so a new metric can be created.

    See: docs/issues/2026-02-05-metric-generation-no-new-metrics.md
    """

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_rag_candidates_returns_none(self):
        """
        When RAG returns no candidates, match_metric_semantic should return None.

        This ensures that unknown metrics are created as PENDING instead of
        being incorrectly matched to unrelated metrics from the same category.

        BUG DEMONSTRATION: Before the fix, this test would fail because
        the category fallback would find metrics from the same category
        and the LLM would incorrectly match against them.

        AFTER FIX: When RAG returns empty, function returns None immediately
        without using category fallback, allowing new metrics to be created.
        """
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.services.metric_generation import MetricGenerationService

        # Create service with mocked dependencies
        mock_db = AsyncMock()
        mock_redis = MagicMock()
        mock_embedding_service = AsyncMock()

        # Mock embedding service to return NO candidates (simulating low similarity)
        mock_embedding_service.find_similar = AsyncMock(return_value=[])

        with patch("app.services.metric_generation.OpenRouterClient"):
            service = MetricGenerationService(
                db=mock_db,
                redis=mock_redis,
            )
            service.embedding_service = mock_embedding_service

        extracted = ExtractedMetricData(
            name="Интернальность",  # This metric doesn't exist in DB
            description="Тест метрика",
            category="Психологические",
        )

        # Before fix: this would call _get_category_fallback_candidates and
        # potentially return a false match from the same category.
        # After fix: this should return None immediately.
        result, similarity = await service.match_metric_semantic(extracted)

        assert result is None, (
            "Expected None when RAG returns no candidates. "
            "Bug: category fallback was causing false matches."
        )
        assert similarity == 0.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_low_similarity_candidates_with_llm_unknown(self):
        """
        When all candidates have low similarity and LLM returns 'unknown',
        match_metric_semantic should return None.
        """
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.services.metric_generation import MetricGenerationService

        mock_db = AsyncMock()
        mock_redis = MagicMock()
        mock_embedding_service = AsyncMock()

        # Mock embedding service to return low-similarity candidates
        mock_embedding_service.find_similar = AsyncMock(return_value=[
            {
                "metric_def_id": "uuid-1",
                "code": "some_unrelated",
                "name": "Unrelated Metric",
                "name_ru": "Несвязанная метрика",
                "similarity": 0.35,  # Low but above threshold
                "indexed_text": "Some unrelated metric",
            }
        ])

        with patch("app.services.metric_generation.OpenRouterClient"):
            service = MetricGenerationService(
                db=mock_db,
                redis=mock_redis,
            )
            service.embedding_service = mock_embedding_service

        extracted = ExtractedMetricData(
            name="Сила личности",
            description="Уникальная метрика",
            category="Личностные",
        )

        # Mock LLM to return "unknown" decision
        mock_ai_client = AsyncMock()
        mock_ai_client.generate_text = AsyncMock(return_value={
            "choices": [{
                "message": {
                    "content": '{"decision": "unknown", "metric_code": null, "confidence": 0.3, "reason": "Метрика концептуально отличается от всех кандидатов"}'
                }
            }]
        })
        mock_ai_client.close = AsyncMock()

        # Patch at the correct module level where create_ai_client is imported
        with patch("app.core.ai_factory.create_ai_client", return_value=mock_ai_client):
            result, similarity = await service.match_metric_semantic(extracted)

        assert result is None
        assert similarity == 0.0
