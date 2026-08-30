"""shijiajing-build-eval：Phase 1 provisional 数据集构建 CLI（方案 §5–§9）。

子命令：

- ``simulate``：生成确定性模拟 workspace（本环境适配：用户授权模拟数据集）。
- ``collect``：按 sources.jsonl 采集真实商品页 → captures + 本地证据（§5.2）。
- ``prepare``：脱敏 + Agent Gold 标签 → offers_snapshot / offer_labels /
  asset_inventory（§6）。
- ``generate``：六类数据集 + manifest（§8）。
- ``validate``：§9 全部数据校验（任何一项失败退出非零）。

退出码：0 = 成功；1 = 校验失败；2 = 配置/输入错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shijiajing_agent.config import load_settings
from shijiajing_agent.contracts import ImageContentType, Offer, SellerType, sha256_hex
from shijiajing_agent.domain.taxonomy import Taxonomy, load_taxonomy
from shijiajing_agent.eval_data import (
    DATASET_ID_SIM,
    AssetInventoryEntry,
    AssetMapEntry,
    CaptureRecord,
    DatasetManifest,
    GoldLabelDraft,
    HmacKeyStore,
    OfferGoldLabel,
    SourceSpec,
    compute_files_sha256,
    load_asset_map,
    load_jsonl_rows,
    mask_id,
    sha256_hmac_url,
    stable_split,
    write_jsonl,
)
from shijiajing_agent.eval_freeze import (
    freeze_dataset,
    load_adjudication_record,
    validate_frozen_dataset_metadata,
)
from shijiajing_agent.evals import (
    DATASET_FILES,
    load_all_datasets,
)
from shijiajing_agent.tools.cli_support import configure_utf8_output

_EXIT_OK = 0
_EXIT_VALIDATE_FAIL = 1
_EXIT_CONFIG_ERROR = 2

_MAX_HTML_BYTES = 5 * 1024 * 1024  # 5 MiB（§5.2）
_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MiB
_TIMEOUT_SECONDS = 15.0


# ---------------------------------------------------------------------------
# collect：真实采集（§5.2）
# ---------------------------------------------------------------------------


def _as_dict(value: Any) -> dict[str, Any]:
    """不可信 JSON 值的类型窄化（strict 模式：Any → dict[str, Any]）。"""
    from typing import cast

    return cast(dict[str, Any], value)


def parse_jsonld(raw: bytes) -> dict[str, Any] | None:
    """优先 JSON-LD/schema.org 结构化解析（§5.2）。"""
    text = raw.decode("utf-8", errors="replace")
    pattern = re.compile(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S
    )
    for m in pattern.finditer(text):
        try:
            data: Any = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        candidates: list[Any] = data if isinstance(data, list) else [data]  # type: ignore[reportUnknownVariableType]
        for item in candidates:
            if isinstance(item, dict) and item.get("@type") == "Product":  # type: ignore[reportUnknownMemberType]
                return _as_dict(item)
    return None


def parse_jd_item_page(raw: bytes) -> dict[str, Any] | None:
    """京东移动详情页内嵌 JSON 契约（window._itemOnly.item，文档化数据契约）。

    京东商品页无 JSON-LD；移动版页面内嵌 item JSON（skuName/brandName/image）。
    只解析该内嵌 JSON 契约，不做 HTML 字符串猜字段路径。
    """
    text = raw.decode("gbk", errors="replace")
    m = re.search(r"_itemOnly = \(\{(.*?)\n\}\);?", text, re.S)
    if not m:
        return None
    try:
        data: Any = json.loads("{" + m.group(1) + "}")
    except json.JSONDecodeError:
        return None
    item = data.get("item")
    if isinstance(item, dict):
        return _as_dict(item)
    return None


def _num(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _coerce_seller(value: Any) -> SellerType:
    if isinstance(value, SellerType):
        return value
    try:
        return SellerType(str(value)) if value else SellerType.UNKNOWN
    except ValueError:
        return SellerType.UNKNOWN


def extract_offer_fields(page: dict[str, Any], source: SourceSpec) -> dict[str, Any] | None:
    """JSON-LD Product / JD item → 提取结果（与模拟证据同构）。无结构化字段返回 None。"""
    title: Any = page.get("name") or page.get("skuName")
    if not title:
        return None
    brand_raw: Any = page.get("brand")
    brand: Any = _as_dict(brand_raw).get("name") if isinstance(brand_raw, dict) else brand_raw
    offers: Any = page.get("offers")
    price: float | None = None
    if isinstance(offers, dict):
        price = _num(_as_dict(offers).get("price"))
    elif isinstance(offers, list) and offers:
        price = _num(_as_dict(offers[0]).get("price"))
    images: Any = page.get("image") or page.get("images") or []
    if isinstance(images, str):
        images = [images]
    if isinstance(images, list):
        images = [i for i in images if isinstance(i, str)]  # type: ignore[reportUnknownVariableType]
    return {
        "extraction": "jsonld" if page.get("@type") == "Product" else "jd_item",
        "source_id": source.source_id,
        "offer": {
            "platform": source.platform,
            "source_product_id": page.get("skuId") or page.get("productID"),
            "source_updated_at": None,
            "title": str(title),
            "category_id": source.category_id,
            "brand": str(brand) if brand else None,
            "model": page.get("model"),
            "identity_attributes": {},
            "variant_attributes": {},
            "descriptive_attributes": {},
            "price": price,
            "original_price": None,
            "shipping_fee": None,
            "coupon_amount": None,
            "currency": "CNY",
            "shop_id": None,
            "shop_name": None,
            "seller_type": None,
            "rating": None,
            "sales": None,
            "review_count": None,
            "delivery_days": None,
        },
        "images": images,
    }


def _robots_allows(url: str, transport: Any, cache: dict[str, bool]) -> bool:
    """简单 robots.txt 检查：尊重 Disallow（§5.2 禁止绕过 robots 限制）。"""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.netloc
    if host in cache:
        return cache[host]
    try:
        req = _request("https", host, "/robots.txt", transport)
        if req is None:
            cache[host] = True
            return True
        body = req.read(_MAX_HTML_BYTES).decode("utf-8", errors="replace")
        allowed = True
        path = parsed.path or "/"
        for line in body.splitlines():
            if line.lower().startswith("disallow:"):
                rule = line.split(":", 1)[1].strip()
                if rule and path.startswith(rule.rstrip("*")):
                    allowed = False
        cache[host] = allowed
        return allowed
    except Exception:
        cache[host] = True
        return True


def _request(scheme: str, host: str, path: str, transport: Any) -> Any | None:
    import httpx

    client = httpx.Client(transport=transport) if transport is not None else httpx.Client()
    try:
        resp = client.get(
            f"{scheme}://{host}{path}",
            timeout=_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": "shijiajing-eval-collector/0.1 (research)"},
        )
        return resp
    except Exception:
        return None
    finally:
        client.close()


def collect_sources(
    sources_path: Path,
    workspace: Path,
    *,
    as_of: str,
    transport: Any = None,
) -> tuple[int, Counter[str]]:
    """执行采集（§5.2）。transport 用于 contract 测试注入录制响应。"""
    rows = load_jsonl_rows(sources_path, SourceSpec)
    key = HmacKeyStore(workspace / "keys" / "hmac.key")
    pages_dir = workspace / "raw" / "pages"
    images_dir = workspace / "raw" / "images"
    pages_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    captures: list[CaptureRecord] = []
    asset_map: list[AssetMapEntry] = []
    asset_bindings: list[dict[str, str]] = []
    robots_cache: dict[str, bool] = {}
    status_counts: Counter[str] = Counter()

    from urllib.parse import urlparse

    for source in rows:
        parsed = urlparse(source.url)
        capture_id = f"cap:{source.source_id}"
        if not _robots_allows(source.url, transport, robots_cache):
            captures.append(
                CaptureRecord(
                    capture_id=capture_id,
                    source_id=source.source_id,
                    status="unavailable",
                    error_message="robots.txt 禁止抓取",
                )
            )
            status_counts["unavailable"] += 1
            continue
        last_error = "请求失败"
        try:
            resp = _request(parsed.scheme, parsed.netloc, parsed.path or "/", transport)
        except Exception as exc:
            resp = None
            last_error = str(exc)
        if resp is None:
            captures.append(
                CaptureRecord(
                    capture_id=capture_id,
                    source_id=source.source_id,
                    status="unavailable",
                    error_message=last_error,
                )
            )
            status_counts["unavailable"] += 1
            continue
        final_url = str(resp.url)
        body = resp.content
        if len(body) > _MAX_HTML_BYTES:
            captures.append(
                CaptureRecord(
                    capture_id=capture_id,
                    source_id=source.source_id,
                    status="invalid",
                    http_status=resp.status_code,
                    final_url=final_url,
                    error_message="响应超过 5 MiB 上限",
                )
            )
            status_counts["invalid"] += 1
            continue
        page = parse_jsonld(body) or parse_jd_item_page(body)
        if page is None:
            captures.append(
                CaptureRecord(
                    capture_id=capture_id,
                    source_id=source.source_id,
                    status="manual_required",
                    http_status=resp.status_code,
                    final_url=final_url,
                    error_message="无 JSON-LD/内嵌 JSON 结构化字段",
                )
            )
            status_counts["manual_required"] += 1
            continue
        extracted = extract_offer_fields(page, source)
        if extracted is None:
            captures.append(
                CaptureRecord(
                    capture_id=capture_id,
                    source_id=source.source_id,
                    status="manual_required",
                    http_status=resp.status_code,
                    final_url=final_url,
                    error_message="结构化字段不完整（无标题）",
                )
            )
            status_counts["manual_required"] += 1
            continue
        evidence_bytes = json.dumps(extracted, ensure_ascii=False, indent=2).encode("utf-8")
        evidence_path = f"raw/pages/{capture_id.replace(':', '_')}.json"
        (workspace / evidence_path).write_bytes(evidence_bytes)
        captures.append(
            CaptureRecord(
                capture_id=capture_id,
                source_id=source.source_id,
                status="ok",
                http_status=resp.status_code,
                fetched_at=as_of,
                final_url=final_url,
                final_url_hmac=key.mask(final_url),
                content_sha256=sha256_hex(evidence_bytes),
                content_type="application/json",
                size_bytes=len(evidence_bytes),
                evidence_path=evidence_path,
                error_message=None,
            )
        )
        status_counts["ok"] += 1
        # 图片资产下载（失败不阻断采集）
        for i, image_url in enumerate(extracted.get("images") or []):
            try:
                img = _request(*_split_url(image_url), transport)
                if img is None or len(img.content) > _MAX_IMAGE_BYTES:
                    continue
                asset_id = f"ast:{source.source_id}:{i}"
                safe_id = asset_id.replace(":", "_")
                ext = "png" if img.headers.get("content-type", "").endswith("png") else "jpg"
                data = img.content
                (images_dir / f"{safe_id}.{ext}").write_bytes(data)
                asset_map.append(
                    AssetMapEntry(
                        asset_id=asset_id,
                        content_type=ImageContentType(
                            "image/png" if ext == "png" else "image/jpeg"
                        ),
                        sha256=sha256_hex(data),
                        width=0,
                        height=0,
                        local_path=f"{safe_id}.{ext}",
                        source_content_hash=sha256_hex(data),
                    )
                )
                asset_bindings.append({"asset_id": asset_id, "source_id": source.source_id})
            except Exception:
                continue

    write_jsonl(workspace / "captures.jsonl", captures, sort_key="source_id")
    _write_jsonl(
        workspace / "asset_map.jsonl",
        [e.model_dump() for e in asset_map],
        "asset_id",
    )
    _write_jsonl(workspace / "asset_bindings.jsonl", asset_bindings, "asset_id")
    return len(rows), status_counts


def _split_url(url: str) -> tuple[str, str, str]:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.scheme, parsed.netloc, parsed.path or "/"


# ---------------------------------------------------------------------------
# prepare：脱敏 + Gold 标签（§6）
# ---------------------------------------------------------------------------


def prepare_offers(
    workspace: Path,
    out_dir: Path,
    *,
    dataset_id: str,
    as_of: str,
    taxonomy: Taxonomy,
) -> dict[str, int]:
    """captures + 证据 + gold draft → offers_snapshot / offer_labels / asset_inventory。

    确定性：相同输入 + 相同密钥 + 相同 as_of 输出字节一致；输出按 id 排序（§6.1）。
    """
    key = HmacKeyStore(workspace / "keys" / "hmac.key")
    captures = [
        c for c in load_jsonl_rows(workspace / "captures.jsonl", CaptureRecord) if c.status == "ok"
    ]
    drafts = {
        d.source_id: d
        for d in load_jsonl_rows(workspace / "gold_labels_draft.jsonl", GoldLabelDraft)
    }
    asset_map = load_asset_map(workspace / "asset_map.jsonl")

    offers: list[Offer] = []
    labels: list[OfferGoldLabel] = []
    source_map: list[dict[str, str]] = []
    seen_offer_ids: set[str] = set()

    for capture in sorted(captures, key=lambda c: c.source_id):
        assert capture.evidence_path is not None and capture.content_sha256 is not None
        evidence = json.loads((workspace / capture.evidence_path).read_text(encoding="utf-8"))
        of: dict[str, Any] = evidence.get("offer") or {}
        platform = str(of.get("platform") or "")
        source_product_id = of.get("source_product_id")
        dedup_key = (
            f"{platform}|{source_product_id or sha256_hmac_url(key, capture.final_url or '')}"
        )
        offer_id = mask_id("off:", key, dedup_key)
        if offer_id in seen_offer_ids:
            continue
        seen_offer_ids.add(offer_id)

        shop_id_raw = of.get("shop_id")
        offer = Offer(
            offer_id=offer_id,
            platform=platform,
            source_product_id=(
                mask_id("spid:", key, str(source_product_id)) if source_product_id else None
            ),
            source_updated_at=of.get("source_updated_at"),
            title=str(of.get("title") or ""),
            category_id=of.get("category_id") or None,
            brand=of.get("brand") or None,
            model=of.get("model") or None,
            same_item_key=of.get("same_item_key") or None,
            sku_key=of.get("sku_key") or None,
            identity_attributes=dict(of.get("identity_attributes") or {}),
            variant_attributes=dict(of.get("variant_attributes") or {}),
            descriptive_attributes=dict(of.get("descriptive_attributes") or {}),
            price=_num(of.get("price")),
            original_price=_num(of.get("original_price")),
            shipping_fee=_num(of.get("shipping_fee")),
            coupon_amount=_num(of.get("coupon_amount")),
            currency=str(of.get("currency") or "CNY"),
            shop_id=mask_id("shop:", key, str(shop_id_raw)) if shop_id_raw else None,
            shop_name=of.get("shop_name") or None,
            seller_type=_coerce_seller(of.get("seller_type")),
            rating=_num(of.get("rating")),
            sales=_num(of.get("sales")),
            review_count=_num(of.get("review_count")),
            delivery_days=_num(of.get("delivery_days")),
            source_payload_ref=f"sha256:{capture.content_sha256}",
        )
        draft = drafts.get(capture.source_id)
        if draft is None:
            raise ValueError(f"缺失 Gold 标注草稿: {capture.source_id}")
        labels.append(
            OfferGoldLabel(
                offer_id=offer_id,
                gold_spu_id=draft.gold_spu_id,
                gold_sku_id=draft.gold_sku_id,
                category_id=str(of.get("category_id") or draft.gold_spu_id),
                identity_attributes=dict(draft.identity_attributes),
                variant_attributes=dict(draft.variant_attributes),
                evidence_refs=list(draft.evidence_refs),
                label_source="agent",
                label_rationale=draft.label_rationale,
                split=stable_split(dataset_id, draft.gold_spu_id),
            )
        )
        offers.append(offer)
        source_map.append({"offer_id": offer_id, "source_id": capture.source_id})

    # 资产清单：校验本地文件 SHA-256 后写入 inventory（§6.1：只提交摘要，不提交二进制）
    inventory: list[AssetInventoryEntry] = []
    for entry in sorted(asset_map.values(), key=lambda e: e.asset_id):
        path = workspace / "raw" / "images" / entry.local_path
        if not path.is_file():
            raise ValueError(f"资产文件缺失: {entry.local_path}")
        if sha256_hex(path.read_bytes()) != entry.sha256:
            raise ValueError(f"资产摘要不一致: {entry.asset_id}")
        inventory.append(
            AssetInventoryEntry(
                asset_id=entry.asset_id,
                content_type=entry.content_type,
                sha256=entry.sha256,
                width=entry.width,
                height=entry.height,
                source_content_hash=entry.source_content_hash,
            )
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "offers_snapshot.jsonl", offers, sort_key="offer_id")
    write_jsonl(out_dir / "offer_labels.jsonl", labels, sort_key="offer_id")
    write_jsonl(out_dir / "asset_inventory.jsonl", inventory, sort_key="asset_id")
    _write_jsonl(workspace / "offer_source_map.jsonl", source_map, "offer_id")
    return {
        "offer_count": len(offers),
        "spu_count": len({label.gold_spu_id for label in labels}),
        "asset_count": len(inventory),
    }


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, rows: list[dict[str, Any]], sort_key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in sorted(rows, key=lambda r: r[sort_key]):
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# validate（§9）
# ---------------------------------------------------------------------------


def validate_datasets(
    datasets_dir: Path,
    *,
    assets_dir: Path | None = None,
    workspace: Path | None = None,
    taxonomy: Taxonomy,
) -> list[str]:
    """§9 全部校验。返回错误列表；空列表表示通过。"""
    errors: list[str] = []
    if not datasets_dir.is_dir():
        return [f"数据集目录不存在: {datasets_dir}"]

    # 1) 全部 JSONL 通过 Pydantic 契约（extra=forbid）
    manifest_path = datasets_dir / "manifest.json"
    if not manifest_path.exists():
        errors.append("manifest.json 缺失")
        return errors
    try:
        manifest = DatasetManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"manifest.json 校验失败: {exc}"]

    datasets = load_all_datasets(datasets_dir)
    try:
        offers = [
            Offer.model_validate(r)
            for r in load_jsonl_rows(datasets_dir / "offers_snapshot.jsonl", Offer)
        ]
        labels = [
            OfferGoldLabel.model_validate(r)
            for r in load_jsonl_rows(datasets_dir / "offer_labels.jsonl", OfferGoldLabel)
        ]
        inventory = [
            AssetInventoryEntry.model_validate(r)
            for r in load_jsonl_rows(datasets_dir / "asset_inventory.jsonl", AssetInventoryEntry)
        ]
    except Exception as exc:
        return [f"数据文件校验失败: {exc}"]

    # 2) 行数（§4.2）
    expected_rows = {
        "recognition": 300,
        "intent": 300,
        "retrieval": 150,
        "same_item": 600,
        "ranking": 90,
        "end_to_end": 120,
    }
    for kind, expected in expected_rows.items():
        actual = len(datasets.get(kind) or [])
        if actual != expected:
            errors.append(f"{kind}: 期望 {expected} 行，实际 {actual}")

    # §4.1 规模
    expected_offers = {"headphone": 340, "sneaker": 340, "hair_dryer": 320}
    expected_spus = {"headphone": 70, "sneaker": 70, "hair_dryer": 60}
    cat_offers: Counter[str] = Counter()
    for o in offers:
        if o.category_id:
            cat_offers[o.category_id] += 1
    for cat, expected in expected_offers.items():
        if cat_offers.get(cat, 0) != expected:
            errors.append(f"offer 数 {cat}: 期望 {expected}，实际 {cat_offers.get(cat, 0)}")
    spu_by_cat: dict[str, set[str]] = defaultdict(set)
    for label in labels:
        spu_by_cat[label.category_id].add(label.gold_spu_id)
    for cat, expected in expected_spus.items():
        if len(spu_by_cat.get(cat, set())) != expected:
            errors.append(f"SPU 数 {cat}: 期望 {expected}，实际 {len(spu_by_cat.get(cat, set()))}")
    if len(offers) != 1000:
        errors.append(f"offer 总数: 期望 1000，实际 {len(offers)}")
    if len(inventory) != 300:
        errors.append(f"资产总数: 期望 300，实际 {len(inventory)}")

    # 3) ID 全局唯一
    offer_ids = [o.offer_id for o in offers]
    if len(set(offer_ids)) != len(offer_ids):
        errors.append("Offer ID 存在重复")
    all_sample_ids: list[str] = []
    for kind, rows in datasets.items():
        typed_rows = [cast_any(r) for r in rows]
        all_sample_ids.extend(str(r.id) for r in typed_rows)
        ids = [str(r.id) for r in typed_rows]
        if len(set(ids)) != len(ids):
            errors.append(f"{kind}: sample ID 存在重复")
    if len(set(all_sample_ids)) != len(all_sample_ids):
        errors.append("跨数据集 sample ID 存在重复")
    asset_ids = [a.asset_id for a in inventory]
    if len(set(asset_ids)) != len(asset_ids):
        errors.append("asset ID 存在重复")

    # 4) sample source refs 可解析
    capture_source_ids: set[str] = set()
    if workspace is not None and (workspace / "captures.jsonl").exists():
        capture_source_ids = {
            c.source_id for c in load_jsonl_rows(workspace / "captures.jsonl", CaptureRecord)
        }
    manifest_source_ids = set(manifest.source_ids)
    for kind, rows in datasets.items():
        for row in rows:
            typed = cast_any(row)
            meta = getattr(typed, "meta", None)
            if meta is None:
                errors.append(f"{kind} {typed.id}: provisional 数据要求 meta 必填")
                continue
            for ref in meta.source_refs:
                if ref not in manifest_source_ids and ref not in capture_source_ids:
                    errors.append(f"{kind} {typed.id}: source ref 无法解析: {ref}")

    # 5) 图片 SHA-256 与本地文件一致
    if assets_dir is not None:
        asset_map = load_asset_map(assets_dir.parent / "asset_map.jsonl")
        inventory_by_id = {a.asset_id: a for a in inventory}
        for entry in asset_map.values():
            inv = inventory_by_id.get(entry.asset_id)
            if inv is None:
                errors.append(f"asset_inventory 缺少资产: {entry.asset_id}")
                continue
            path = assets_dir / entry.local_path
            if not path.is_file():
                errors.append(f"资产文件缺失: {entry.local_path}")
                continue
            if sha256_hex(path.read_bytes()) != entry.sha256:
                errors.append(f"资产摘要不一致: {entry.asset_id}")

    # 6) Gold SPU 不跨 split（SPU 泄漏检查，§4.3）
    spu_splits: dict[str, set[str]] = defaultdict(set)
    for label in labels:
        spu_splits[label.gold_spu_id].add(label.split)
    leaked = [spu for spu, splits in spu_splits.items() if len(splits) > 1]
    if leaked:
        errors.append(f"Gold SPU 跨 split（泄漏）: {sorted(leaked)[:5]}")

    # 7) same-item 标签一致性
    label_by_offer = {label.offer_id: label for label in labels}
    for row in datasets.get("same_item") or []:
        pair = cast_any(row)
        a: dict[str, Any] = pair.offer_a
        b: dict[str, Any] = pair.offer_b
        la, lb = label_by_offer.get(a["offer_id"]), label_by_offer.get(b["offer_id"])
        if pair.same_sku and not pair.same_spu:
            errors.append(f"same_item {pair.id}: same_sku 但 same_spu=false（矛盾）")
        if la is None or lb is None:
            errors.append(f"same_item {pair.id}: Offer 不在 Gold 目录")
            continue
        if pair.same_sku:
            if la.gold_sku_id != lb.gold_sku_id:
                errors.append(f"same_item {pair.id}: same-SKU 对 Gold SKU 不一致")
            if la.gold_spu_id != lb.gold_spu_id:
                errors.append(f"same_item {pair.id}: same-SKU 对 Gold SPU 不一致")
        if pair.same_spu and not pair.same_sku:
            if la.gold_spu_id != lb.gold_spu_id:
                errors.append(f"same_item {pair.id}: 同 SPU 对 Gold SPU 不一致")
            if la.gold_sku_id == lb.gold_sku_id:
                errors.append(f"same_item {pair.id}: 同 SPU 不同 SKU 对 Gold SKU 相同")
        # §4.3：负样本对同 split
        if not pair.same_spu and la.split != lb.split:
            errors.append(f"same_item {pair.id}: 负样本对跨 split")

    # 8) Gold 标签不得泄漏到 Offer.same_item_key / sku_key
    gold_spu_ids = {label.gold_spu_id for label in labels}
    gold_sku_ids = {label.gold_sku_id for label in labels}
    for o in offers:
        if o.same_item_key in gold_spu_ids:
            errors.append(f"offer {o.offer_id}: same_item_key 泄漏 Gold SPU")
        if o.sku_key in gold_sku_ids:
            errors.append(f"offer {o.offer_id}: sku_key 泄漏 Gold SKU")

    # 9) 所有 expected SPU/SKU ID 存在于 Gold 目录
    all_expected_spu: set[str] = set()
    all_expected_sku: set[str] = set()
    for row in datasets.get("retrieval") or []:
        ret = cast_any(row)
        all_expected_spu.update(ret.expected_spu_ids)
        all_expected_sku.update(ret.expected_sku_ids)
    for row in datasets.get("end_to_end") or []:
        wf = cast_any(row)
        all_expected_sku.update(wf.expected_sku_ids)
    missing_spu = all_expected_spu - gold_spu_ids
    missing_sku = all_expected_sku - gold_sku_ids
    if missing_spu:
        errors.append(f"expected SPU 不在 Gold 目录: {sorted(missing_spu)[:5]}")
    if missing_sku:
        errors.append(f"expected SKU 不在 Gold 目录: {sorted(missing_sku)[:5]}")

    # 10) taxonomy 键精确存在
    for label in labels:
        if taxonomy.get_category(label.category_id) is None:
            errors.append(f"标签分类不存在: {label.category_id}")
        for key in label.identity_attributes:
            if key not in taxonomy.identity_attributes(label.category_id):
                errors.append(f"标签 identity 属性键不存在: {label.category_id}.{key}")
        for key in label.variant_attributes:
            if key not in taxonomy.variant_attributes(label.category_id):
                errors.append(f"标签 variant 属性键不存在: {label.category_id}.{key}")
    for kind, rows in datasets.items():
        for row in rows:
            typed = cast_any(row)
            meta = getattr(typed, "meta", None)
            if meta is None:
                continue
            if taxonomy.get_category(meta.category_id) is None:
                errors.append(f"{kind} {typed.id}: meta 分类不存在: {meta.category_id}")

    # 11) manifest 统计一致（§9）
    actual_files = compute_files_sha256(datasets_dir)
    for filename, expected_sha in manifest.files.items():
        if actual_files.get(filename) != expected_sha:
            errors.append(f"文件摘要不一致: {filename}")
    if len(actual_files) != len(manifest.files):
        errors.append("manifest.files 与实际文件数量不一致")
    if manifest.trust_level == "provisional":
        if manifest.label_method != "agent_only":
            errors.append("provisional manifest label_method 必须为 agent_only")
        if manifest.gate_eligible:
            errors.append("provisional manifest gate_eligible 必须为 false")
    elif manifest.trust_level == "frozen":
        errors.extend(validate_frozen_dataset_metadata(datasets_dir, manifest))
        if manifest.label_method != "adjudicated":
            errors.append("frozen manifest label_method 必须为 adjudicated")
        if not manifest.gate_eligible:
            errors.append("frozen manifest gate_eligible 必须为 true")
        if any(label.label_source != "adjudicated" for label in labels):
            errors.append("frozen manifest 的 offer_labels 必须全部为 adjudicated")
        for kind, rows in datasets.items():
            for row in rows:
                meta = getattr(row, "meta", None)
                if meta is None or meta.label_source != "adjudicated":
                    row_id = row.model_dump(mode="json").get("id", "<unknown>")
                    errors.append(f"frozen {kind} {row_id}: meta.label_source 必须为 adjudicated")
    if manifest.offer_count != len(offers):
        errors.append("manifest.offer_count 与实际不一致")
    if manifest.spu_count != len(spu_splits):
        errors.append("manifest.spu_count 与实际不一致")
    if manifest.asset_count != len(inventory):
        errors.append("manifest.asset_count 与实际不一致")
    actual_by_split = Counter(label.split for label in labels)
    if dict(actual_by_split) != manifest.counts_by_split:
        errors.append("manifest.counts_by_split 与实际不一致")
    actual_by_platform = Counter(o.platform for o in offers)
    if dict(actual_by_platform) != manifest.counts_by_platform:
        errors.append("manifest.counts_by_platform 与实际不一致")
    if dict(cat_offers) != manifest.categories:
        errors.append("manifest.categories 与实际不一致")
    for filename, expected in manifest.counts_by_file.items():
        if filename in DATASET_FILES:
            kind = next(k for k, v in DATASET_FILES.items() if v[0] == filename)
            actual = len(datasets.get(kind) or [])
            if actual != expected:
                errors.append(f"manifest.counts_by_file[{filename}] 与实际不一致")

    # 12) 平台覆盖约束（§4.1）
    cat_platform: dict[str, set[str]] = defaultdict(set)
    for o in offers:
        if o.category_id:
            cat_platform[o.category_id].add(o.platform)
    for cat, platforms in cat_platform.items():
        if len(platforms) < 2:
            errors.append(f"{cat}: 平台覆盖不足 2 个")
    for cat, offers_of_cat in _offers_by_cat(offers).items():
        total = len(offers_of_cat)
        for platform, count in Counter(o.platform for o in offers_of_cat).items():
            if total and count / total > 0.6:
                errors.append(f"{cat}/{platform}: 平台占比 {count / total:.1%} 超过 60%")
    for label in labels:
        spu_offers = [
            o
            for o in offers
            if o.offer_id in label_by_offer
            and label_by_offer[o.offer_id].gold_spu_id == label.gold_spu_id
        ]
        if len(spu_offers) < 3:
            errors.append(f"SPU {label.gold_spu_id}: Offer 数少于 3")
        platforms = {o.platform for o in spu_offers}
        if len(platforms) < 2:
            errors.append(f"SPU {label.gold_spu_id}: 平台覆盖不足 2 个")

    return errors


def cast_any(value: Any) -> Any:
    """strict 模式下数据集行（BaseModel 子类）的类型窄化辅助。"""
    return value


def _offers_by_cat(offers: list[Offer]) -> dict[str, list[Offer]]:
    out: dict[str, list[Offer]] = defaultdict(list)
    for o in offers:
        if o.category_id:
            out[o.category_id].append(o)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="识价镜 Agent provisional 数据集构建")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sim = sub.add_parser("simulate", help="生成确定性模拟 workspace（用户授权适配）")
    p_sim.add_argument("--workspace", type=Path, required=True)
    p_sim.add_argument("--dataset-id", default=DATASET_ID_SIM)
    p_sim.add_argument("--as-of", required=True, help="ISO-8601 UTC")

    p_collect = sub.add_parser("collect", help="按 sources.jsonl 采集真实商品页（§5）")
    p_collect.add_argument("--sources", type=Path, required=True)
    p_collect.add_argument("--workspace", type=Path, required=True)
    p_collect.add_argument("--as-of", default=None, help="ISO-8601 UTC（默认当前时间）")

    p_prepare = sub.add_parser("prepare", help="脱敏 + Gold 标签（§6）")
    p_prepare.add_argument("--workspace", type=Path, required=True)
    p_prepare.add_argument("--out", type=Path, required=True)
    p_prepare.add_argument("--dataset-id", default=DATASET_ID_SIM)
    p_prepare.add_argument("--as-of", required=True, help="ISO-8601 UTC")

    p_gen = sub.add_parser("generate", help="六类数据集 + manifest（§8）")
    p_gen.add_argument("--snapshot", type=Path, required=True)
    p_gen.add_argument("--labels", type=Path, required=True)
    p_gen.add_argument("--assets", type=Path, required=True)
    p_gen.add_argument("--asset-map", type=Path, required=True)
    p_gen.add_argument("--asset-bindings", type=Path, required=True)
    p_gen.add_argument("--offer-source-map", type=Path, required=True)
    p_gen.add_argument("--assets-dir", type=Path, required=True)
    p_gen.add_argument("--out", type=Path, required=True)
    p_gen.add_argument("--dataset-id", default=DATASET_ID_SIM)
    p_gen.add_argument("--dataset-version", default="1.0.0")
    p_gen.add_argument("--as-of", required=True, help="ISO-8601 UTC")
    p_gen.add_argument("--created-at", default=None, help="ISO-8601 UTC（默认同 as-of）")
    p_gen.add_argument(
        "--retrieval-strategy",
        type=Path,
        default=None,
        help="可选策略比较夹具 JSONL；正式性能门禁必须提供并随 manifest 冻结",
    )

    p_freeze = sub.add_parser("freeze", help="人工仲裁后复制并冻结数据集")
    p_freeze.add_argument("--datasets-dir", type=Path, required=True)
    p_freeze.add_argument("--out", type=Path, required=True)
    p_freeze.add_argument("--adjudication-record", type=Path, required=True)
    p_freeze.add_argument("--assets-dir", type=Path, default=None)
    p_freeze.add_argument("--workspace", type=Path, default=None)

    p_val = sub.add_parser("validate", help="§9 数据校验")
    p_val.add_argument("--datasets-dir", type=Path, required=True)
    p_val.add_argument("--assets-dir", type=Path, default=None)
    p_val.add_argument("--workspace", type=Path, default=None)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = _parse_args(argv)
    settings = load_settings()
    try:
        taxonomy = load_taxonomy(settings.taxonomy_path_resolved)
    except Exception as exc:
        print(f"taxonomy 加载失败：{exc}", file=sys.stderr)
        return _EXIT_CONFIG_ERROR

    if args.command == "simulate":
        from shijiajing_agent.eval_simulate import write_simulated_workspace

        try:
            counts = write_simulated_workspace(
                args.workspace, dataset_id=args.dataset_id, as_of=args.as_of
            )
        except Exception as exc:
            print(f"simulate 失败：{exc}", file=sys.stderr)
            return _EXIT_CONFIG_ERROR
        print(
            f"模拟 workspace 已生成：{args.workspace} "
            f"(offers={counts['offer_count']}, spu={counts['spu_count']}, "
            f"assets={counts['asset_count']}, sources={counts['source_count']})"
        )
        return _EXIT_OK

    if args.command == "collect":
        if not args.sources.is_file():
            print(f"sources 文件不存在：{args.sources}", file=sys.stderr)
            return _EXIT_CONFIG_ERROR
        as_of = args.as_of or datetime.now(UTC).isoformat(timespec="seconds")
        try:
            n, statuses = collect_sources(args.sources, args.workspace, as_of=as_of)
        except Exception as exc:
            print(f"collect 失败：{exc}", file=sys.stderr)
            return _EXIT_CONFIG_ERROR
        print(f"采集完成：{n} 个源，状态 {dict(statuses)}")
        return _EXIT_OK

    if args.command == "prepare":
        try:
            counts = prepare_offers(
                args.workspace,
                args.out,
                dataset_id=args.dataset_id,
                as_of=args.as_of,
                taxonomy=taxonomy,
            )
        except Exception as exc:
            print(f"prepare 失败：{exc}", file=sys.stderr)
            return _EXIT_CONFIG_ERROR
        print(
            f"脱敏完成：{counts['offer_count']} Offer / {counts['spu_count']} SPU / "
            f"{counts['asset_count']} 资产 → {args.out}"
        )
        return _EXIT_OK

    if args.command == "generate":
        from shijiajing_agent.eval_generate import generate_datasets

        created_at = args.created_at or args.as_of
        try:
            manifest = generate_datasets(
                args.out,
                snapshot_path=args.snapshot,
                labels_path=args.labels,
                assets_path=args.assets,
                asset_map_path=args.asset_map,
                asset_bindings_path=args.asset_bindings,
                offer_source_map_path=args.offer_source_map,
                assets_dir=args.assets_dir,
                dataset_id=args.dataset_id,
                dataset_version=args.dataset_version,
                as_of=args.as_of,
                created_at=created_at,
                taxonomy=taxonomy,
                retrieval_strategy_path=args.retrieval_strategy,
            )
        except Exception as exc:
            print(f"generate 失败：{exc}", file=sys.stderr)
            return _EXIT_CONFIG_ERROR
        print(f"数据集已生成：{args.out}（dataset_id={manifest.dataset_id}）")
        return _EXIT_OK

    if args.command == "freeze":
        if not args.datasets_dir.is_dir():
            print(f"数据集目录不存在：{args.datasets_dir}", file=sys.stderr)
            return _EXIT_CONFIG_ERROR
        validation_errors = validate_datasets(
            args.datasets_dir,
            assets_dir=args.assets_dir,
            workspace=args.workspace,
            taxonomy=taxonomy,
        )
        if validation_errors:
            print(f"冻结前数据校验失败：{len(validation_errors)} 项错误", file=sys.stderr)
            for error in validation_errors[:50]:
                print(f"  - {error}", file=sys.stderr)
            return _EXIT_VALIDATE_FAIL
        try:
            record = load_adjudication_record(args.adjudication_record)
            manifest = freeze_dataset(args.datasets_dir, args.out, record)
        except (OSError, ValueError) as exc:
            print(f"freeze 失败：{exc}", file=sys.stderr)
            return _EXIT_CONFIG_ERROR
        print(f"数据集已冻结：{args.out}（dataset_id={manifest.dataset_id}）")
        return _EXIT_OK

    if args.command == "validate":
        if not args.datasets_dir.is_dir():
            print(f"数据集目录不存在：{args.datasets_dir}", file=sys.stderr)
            return _EXIT_CONFIG_ERROR
        errors = validate_datasets(
            args.datasets_dir,
            assets_dir=args.assets_dir,
            workspace=args.workspace,
            taxonomy=taxonomy,
        )
        if errors:
            print(f"数据校验失败：{len(errors)} 项错误", file=sys.stderr)
            for error in errors[:50]:
                print(f"  - {error}", file=sys.stderr)
            if len(errors) > 50:
                print(f"  ... 共 {len(errors)} 项", file=sys.stderr)
            return _EXIT_VALIDATE_FAIL
        print("✅ 数据校验全部通过")
        return _EXIT_OK

    print(f"未知子命令：{args.command}", file=sys.stderr)
    return _EXIT_CONFIG_ERROR


if __name__ == "__main__":
    sys.exit(main())
