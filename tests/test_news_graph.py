"""Graph extraction must reject unsupported or invented relations."""
import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "build_news_graph", Path(__file__).resolve().parents[1] / "scripts/build-news-graph.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_only_verbatim_supported_relation_is_saved():
    source = "台積電宣布擴建先進封裝產能。"
    good = {"subject": {"kind": "company", "name": "台積電"},
            "predicate": "involved_in", "object": {"kind": "event", "name": "擴建先進封裝產能"},
            "evidence": source}
    invented = {**good, "evidence": "台積電股價因此大漲。"}
    wrong_type = {**good, "predicate": "predicts_price"}
    assert MODULE.validate_relations({"relations": [good, invented, wrong_type]}, source) == [
        ("company", "台積電", "involved_in", "event", "擴建先進封裝產能", source)]


def test_missing_or_malformed_relations_fail_closed():
    try:
        MODULE.validate_relations({"entities": []}, "新聞內容")
    except ValueError:
        pass
    else:
        raise AssertionError("Missing relations array must fail")
    assert MODULE.validate_relations({"relations": [{"subject": "fake"}]}, "新聞內容") == []


def test_evidence_whitespace_is_restored_from_original():
    source = "聯發科推升指數至48,601點。"
    relation = {"subject": {"kind": "company", "name": "聯發科"},
                "predicate": "involved_in", "object": {"kind": "event", "name": "指數上漲"},
                "evidence": "聯發科推升指數至 48,601 點。"}
    assert MODULE.validate_relations({"relations": [relation]}, source)[0][-1] == source
