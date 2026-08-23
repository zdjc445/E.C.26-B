"""召回后的确定性相关性二阶段重排。"""

from __future__ import annotations

from shijiajing_agent.contracts import RetrievalCandidate, RetrievalQuery


class CandidateRelevanceReranker:
    version = "candidate-rerank-v1"

    def rerank(
        self,
        candidates: list[RetrievalCandidate],
        query: RetrievalQuery,
        limit: int,
    ) -> list[RetrievalCandidate]:
        keywords = {
            token.lower()
            for token in (query.query_text.split() + query.soft_terms)
            if token.strip()
        }
        negative = {token.lower() for token in query.negative_terms if token.strip()}
        scored: list[RetrievalCandidate] = []
        for candidate in candidates:
            offer = candidate.offer
            text = " ".join(
                value for value in (offer.title, offer.brand or "", offer.model or "") if value
            ).lower()
            keyword_hits = sum(1 for keyword in keywords if keyword in text)
            negative_hits = sum(1 for term in negative if term in text)
            score = (
                candidate.recall_score * 0.45
                + (1.0 if offer.category_id == query.hard_filters.category_id else 0.0) * 0.20
                + min(1.0, keyword_hits / max(1, len(keywords))) * 0.20
                - min(1.0, negative_hits) * 0.15
            )
            scored.append(
                candidate.model_copy(update={"rerank_score": score, "rerank_version": self.version})
            )
        return sorted(
            scored,
            key=lambda candidate: (
                -(candidate.rerank_score or 0.0),
                -candidate.recall_score,
                candidate.offer.offer_id,
            ),
        )[:limit]
