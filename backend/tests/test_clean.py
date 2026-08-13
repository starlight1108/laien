"""清洗与去重测试（确定性规则）。"""
from app.schemas import RawReview
from app.services.clean import clean_pipeline, clean_review, deduplicate, normalize_text


def _r(rid: str, content: str, rating: int = 3) -> RawReview:
    return RawReview(review_id=rid, title="", content=content, rating=rating)


def _clean(rid: str, content: str, rating: int = 3):
    return clean_review(_r(rid, content, rating))


def test_normalize_text():
    assert normalize_text("  Hello, WORLD!!! ") == "hello world"
    assert normalize_text("I love 💪 this app!") == "i love this app"


def test_exact_deduplication():
    out = deduplicate([_clean("a", "This app is great!"), _clean("b", "This app is great!")])
    dup = [r for r in out if r.is_duplicate]
    assert len(dup) == 1
    assert dup[0].review_id == "b"


def test_near_deduplication():
    a = "The workout plans are really useful and I love the reminders feature."
    b = "The workout plans are really useful and I love the reminders feature!!"
    out = deduplicate([_clean("a", a), _clean("b", b)])
    dup = [r for r in out if r.is_duplicate]
    assert len(dup) == 1


def test_clean_pipeline_report():
    raw = [
        _r("1", "Great app for home workouts!"),
        _r("2", "Great app for home workouts!"),
        _r("3", "Crash on startup every time."),
    ]
    result = clean_pipeline(raw)
    assert result["report"]["input_count"] == 3
    assert result["report"]["kept_count"] == 2
    assert result["report"]["duplicate_count"] == 1
    assert len(result["kept"]) == 2


def test_clean_pipeline_removes_html():
    raw = [_r("1", "Love it &amp; highly recommend <b>everyone</b>")]
    result = clean_pipeline(raw)
    assert "&amp;" not in result["kept"][0].content
    assert "<b>" not in result["kept"][0].content
