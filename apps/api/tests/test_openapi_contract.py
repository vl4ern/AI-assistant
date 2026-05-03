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
