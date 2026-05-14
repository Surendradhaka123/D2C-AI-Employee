"""Tests for the hard citation enforcement contract."""

from chat.citations import enforce_citations, find_uncited_numbers, SYSTEM_PROMPT


class TestCitationEnforcement:
    def test_clean_response_passes(self):
        text = "Your NDR rate is 28% [src:shiprocket:AWB10001] for DTDC courier."
        is_clean, violations = enforce_citations(text)
        assert is_clean is True
        assert violations == []

    def test_bare_rupee_amount_caught(self):
        text = "Your total revenue is ₹6,00,000 this month."
        is_clean, violations = enforce_citations(text)
        assert is_clean is False
        assert any("₹" in v for v in violations)

    def test_bare_percentage_caught(self):
        text = "The NDR rate is 28% which is above threshold."
        is_clean, violations = enforce_citations(text)
        assert is_clean is False

    def test_cited_percentage_passes(self):
        text = "The NDR rate is 28% [src:shiprocket:aggregate:47_shipments] which is above threshold."
        is_clean, violations = enforce_citations(text)
        assert is_clean is True

    def test_multiple_violations_all_caught(self):
        text = "Revenue is ₹5,00,000 and NDR rate is 26%."
        violations = find_uncited_numbers(text)
        assert len(violations) == 2

    def test_system_prompt_contains_citation_instruction(self):
        assert "[src:" in SYSTEM_PROMPT
        assert "hallucination" in SYSTEM_PROMPT.lower()

    def test_count_with_label_caught(self):
        text = "We found 400 shipments in the last 30 days."
        is_clean, violations = enforce_citations(text)
        assert is_clean is False

    def test_count_with_citation_passes(self):
        text = "We found 400 shipments [src:shiprocket:aggregate:400_shipments] in the last 30 days."
        is_clean, violations = enforce_citations(text)
        assert is_clean is True
