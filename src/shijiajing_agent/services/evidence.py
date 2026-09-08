"""证据注册、引用检查和字段级质量报告。"""

from __future__ import annotations

import json
from dataclasses import dataclass

from shijiajing_agent.agent_runtime.contracts import (
    EvidenceQualityReport,
    EvidenceRecord,
    VerifiedFact,
)
from shijiajing_agent.contracts import RankedGroup, content_hash


@dataclass(frozen=True)
class EvidenceInspection:
    records: list[EvidenceRecord]
    reports: list[EvidenceQualityReport]
    invalid_ids: list[str]


class EvidenceService:
    """证据 ID 由服务端从受控商品字段计算，模型不能凭空生成。"""

    _FIELDS = (
        "title",
        "platform",
        "price",
        "original_price",
        "shipping_fee",
        "coupon_amount",
        "currency",
        "category_id",
        "brand",
        "model",
        "variant_attributes",
        "source_updated_at",
    )

    def register(self, groups: list[RankedGroup]) -> list[EvidenceRecord]:
        result: list[EvidenceRecord] = []
        for ranked in groups:
            group_id = ranked.group.group_id
            for offer in ranked.group.offers:
                fields = {
                    name: getattr(offer, name)
                    for name in self._FIELDS
                    if getattr(offer, name) is not None
                }
                payload = {
                    "candidate_id": group_id,
                    "offer_id": offer.offer_id,
                    "source_id": offer.source_product_id or offer.offer_id,
                    "data_version": offer.data_version,
                    "fields": fields,
                    "source_time": offer.source_updated_at,
                }
                digest = content_hash(payload)
                result.append(
                    EvidenceRecord(
                        evidence_id=digest,
                        candidate_id=group_id,
                        offer_id=offer.offer_id,
                        source_id=offer.source_product_id or offer.offer_id,
                        data_version=offer.data_version,
                        fields=fields,
                        source_time=offer.source_updated_at,
                        content_hash=content_hash(
                            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
                        ),
                    )
                )
        return result

    def inspect(
        self,
        evidence: dict[str, EvidenceRecord],
        evidence_ids: list[str],
        *,
        fields: list[str] | None = None,
        result_id: str | None = None,
        constraints_version: int = 1,
    ) -> EvidenceInspection:
        records: list[EvidenceRecord] = []
        invalid: list[str] = []
        requested = list(dict.fromkeys(evidence_ids))
        for evidence_id in requested:
            record = evidence.get(evidence_id)
            if record is None:
                invalid.append(evidence_id)
            else:
                records.append(record)
        reports: list[EvidenceQualityReport] = []
        if result_id is not None:
            selected = [item for item in records if item.candidate_id == result_id]
            allowed_fields = set(fields or [])
            facts: list[VerifiedFact] = []
            for item in selected:
                for field, value in item.fields.items():
                    if allowed_fields and field not in allowed_fields:
                        continue
                    if value is not None:
                        facts.append(
                            VerifiedFact(
                                candidate_id=result_id,
                                field=field,
                                value=value,
                                evidence_ids=[item.evidence_id],
                            )
                        )
            reports.append(
                EvidenceQualityReport(
                    result_id=result_id,
                    constraints_version=constraints_version,
                    comparable=bool(selected),
                    evidence_ids=[item.evidence_id for item in selected],
                    missing_fields=(fields or [])
                    if not selected
                    else [
                        field
                        for field in (fields or [])
                        if not any(field in item.fields for item in selected)
                    ],
                    allowed_facts=facts,
                )
            )
        return EvidenceInspection(records=records, reports=reports, invalid_ids=invalid)

    def quality_for_groups(
        self,
        groups: list[RankedGroup],
        records: dict[str, EvidenceRecord],
        *,
        constraints_version: int,
    ) -> list[EvidenceQualityReport]:
        reports: list[EvidenceQualityReport] = []
        for ranked in groups:
            group = ranked.group
            group_records = [
                item for item in records.values() if item.candidate_id == group.group_id
            ]
            evidence_ids = [item.evidence_id for item in group_records]
            facts: list[VerifiedFact] = []
            for item in group_records:
                for field in ("price", "platform", "title", "brand", "model", "currency"):
                    if field in item.fields:
                        facts.append(
                            VerifiedFact(
                                candidate_id=group.group_id,
                                field=field,
                                value=item.fields[field],
                                evidence_ids=[item.evidence_id],
                            )
                        )
            missing: list[str] = []
            if group.min_price is None:
                missing.append("price")
            if not group_records:
                missing.append("evidence")
            reports.append(
                EvidenceQualityReport(
                    result_id=group.group_id,
                    constraints_version=constraints_version,
                    comparable=bool(group_records) and not group.missing_sku_attributes,
                    evidence_ids=evidence_ids,
                    missing_fields=missing + list(group.missing_sku_attributes),
                    conflict_fields=list(group.risks),
                    allowed_facts=facts,
                )
            )
        return reports


__all__ = ["EvidenceInspection", "EvidenceService"]
