"""导入解析测试（JSON / CSV）。"""
import pytest

from app.services.importing import ImportError_, parse_import_text


def test_parse_json_array():
    text = '[{"id": "1", "title": "t", "content": "c", "rating": 5}]'
    data = parse_import_text(text)
    assert data[0]["review_id"] == "1"
    assert data[0]["rating"] == 5


def test_parse_json_wrapped():
    text = '{"reviews": [{"id": "1", "title": "t", "content": "c", "rating": 4}]}'
    data = parse_import_text(text)
    assert len(data) == 1


def test_parse_csv():
    text = "id,title,content,rating,version\n1,t,c,3,1.0\n2,t2,c2,5,2.0"
    data = parse_import_text(text)
    assert len(data) == 2
    assert data[1]["rating"] == 5
    assert data[1]["version"] == "2.0"


def test_missing_required_field():
    with pytest.raises(ImportError_):
        parse_import_text('[{"id": "1", "title": "t", "content": "c"}]')


def test_invalid_rating():
    with pytest.raises(ImportError_):
        parse_import_text('[{"id": "1", "title": "t", "content": "c", "rating": 99}]')


def test_empty_input():
    with pytest.raises(ImportError_):
        parse_import_text("   ")
