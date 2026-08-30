# SPDX-License-Identifier: AGPL-3.0-or-later
from validrig.models.sut import SUTBinding, SUTSpec
from validrig.sut.fake import FakeModel
from validrig.sut.registry import build_adapter


def _fake():
    return FakeModel(system_prompt="summarize", model_version="1")


def test_fake_model_is_deterministic():
    m = _fake()
    a = m.generate("some clinical document with EGFR", seed=7)
    b = m.generate("some clinical document with EGFR", seed=7)
    assert a.raw_output == b.raw_output
    assert a.usage == b.usage


def test_different_document_changes_output():
    m = _fake()
    a = m.generate("document one", seed=7)
    b = m.generate("document two", seed=7)
    assert a.raw_output != b.raw_output


def test_seed_changes_output():
    m = _fake()
    a = m.generate("same document", seed=1)
    b = m.generate("same document", seed=2)
    assert a.raw_output != b.raw_output


def test_output_contains_document_evidence():
    # evidence tokens present in the document must survive into the output so the
    # judge can find them; this is what makes ablation lower the score.
    m = _fake()
    out = m.generate("Findings include EGFR exon 19 deletion.", seed=0)
    assert "EGFR" in out.raw_output


def test_usage_is_consistent():
    m = _fake()
    out = m.generate("a b c d e", seed=0)
    assert out.usage.total_tokens == out.usage.prompt_tokens + out.usage.completion_tokens
    assert out.usage.total_tokens > 0
    assert out.usage.cost_chf >= 0.0


def test_registry_builds_fake_for_fake_binding():
    spec = SUTSpec(
        id="s",
        kind="llm_call",
        binding=SUTBinding(model_id="fake", model_version="1", system_prompt="x"),
    )
    adapter = build_adapter(spec)
    assert isinstance(adapter, FakeModel)
