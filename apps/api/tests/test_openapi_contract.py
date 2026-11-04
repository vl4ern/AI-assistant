from __future__ import annotations

from pathlib import Path

import yaml


def _load_contract() -> dict:
    root = Path(__file__).resolve().parents[3]
    contract_path = root / "packages" / "contracts" / "openapi.yaml"
    return yaml.safe_load(contract_path.read_text(encoding="utf-8"))


def test_contract_contains_intelligence_fields() -> None:
    contract = _load_contract()

    task_create_props = (
        contract["components"]["schemas"]["TaskCreate"]["properties"]
    )

    assert "depends_on" in task_create_props
    assert "allow_split" in task_create_props
    assert "min_chunk_minutes" in task_create_props


def test_contract_contains_task_extraction_endpoint() -> None:
    contract = _load_contract()

    path = contract["paths"]["/v1/tasks/extract"]["post"]
    assert path["security"] == [{"bearerAuth": []}]

    request_schema = path["requestBody"]["content"]["multipart/form-data"][
        "schema"
    ]
    assert set(request_schema["properties"]) == {"text", "file"}

    draft_props = contract["components"]["schemas"]["TaskDraft"]["properties"]
    assert "title" in draft_props
    assert "input_kind" in draft_props
    assert "warnings" in draft_props
    assert draft_props["input_kind"]["enum"] == ["text", "image"]

    drafts_props = (
        contract["components"]["schemas"]["TaskDrafts"]["properties"]
    )
    assert "tasks" in drafts_props
    assert drafts_props["tasks"]["type"] == "array"
    assert drafts_props["tasks"]["items"]["$ref"] == "#/components/schemas/TaskDraft"


def test_contract_task_extraction_accepts_several_files() -> None:
    contract = _load_contract()

    path = contract["paths"]["/v1/tasks/extract"]["post"]
    request_schema = path["requestBody"]["content"]["multipart/form-data"]["schema"]
    file_prop = request_schema["properties"]["file"]
    assert "files" not in file_prop
    assert file_prop["type"] == "array"
    assert file_prop["items"]["format"] == "binary"

    assert contract["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"


def test_contract_contains_reorder_feedback_endpoint() -> None:
    contract = _load_contract()

    paths = contract["paths"]
    assert "/v1/schedule/reorder-feedback" in paths

    payload_props = (
        contract["components"]["schemas"]["ReorderFeedbackRequest"]["properties"]
    )
    assert "moved_task_id" in payload_props
    assert "left_task_id" in payload_props
    assert "right_task_id" in payload_props
