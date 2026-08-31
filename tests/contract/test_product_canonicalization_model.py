"""Ark 商品归一化模型适配器的结构化输出契约。"""

from __future__ import annotations

from shijiajing_agent.adapters.ark_models import (
    ArkDynamicProductCanonicalizer,
    ArkDynamicSchemaInducer,
)
from shijiajing_agent.contracts import Offer, VerifiedDynamicSchema


async def test_dynamic_ark_ports_share_structured_contract(ark_client) -> None:
    responses = [
        """{
          "concepts": [{
            "local_concept_id": "widget",
            "canonical_label": "Widget",
            "label_confidence": 0.99,
            "evidence": [{"offer_id": "offer-1", "source_path": "title", "raw_value": "Widget"}],
            "attributes": []
          }],
          "assignments": [{
            "offer_id": "offer-1",
            "local_concept_id": "widget",
            "confidence": 0.99,
            "evidence": [{"offer_id": "offer-1", "source_path": "title", "raw_value": "Widget"}]
          }]
        }""",
        """{
          "schema_id": "0000000000000000000000000000000000000000000000000000000000000000",
          "items": [{
            "offer_id": "offer-1",
            "local_concept_id": "widget",
            "category_concept": "Widget",
            "category_confidence": 0.99,
            "category_evidence": {
              "offer_id": "offer-1",
              "source_path": "title",
              "raw_value": "Widget"
            },
            "fields": [],
            "unresolved_fields": []
          }]
        }""",
    ]
    client, server = ark_client(responses)
    offer = Offer(offer_id="offer-1", platform="test", title="Acme Widget")
    schema = VerifiedDynamicSchema(schema_id="0" * 64, input_offer_ids=[offer.offer_id])

    proposal = await ArkDynamicSchemaInducer(client).induce_schema([offer])
    result = await ArkDynamicProductCanonicalizer(client).canonicalize_dynamic([offer], schema)

    assert proposal.assignments[0].offer_id == offer.offer_id
    assert result.schema_id == schema.schema_id
    assert len(server.requests) == 2
    assert "不可信数据" in server.requests[1]["messages"][1]["content"]
    await client.close()
