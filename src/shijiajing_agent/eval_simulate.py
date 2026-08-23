"""确定性模拟数据生成器（Phase 1 适配，用户授权）。

背景：本环境无法匿名访问淘宝/拼多多，京东仅有已知商品 ID 的详情页可匿名访问，
且京东搜索/列表与搜索引擎均被反爬拦截，无法自动发现 1,000 个商品 URL。
用户明确授权"模拟数据集，不需要完全真实"（2026-08-21）。

本模块据此生成**确定性、可复现**的模拟证据与 Offer 数据，替代真实采集步骤，
并如实标注来源：

- 所有源 URL 使用保留域名 ``example.com``（RFC 2606，显然非真实页面）。
- sources.jsonl 的 notes 与 manifest.known_limitations 明确声明模拟来源。
- dataset_id 使用 ``shijiajing-provisional-sim-v1``（计划固定值带 real 后缀，
  本环境如实改为 sim）。
- 全部字段结构与分布符合计划 §4–§6 契约：SPU/SKU 结构、平台覆盖、拆分、
  脱敏、确定性（相同种子 + 相同 --as-of 输出字节一致）。

生成器是纯函数：相同 ``dataset_id + as_of`` 输入永远产出相同输出。
"""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from shijiajing_agent.contracts import ImageContentType, SellerType, sha256_hex
from shijiajing_agent.eval_data import (
    AssetMapEntry,
    CaptureRecord,
    GoldLabelDraft,
    HmacKeyStore,
    SourceSpec,
)

# ---------------------------------------------------------------------------
# 确定性随机源（不依赖进程随机 hash；相同种子永远相同输出）
# ---------------------------------------------------------------------------


class SimRng:
    def __init__(self, seed: bytes) -> None:
        self._state = hashlib.sha256(seed).digest()

    def _next(self) -> int:
        self._state = hashlib.sha256(self._state).digest()
        return int.from_bytes(self._state[:8], "big")

    def choice(self, seq: list[Any]) -> Any:
        return seq[self._next() % len(seq)]

    def randint(self, lo: int, hi: int) -> int:
        return lo + self._next() % (hi - lo + 1)

    def uniform(self, lo: float, hi: float) -> float:
        return lo + (hi - lo) * (self._next() / (1 << 64))

    def chance(self, p: float) -> bool:
        return (self._next() / (1 << 64)) < p


# ---------------------------------------------------------------------------
# 品类配置
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelSpec:
    model: str
    base_price: float


@dataclass(frozen=True)
class CategoryConfig:
    category_id: str
    noun: str
    n_spu: int
    n_offers: int
    n_assets: int
    models_by_brand: dict[str, list[ModelSpec]]
    identity_options: dict[str, list[str]]
    variant_options: dict[str, list[str]]
    descriptive_options: dict[str, list[str]]

    @property
    def brands(self) -> list[str]:
        return list(self.models_by_brand)


_CATEGORY_CONFIGS: list[CategoryConfig] = [
    CategoryConfig(
        category_id="headphone",
        noun="耳机",
        n_spu=70,
        n_offers=340,
        n_assets=100,
        models_by_brand={
            "索尼": [
                ModelSpec("WH-1000XM5", 2399.0),
                ModelSpec("WH-1000XM4", 1699.0),
                ModelSpec("WH-CH720N", 899.0),
                ModelSpec("WH-CH520", 349.0),
                ModelSpec("WF-1000XM5", 1999.0),
                ModelSpec("WF-C700N", 699.0),
                ModelSpec("WH-1000XM3", 1299.0),
                ModelSpec("WF-C500", 399.0),
                ModelSpec("WI-C100", 199.0),
                ModelSpec("WH-XB910N", 1099.0),
            ],
            "JBL": [
                ModelSpec("Tune 770NC", 799.0),
                ModelSpec("Tune 510BT", 299.0),
                ModelSpec("Tune Flex", 399.0),
                ModelSpec("Tour ONE M2", 1999.0),
                ModelSpec("Live 770NC", 1199.0),
                ModelSpec("Reflect Flow Pro", 899.0),
                ModelSpec("Quantum 360X", 1499.0),
                ModelSpec("T280TWS", 199.0),
                ModelSpec("Endurance Peak 3", 499.0),
                ModelSpec("Wave Beam", 399.0),
            ],
            "Bose": [
                ModelSpec("QuietComfort 45", 1799.0),
                ModelSpec("QuietComfort Ultra", 2999.0),
                ModelSpec("QuietComfort Earbuds II", 1599.0),
                ModelSpec("SoundLink Flex", 899.0),
                ModelSpec("SoundLink Max", 1999.0),
                ModelSpec("Sport Earbuds", 999.0),
                ModelSpec("QuietComfort SE", 1299.0),
                ModelSpec("SoundLink On-Ear", 699.0),
            ],
            "小米": [
                ModelSpec("Redmi Buds 6 Pro", 399.0),
                ModelSpec("Redmi Buds 5", 199.0),
                ModelSpec("Xiaomi Buds 5", 699.0),
                ModelSpec("Redmi Buds 4 Pro", 349.0),
                ModelSpec("Xiaomi Buds 4 Pro", 899.0),
                ModelSpec("Redmi Buds 6", 299.0),
                ModelSpec("Xiaomi 开放式耳机", 699.0),
                ModelSpec("Redmi Buds 5 Pro", 249.0),
                ModelSpec("小米降噪耳机 Pro", 999.0),
                ModelSpec("小米活塞耳机", 99.0),
            ],
            "漫步者": [
                ModelSpec("W820NB", 399.0),
                ModelSpec("Lolli3 ANC", 329.0),
                ModelSpec("NeoBuds Pro 2", 899.0),
                ModelSpec("W200BT", 109.0),
                ModelSpec("Z2", 149.0),
                ModelSpec("STAX Spirit S3", 1999.0),
                ModelSpec("W830NB", 449.0),
                ModelSpec("Lollipods", 179.0),
            ],
            "森海塞尔": [
                ModelSpec("Momentum 4", 2299.0),
                ModelSpec("HD 450BT", 799.0),
                ModelSpec("CX Plus", 699.0),
                ModelSpec("IE 200", 999.0),
                ModelSpec("Accentum", 1299.0),
                ModelSpec("HD 458BT", 649.0),
                ModelSpec("Momentum True Wireless 4", 2499.0),
                ModelSpec("CX 80S", 399.0),
            ],
            "铁三角": [
                ModelSpec("ATH-M50xBT2", 1399.0),
                ModelSpec("ATH-SQ1TW", 499.0),
                ModelSpec("ATH-CKS50TW", 799.0),
                ModelSpec("ATH-M20x", 399.0),
                ModelSpec("ATH-AR5BT", 899.0),
                ModelSpec("ATH-MSR7b", 1999.0),
            ],
            "Beats": [
                ModelSpec("Studio Pro", 1999.0),
                ModelSpec("Solo 4", 1299.0),
                ModelSpec("Studio Buds+", 899.0),
                ModelSpec("Fit Pro", 1199.0),
                ModelSpec("Powerbeats Pro", 1599.0),
            ],
            "三星": [
                ModelSpec("Galaxy Buds3 Pro", 1299.0),
                ModelSpec("Galaxy Buds FE", 499.0),
                ModelSpec("Galaxy Buds2 Pro", 999.0),
            ],
            "华为": [
                ModelSpec("FreeBuds Pro 3", 999.0),
                ModelSpec("FreeBuds 5i", 499.0),
            ],
        },
        identity_options={
            "connectivity": ["蓝牙", "有线", "双模"],
            "wearing_style": ["头戴式", "入耳式", "半入耳式", "骨传导"],
        },
        variant_options={
            "color": ["黑色", "白色", "银色", "蓝色", "红色", "金色"],
            "set_type": ["单件", "套装"],
        },
        descriptive_options={
            "noise_cancellation": ["主动降噪", "被动降噪", "无"],
            "battery_life": ["8小时", "12小时", "24小时", "30小时", "40小时"],
        },
    ),
    CategoryConfig(
        category_id="sneaker",
        noun="运动鞋",
        n_spu=70,
        n_offers=340,
        n_assets=100,
        models_by_brand={
            "耐克": [
                ModelSpec("Air Zoom Pegasus 41", 899.0),
                ModelSpec("Air Zoom Pegasus 40", 699.0),
                ModelSpec("Air Force 1 07", 749.0),
                ModelSpec("Air Jordan 1 Low", 999.0),
                ModelSpec("Revolution 7", 399.0),
                ModelSpec("Air Max 270", 1099.0),
                ModelSpec("Downshifter 12", 349.0),
                ModelSpec("Vomero 17", 1299.0),
                ModelSpec("Air Zoom Structure 25", 899.0),
                ModelSpec("Winflo 10", 599.0),
            ],
            "阿迪达斯": [
                ModelSpec("Ultraboost Light", 1199.0),
                ModelSpec("Ultraboost 5", 1399.0),
                ModelSpec("Duramo Speed", 429.0),
                ModelSpec("Supernova Rise", 899.0),
                ModelSpec("Adizero Boston 12", 999.0),
                ModelSpec("Runfalcon 3", 299.0),
                ModelSpec("Copa Pure 2", 1099.0),
                ModelSpec("Adizero SL 2", 699.0),
                ModelSpec("Response Super", 549.0),
                ModelSpec("Drop Set 2", 799.0),
            ],
            "新百伦": [
                ModelSpec("Fresh Foam X 1080 v14", 1099.0),
                ModelSpec("Fresh Foam 880 v14", 899.0),
                ModelSpec("FuelCell Propel v5", 749.0),
                ModelSpec("574", 599.0),
                ModelSpec("Fresh Foam X 860 v14", 949.0),
                ModelSpec("FuelCell Rebel v4", 899.0),
                ModelSpec("Fresh Foam Arishi v5", 499.0),
                ModelSpec("990v6", 1599.0),
                ModelSpec("Fresh Foam X More v5", 1099.0),
                ModelSpec("Furon 7", 899.0),
            ],
            "亚瑟士": [
                ModelSpec("GEL-KAYANO 30", 1099.0),
                ModelSpec("GEL-NIMBUS 26", 1099.0),
                ModelSpec("GT-2000 13", 899.0),
                ModelSpec("GEL-CUMULUS 25", 799.0),
                ModelSpec("Magic Speed 3", 999.0),
                ModelSpec("GEL-KAYANO 31", 1199.0),
                ModelSpec("Novablast 4", 899.0),
                ModelSpec("GEL-CONTEND 8", 499.0),
                ModelSpec("GEL-NIMBUS 25", 999.0),
                ModelSpec("Metaracer", 1399.0),
            ],
            "安踏": [
                ModelSpec("C100 碳板跑鞋", 799.0),
                ModelSpec("毒刺 5", 299.0),
                ModelSpec("马赫 4", 599.0),
                ModelSpec("创 3.0", 399.0),
                ModelSpec("C202 5.0", 999.0),
                ModelSpec("氢跑 4", 349.0),
                ModelSpec("柏油路霸 2", 699.0),
                ModelSpec("安踏冠军 2", 899.0),
                ModelSpec("绝影 2", 1099.0),
                ModelSpec("水花 5", 599.0),
            ],
            "李宁": [
                ModelSpec("飞电 4C", 899.0),
                ModelSpec("赤兔 7", 399.0),
                ModelSpec("超轻 21", 499.0),
                ModelSpec("利刃 4", 699.0),
                ModelSpec("音速 12", 599.0),
                ModelSpec("绝影 3", 1299.0),
                ModelSpec("烈骏 7", 549.0),
                ModelSpec("闪击 10", 649.0),
                ModelSpec("韦德之道 11", 1699.0),
                ModelSpec("疾风 2", 449.0),
            ],
            "彪马": [
                ModelSpec("Velocity Nitro 3", 799.0),
                ModelSpec("ForeverRun Nitro", 899.0),
                ModelSpec("RS-X", 699.0),
                ModelSpec("PALERMO", 499.0),
                ModelSpec("Deviate Nitro 3", 1099.0),
                ModelSpec("Electrify Nitro 3", 649.0),
                ModelSpec("Scuderia Ferrari", 1599.0),
                ModelSpec("Suede Classic", 469.0),
            ],
            "昂跑": [
                ModelSpec("Cloudrunner 2", 1099.0),
                ModelSpec("Cloud 5", 1099.0),
                ModelSpec("Cloudmonster 2", 1299.0),
                ModelSpec("Cloudsurfer", 1199.0),
                ModelSpec("Cloudtilt", 1599.0),
                ModelSpec("Cloudflow 4", 1099.0),
            ],
            "斯凯奇": [
                ModelSpec("Go Run Ride 11", 799.0),
                ModelSpec("Go Run Maxroad 5", 899.0),
                ModelSpec("Arch Fit 2.0", 599.0),
                ModelSpec("Go Walk 7", 449.0),
                ModelSpec("D'Lites", 549.0),
                ModelSpec("Go Run Razor 4", 899.0),
            ],
        },
        identity_options={"shoe_type": ["跑步", "篮球", "休闲", "综训"]},
        variant_options={
            "size": ["38", "39", "40", "41", "42", "43", "44", "45"],
            "color": ["黑色", "白色", "红色", "蓝色", "灰色", "荧光绿"],
        },
        descriptive_options={
            "upper_material": ["织物", "皮革", "合成革"],
        },
    ),
    CategoryConfig(
        category_id="hair_dryer",
        noun="吹风机",
        n_spu=60,
        n_offers=320,
        n_assets=100,
        models_by_brand={
            "戴森": [
                ModelSpec("HD15", 2999.0),
                ModelSpec("HD16", 3299.0),
                ModelSpec("Supersonic r", 2799.0),
                ModelSpec("HD08", 2599.0),
                ModelSpec("Airwrap", 3699.0),
                ModelSpec("HD07", 2299.0),
            ],
            "飞利浦": [
                ModelSpec("BHD720", 899.0),
                ModelSpec("BHD337", 499.0),
                ModelSpec("BHD308", 399.0),
                ModelSpec("BHD828", 1299.0),
                ModelSpec("BHD283", 299.0),
                ModelSpec("BHD528", 699.0),
                ModelSpec("HP8235", 599.0),
                ModelSpec("BHD107", 199.0),
            ],
            "松下": [
                ModelSpec("EH-NA9C", 1299.0),
                ModelSpec("EH-NE7J", 399.0),
                ModelSpec("EH-NA98", 999.0),
                ModelSpec("EH-NE6H", 329.0),
                ModelSpec("EH-NA0G", 1599.0),
                ModelSpec("EH-NE5J", 299.0),
                ModelSpec("EH-NA3H", 699.0),
                ModelSpec("EH-WNE6A", 279.0),
            ],
            "小米": [
                ModelSpec("米家高速吹风机 H501", 299.0),
                ModelSpec("米家负离子吹风机", 129.0),
                ModelSpec("米家水离子吹风机", 199.0),
                ModelSpec("米家高速吹风机 H701", 399.0),
                ModelSpec("米家便携吹风机", 99.0),
                ModelSpec("米家高速吹风机 M30", 599.0),
                ModelSpec("米家智能吹风机", 249.0),
                ModelSpec("米家青春版吹风机", 159.0),
            ],
            "徕芬": [
                ModelSpec("LF03", 599.0),
                ModelSpec("SE", 399.0),
                ModelSpec("LF03 Pro", 799.0),
                ModelSpec("LF03S", 699.0),
                ModelSpec("SE Lite", 299.0),
                ModelSpec("Golden 版", 899.0),
            ],
            "康夫": [
                ModelSpec("KF-8905", 199.0),
                ModelSpec("KF-3545", 149.0),
                ModelSpec("KF-5874", 249.0),
                ModelSpec("KF-3139", 129.0),
                ModelSpec("KF-8898", 299.0),
                ModelSpec("KF-3033", 99.0),
            ],
        },
        identity_options={
            "power": ["1200W", "1600W", "1800W", "2000W", "2200W"],
            "ion_type": ["负离子", "水离子", "无"],
        },
        variant_options={
            "color": ["黑色", "白色", "粉色", "紫色", "蓝色", "红色"],
            "voltage_region": ["国行220V", "海外版110V", "全球电压"],
            "set_type": ["单机", "套装"],
        },
        descriptive_options={
            "nozzle_count": ["2个", "3个", "4个", "5个"],
        },
    ),
]


# ---------------------------------------------------------------------------
# 模拟世界模型
# ---------------------------------------------------------------------------

_PLATFORMS = ("jd", "taobao", "pinduoduo")


@dataclass
class SimOffer:
    source_id: str
    spu_id: str
    sku_id: str
    category_id: str
    platform: str
    brand_zh: str
    model: str
    title: str
    price: float | None
    original_price: float | None
    shipping_fee: float | None
    coupon_amount: float | None
    currency: str
    shop_id: str
    shop_name: str
    seller_type: SellerType
    rating: float | None
    sales: float | None
    review_count: float | None
    delivery_days: float | None
    source_updated_at: str | None
    identity: dict[str, str]
    variant: dict[str, str]
    descriptive: dict[str, str]
    source_product_id: str
    asset_id: str | None


@dataclass
class SimSku:
    sku_id: str
    spu_id: str
    category_id: str
    identity: dict[str, str]
    variant: dict[str, str]
    offers: list[SimOffer] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


def _make_png(width: int, height: int, seed: bytes) -> bytes:
    """确定性 PNG（zlib 压缩，无外部依赖）。种子决定颜色块。"""
    rng = SimRng(seed)
    base = (rng.randint(40, 220), rng.randint(40, 220), rng.randint(40, 220))
    accent = (rng.randint(40, 220), rng.randint(40, 220), rng.randint(40, 220))
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter none
        for x in range(width):
            if (x // 8 + y // 8) % 2 == 0:
                raw.extend(base)
            else:
                raw.extend(accent)

    def chunk(tag: bytes, data: bytes) -> bytes:
        out = struct.pack(">I", len(data)) + tag + data
        return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------------------
# 模拟世界生成（确定性）
# ---------------------------------------------------------------------------


def _make_offer(
    config: CategoryConfig,
    rng: SimRng,
    spu_id: str,
    sku_id: str,
    brand_zh: str,
    model: str,
    base_price: float,
    identity: dict[str, str],
    variant: dict[str, str],
    platform: str,
    as_of_dt: datetime,
    index: int,
    descriptive: dict[str, str] | None = None,
) -> SimOffer:
    price: float | None = round(base_price * rng.uniform(0.88, 1.18), 2)
    if rng.chance(0.05):
        price = None
    original_price: float | None = None
    if price is not None and rng.chance(0.6):
        original_price = round(price * rng.uniform(1.05, 1.25), 2)
    shipping_fee: float | None = rng.choice([None, None, 0.0, 6.0, 8.0, 10.0, 12.0])
    coupon_amount: float | None = rng.choice([None, None, None, 20.0, 30.0, 50.0])
    rating: float | None = round(rng.uniform(3.5, 5.0), 1) if rng.chance(0.8) else None
    sales: float | None = float(rng.randint(100, 20000)) if rng.chance(0.6) else None
    review_count: float | None = float(rng.randint(10, 5000)) if rng.chance(0.5) else None
    delivery_days: float | None = float(rng.randint(1, 5)) if rng.chance(0.6) else None
    source_updated_at: str | None = None
    if rng.chance(0.9):
        age = timedelta(days=rng.randint(0, 28))
        source_updated_at = (as_of_dt - age).isoformat(timespec="seconds")

    seller_type = rng.choice(
        [
            SellerType.OFFICIAL,
            SellerType.SELF_OPERATED,
            SellerType.THIRD_PARTY,
            SellerType.THIRD_PARTY,
        ]
    )
    shop_name = {
        SellerType.OFFICIAL: f"{brand_zh}官方旗舰店",
        SellerType.SELF_OPERATED: f"{brand_zh}自营旗舰店",
        SellerType.THIRD_PARTY: f"{brand_zh}品牌专营店",
        SellerType.UNKNOWN: f"{brand_zh}数码专营店",
    }[seller_type]

    identity_desc = " ".join(identity.values())
    if descriptive is None:
        # 默认：SKU 级描述由调用方传入；此处兜底为独立随机（真实页面标题常含平台差异描述）
        descriptive = {k: rng.choice(v) for k, v in config.descriptive_options.items()}
    descriptive_desc = " ".join(descriptive.values())
    variant_desc = " ".join(variant.values())
    title = (
        f"{brand_zh} {model} {config.noun} {identity_desc} {descriptive_desc} {variant_desc}"
    ).strip()

    return SimOffer(
        source_id=f"src:sim-{config.category_id}-{index:04d}",
        spu_id=spu_id,
        sku_id=sku_id,
        category_id=config.category_id,
        platform=platform,
        brand_zh=brand_zh,
        model=model,
        title=title,
        price=price,
        original_price=original_price,
        shipping_fee=shipping_fee,
        coupon_amount=coupon_amount,
        currency="CNY",
        shop_id=f"SIMSHOP{index:06d}",
        shop_name=shop_name,
        seller_type=seller_type,
        rating=rating,
        sales=sales,
        review_count=review_count,
        delivery_days=delivery_days,
        source_updated_at=source_updated_at,
        identity=dict(identity),
        variant=dict(variant),
        descriptive=descriptive,
        source_product_id=(f"SIM{config.category_id.upper()}{platform.upper()}{index:06d}"),
        asset_id=None,
    )


def _build_world(
    config: CategoryConfig, rng: SimRng, as_of_dt: datetime
) -> tuple[list[SimSku], list[SimOffer]]:
    """生成一个品类的 SPU/SKU/Offer（确定性，总数精确等于配置目标）。"""
    skus: list[SimSku] = []
    offers: list[SimOffer] = []
    cat_platform_counts = {p: 0 for p in _PLATFORMS}

    # 每 SPU offer 数：保底 3 + 确定性轮询分配剩余
    extras = [0] * config.n_spu
    remaining = config.n_offers - 3 * config.n_spu
    for i in range(remaining):
        extras[i % config.n_spu] += 1
    spu_offers_count = [3 + extras[i] for i in range(config.n_spu)]

    offer_index = 0
    for i in range(config.n_spu):
        brand_zh = config.brands[i % len(config.brands)]
        brand_models = config.models_by_brand[brand_zh]
        model_spec = brand_models[(i // len(config.brands)) % len(brand_models)]
        spu_id = f"gspu:sim-{config.category_id}-{i:03d}"

        identity = {k: rng.choice(v) for k, v in config.identity_options.items()}
        # SPU 平台对：当前负载最少的 2 个平台（保证每 SPU ≥ 2 平台）
        spu_platforms = sorted(_PLATFORMS, key=lambda p: (cat_platform_counts[p], p))[:2]

        # 每 SPU 2-3 个 SKU：保证同 SPU 不同 SKU 样本对充足（§4.2）
        n_skus = 2 + (i % 2)
        n_offers_here = spu_offers_count[i]
        per_sku = [n_offers_here // n_skus] * n_skus
        for s in range(n_offers_here % n_skus):
            per_sku[s] += 1

        for s in range(n_skus):
            variant = {k: v[(i + s) % len(v)] for k, v in config.variant_options.items()}
            # 描述属性由 SKU 级决定：同 SKU 跨平台标题一致（更接近真实商品标题）
            sku_descriptive = {k: rng.choice(v) for k, v in config.descriptive_options.items()}
            sku_id = f"gsku:sim-{config.category_id}-{i:03d}-{s}"
            sku = SimSku(
                sku_id=sku_id,
                spu_id=spu_id,
                category_id=config.category_id,
                identity=dict(identity),
                variant=dict(variant),
            )
            n = per_sku[s]
            sku_platforms = spu_platforms if n >= 2 else [spu_platforms[0]]
            for k in range(n):
                platform = sku_platforms[k % len(sku_platforms)]
                cat_platform_counts[platform] += 1
                offer = _make_offer(
                    config,
                    rng,
                    spu_id,
                    sku_id,
                    brand_zh,
                    model_spec.model,
                    model_spec.base_price,
                    identity,
                    variant,
                    platform,
                    as_of_dt,
                    offer_index,
                    descriptive=sku_descriptive,
                )
                offer_index += 1
                sku.offers.append(offer)
                offers.append(offer)
            skus.append(sku)

    # 平台 ≤ 60% 再平衡（确定性顺序）
    _rebalance_platforms(offers, skus, cat_platform_counts)
    return skus, offers


def _rebalance_platforms(
    offers: list[SimOffer], skus: list[SimSku], counts: dict[str, int]
) -> None:
    """确定性再平衡：任一平台占比 > 60% 时，把该平台 offer 换到同 SKU 的另一平台。"""
    total = len(offers)
    for _ in range(total * 2):
        over = [p for p, c in counts.items() if c / total > 0.6]
        if not over:
            return
        src = over[0]
        moved = False
        for sku in sorted(skus, key=lambda s: s.sku_id):
            others = sorted({o.platform for o in sku.offers} - {src})
            if not others:
                continue
            for offer in sku.offers:
                if offer.platform == src:
                    counts[src] -= 1
                    offer.platform = others[0]
                    counts[others[0]] += 1
                    moved = True
                    break
            if moved:
                break


# ---------------------------------------------------------------------------
# 写出模拟 workspace（sources/captures/证据/图片/gold draft）
# ---------------------------------------------------------------------------

SIMULATION_NOTE = (
    "simulated source (user-authorized, 2026-08-21): deterministic generator, "
    "no real fetch performed"
)


def safe_name(value: str) -> str:
    """文件名安全化（Windows 不允许冒号等字符）。"""
    return value.replace(":", "_")


def write_simulated_workspace(
    workspace: Path,
    *,
    dataset_id: str,
    as_of: str,
) -> dict[str, int]:
    """生成确定性模拟证据并写入私有 workspace。

    返回 {offer_count, spu_count, asset_count, source_count}。
    """
    as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    if as_of_dt.tzinfo is None:
        as_of_dt = as_of_dt.replace(tzinfo=UTC)
    rng = SimRng(hashlib.sha256(f"{dataset_id}+{as_of}".encode()).digest())
    key = HmacKeyStore(workspace / "keys" / "hmac.key")

    pages_dir = workspace / "raw" / "pages"
    images_dir = workspace / "raw" / "images"
    pages_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    sources: list[SourceSpec] = []
    captures: list[CaptureRecord] = []
    drafts: list[GoldLabelDraft] = []
    asset_map: list[AssetMapEntry] = []
    asset_bindings: list[dict[str, str]] = []

    n_offers = 0
    spu_ids: set[str] = set()
    n_assets = 0
    for config in _CATEGORY_CONFIGS:
        _skus, offers = _build_world(config, rng, as_of_dt)
        spu_ids.update(o.spu_id for o in offers)
        # 先绑定资产（证据 images 引用 asset_id），再写证据
        for i in range(config.n_assets):
            asset_id = f"ast-{config.category_id}-{i:03d}"
            seed = hashlib.sha256(f"{dataset_id}+{asset_id}".encode()).digest()
            data = _make_png(32, 32, seed)
            (images_dir / f"{asset_id}.png").write_bytes(data)
            asset_map.append(
                AssetMapEntry(
                    asset_id=asset_id,
                    content_type=ImageContentType.PNG,
                    sha256=sha256_hex(data),
                    width=32,
                    height=32,
                    local_path=f"{asset_id}.png",
                    source_content_hash=sha256_hex(data),
                )
            )
            if i < len(offers):
                offers[i].asset_id = asset_id
                asset_bindings.append({"asset_id": asset_id, "source_id": offers[i].source_id})
            n_assets += 1
        for offer in offers:
            evidence = _evidence_for(config, offer)
            evidence_bytes = json.dumps(evidence, ensure_ascii=False, indent=2).encode("utf-8")
            content_sha = sha256_hex(evidence_bytes)
            capture_id = f"cap:{offer.source_id}"
            evidence_filename = f"{safe_name(capture_id)}.json"
            (pages_dir / evidence_filename).write_bytes(evidence_bytes)
            final_url = (
                f"https://example.com/products/sim/{config.category_id}/"
                f"{offer.source_id.split('-')[-1]}.html"
            )
            sources.append(
                SourceSpec(
                    source_id=offer.source_id,
                    url=final_url,
                    platform=offer.platform,
                    category_id=config.category_id,
                    official_identity_url=None,
                    notes=SIMULATION_NOTE,
                )
            )
            captures.append(
                CaptureRecord(
                    capture_id=capture_id,
                    source_id=offer.source_id,
                    status="ok",
                    http_status=200,
                    fetched_at=as_of,
                    final_url=final_url,
                    final_url_hmac=key.mask(final_url),
                    content_sha256=content_sha,
                    content_type="application/json",
                    size_bytes=len(evidence_bytes),
                    evidence_path=f"raw/pages/{evidence_filename}",
                    error_message=None,
                )
            )
            drafts.append(
                GoldLabelDraft(
                    source_id=offer.source_id,
                    gold_spu_id=offer.spu_id,
                    gold_sku_id=offer.sku_id,
                    identity_attributes=dict(offer.identity),
                    variant_attributes=dict(offer.variant),
                    evidence_refs=[f"sha256:{content_sha}"],
                    label_rationale=(
                        "模拟来源：Agent 依据模拟证据中的品牌/型号/属性标注"
                        "（用户授权模拟数据集，非真实采集，无独立人工复核）"
                    ),
                )
            )
            n_offers += 1

    _write_jsonl(workspace / "sources.jsonl", [s.model_dump() for s in sources])
    _write_jsonl(workspace / "captures.jsonl", [c.model_dump() for c in captures])
    _write_jsonl(workspace / "gold_labels_draft.jsonl", [d.model_dump() for d in drafts])
    _write_jsonl(workspace / "asset_map.jsonl", [a.model_dump() for a in asset_map])
    _write_jsonl(workspace / "asset_bindings.jsonl", asset_bindings)
    return {
        "offer_count": n_offers,
        "spu_count": len(spu_ids),
        "asset_count": n_assets,
        "source_count": len(sources),
    }


def _evidence_for(config: CategoryConfig, offer: SimOffer) -> dict[str, Any]:
    """模拟证据：与真实采集器输出同构（提取结果 JSON）。"""
    return {
        "extraction": "simulated-jsonld",
        "source_id": offer.source_id,
        "offer": {
            "platform": offer.platform,
            "source_product_id": offer.source_product_id,
            "source_updated_at": offer.source_updated_at,
            "title": offer.title,
            "category_id": offer.category_id,
            "brand": offer.brand_zh,
            "model": offer.model,
            "identity_attributes": offer.identity,
            "variant_attributes": offer.variant,
            "descriptive_attributes": offer.descriptive,
            "price": offer.price,
            "original_price": offer.original_price,
            "shipping_fee": offer.shipping_fee,
            "coupon_amount": offer.coupon_amount,
            "currency": offer.currency,
            "shop_id": offer.shop_id,
            "shop_name": offer.shop_name,
            "seller_type": offer.seller_type.value,
            "rating": offer.rating,
            "sales": offer.sales,
            "review_count": offer.review_count,
            "delivery_days": offer.delivery_days,
        },
        "images": [offer.asset_id] if offer.asset_id else [],
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
