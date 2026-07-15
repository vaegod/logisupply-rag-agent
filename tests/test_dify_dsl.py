from pathlib import Path

import yaml


DSL_FILE = Path(__file__).parents[1] / "dify" / "logisupply_chatflow.dify.yml"


def load_dsl() -> dict:
    with DSL_FILE.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def test_dsl_has_current_app_envelope() -> None:
    dsl = load_dsl()

    assert dsl["kind"] == "app"
    assert dsl["version"] == "0.3.1"
    assert dsl["app"]["mode"] == "advanced-chat"


def test_dsl_contains_all_required_node_types() -> None:
    dsl = load_dsl()
    node_types = [node["data"]["type"] for node in dsl["workflow"]["graph"]["nodes"]]

    assert node_types.count("question-classifier") == 1
    assert node_types.count("knowledge-retrieval") == 2
    assert node_types.count("parameter-extractor") == 2
    assert node_types.count("http-request") == 2
    assert node_types.count("llm") == 4
    assert node_types.count("answer") == 4


def test_dsl_edges_reference_existing_nodes() -> None:
    dsl = load_dsl()
    graph = dsl["workflow"]["graph"]
    node_ids = {node["id"] for node in graph["nodes"]}

    for edge in graph["edges"]:
        assert edge["source"] in node_ids
        assert edge["target"] in node_ids


def test_classifier_has_four_connected_branches() -> None:
    dsl = load_dsl()
    graph = dsl["workflow"]["graph"]
    classifier = next(node for node in graph["nodes"] if node["id"] == "classifier")
    class_ids = {item["id"] for item in classifier["data"]["classes"]}
    handles = {
        edge["sourceHandle"]
        for edge in graph["edges"]
        if edge["source"] == "classifier"
    }

    assert class_ids == {"knowledge", "order", "exception", "other"}
    assert handles == class_ids


def test_dsl_does_not_contain_real_credentials_or_tunnel_domains() -> None:
    content = DSL_FILE.read_text(encoding="utf-8")

    assert "DIFY_API_KEY" not in content
    assert "ngrok" not in content.lower()
    assert "replace-me.example.com" in content
