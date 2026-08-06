"""Unit checks for posting verification semantics (no browser)."""


def test_uncertain_last_attempt_returns_false_in_source():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / "bot" / "fb_poster.py"
    text = source.read_text(encoding="utf-8")
    assert "Consider uncertain as success" not in text
    assert "status uncertain after" in text
    assert "publish_button_selectors" in text
    assert "treating as unsuccessful" in text or "not counting as success" in text
