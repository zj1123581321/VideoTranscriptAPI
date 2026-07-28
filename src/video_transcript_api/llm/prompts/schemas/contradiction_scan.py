"""Semantic contradiction scan JSON schema."""

CONTRADICTION_SCAN_SCHEMA = {
    "type": "object",
    "properties": {
        "contradictions": {
            "type": "array",
            "description": "疑似说话人归属矛盾的段落",
            "items": {
                "type": "object",
                "properties": {
                    "segment_id": {"type": "string", "minLength": 1},
                    "reason": {
                        "type": "string",
                        "enum": [
                            "direct_address_conflict",
                            "self_reference_conflict",
                            "third_person_conflict",
                            "qa_adjacency_conflict",
                        ],
                    },
                    "evidence_segment_ids": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": 1,
                    },
                },
                "required": ["segment_id", "reason", "evidence_segment_ids"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["contradictions"],
    "additionalProperties": False,
}

