"""词法检索核心：中英文分词 + BM25（方案 §13.4 sparse 通道 / §13.7 本地降级）。

- 分词：拉丁词（含数字/连字符）作为一个 token；CJK 连续片段按二元组切分，
  兼顾中文商品标题的检索稳定性，不引入外部分词依赖。
- ``Bm25Index`` 在商品快照上构建倒排索引；``query_sparse_vector`` 供 Milvus
  sparse 通道复用同一 tokenizer（保证 sparse 与本地降级语义一致）。
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable

_LATIN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-\./]*")
_CJK_RE = re.compile(r"[一-鿿㐀-䶿]+")


def token_id(token: str) -> int:
    """token → 稳定 64 位整数 ID。

    Milvus ``SPARSE_FLOAT_VECTOR`` 的键必须是整数；这里用 SHA-256 截断生成
    确定性 ID，索引侧与查询侧共用同一映射，无需共享词表。
    """
    return int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:8], "big")


def tokenize(text: str) -> list[str]:
    """把检索文本切成 token：拉丁词原样保留，CJK 连续片段切成二元组。"""
    tokens: list[str] = []
    for m in _LATIN_RE.finditer(text):
        tokens.append(m.group(0).lower())
    for run in _CJK_RE.findall(text):
        chars = list(run)
        if len(chars) == 1:
            tokens.append(chars[0])
        else:
            tokens.extend(f"{chars[i]}{chars[i + 1]}" for i in range(len(chars) - 1))
    return tokens


def query_sparse_vector(text: str) -> dict[int, float]:
    """查询侧 sparse 向量：token id → 词频（与索引工具共用 token_id 映射）。"""
    return {token_id(t): float(freq) for t, freq in Counter(tokenize(text)).items()}


class Bm25Index:
    """纯 Python BM25 倒排索引（k1=1.5, b=0.75）。用于本地词法降级。"""

    def __init__(self, documents: Iterable[str]) -> None:
        doc_tokens = [tokenize(doc) for doc in documents]
        self._documents = list(documents)
        self._doc_tokens = doc_tokens
        self._doc_len = [len(t) for t in doc_tokens]
        self._avgdl = sum(self._doc_len) / max(1, len(self._doc_len))
        self._n_docs = len(self._doc_len)
        self._df: dict[str, int] = defaultdict(int)
        for tokens in doc_tokens:
            for term in set(tokens):
                self._df[term] += 1

    def score(self, query_tokens: list[str]) -> list[tuple[int, float]]:
        """返回 [(doc_index, bm25_score)]，按分数降序。"""
        k1, b = 1.5, 0.75
        n_docs = self._n_docs
        idf: dict[str, float] = {}
        for term in set(query_tokens):
            df = self._df.get(term, 0)
            idf[term] = math.log(1 + (n_docs - df + 0.5) / (df + 0.5)) if df else 0.0
        scores: list[float] = [0.0] * n_docs
        term_freqs: list[Counter[str]] = [Counter(t) for t in self._doc_tokens]
        for term in set(query_tokens):
            w = idf.get(term, 0.0)
            if not w:
                continue
            for i, tf in enumerate(term_freqs):
                if term in tf:
                    denom = tf[term] + k1 * (1 - b + b * self._doc_len[i] / self._avgdl)
                    scores[i] += w * (tf[term] * (k1 + 1)) / denom
        ranked = sorted(range(n_docs), key=lambda i: scores[i], reverse=True)
        return [(i, scores[i]) for i in ranked if scores[i] > 0]
