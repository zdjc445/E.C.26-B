"""评测数据集生命周期契约（Phase 1 provisional 方案 §5–§7）。

本模块承载 provisional 真实评测闭环的数据契约与工具函数：

- ``SourceSpec`` / ``CaptureRecord``：采集源与采集结果（§5.1）。
- ``OfferGoldLabel`` / ``GoldLabelDraft``：Agent Gold 标签目录（§6.2）。
- ``EvalAssetRef`` / ``EvalSampleMeta``：真实数据样本引用与样本元数据（§7.1–§7.2）。
- ``DatasetManifest``：数据集清单（§7.3），自身不进入 files 哈希映射。
- ``stable_split``：稳定 SHA-256 SPU 拆分（§4.3），不依赖进程随机 hash。
- HMAC 脱敏：本地密钥 + 确定性掩码（§6.1）。
- Asset 解析：私有 asset_map → 内存 data URL（§7.1）。

所有模型使用 ``extra="forbid"`` 严格校验，禁止多余字段。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shijiajing_agent.contracts import ImageContentType, ImageRef, sha256_hex

# ---------------------------------------------------------------------------
# 固定版本值（§3）
# ---------------------------------------------------------------------------

# 计划 §3 固定值为 shijiajing-provisional-real-v1；本环境数据由用户授权的确定性
# 模拟生成器产出（非真实采集），dataset_id 如实标注 sim，见 known_limitations。
DATASET_ID_SIM = "shijiajing-provisional-sim-v1"
DATASET_SCHEMA_VERSION = "1.0"
TRUST_LEVEL_PROVISIONAL = "provisional"
TRUST_LEVEL_FROZEN = "frozen"
LABEL_METHOD_AGENT = "agent_only"
LABEL_METHOD_ADJUDICATED = "adjudicated"
GATE_ELIGIBLE_FALSE = False

# 现有平台 ID（docs/evaluation.md §1；不猜测别名）
PLATFORM_IDS = ("taobao", "jd", "pinduoduo")

SPLIT_DEVELOPMENT = "development"
SPLIT_HOLDOUT = "holdout"
_SPLIT_RATIO_DEVELOPMENT = 0.4  # §4.3：40% development / 60% holdout


def stable_split(dataset_id: str, gold_spu_id: str) -> Literal["development", "holdout"]:
    """稳定 SHA-256 拆分（§4.3）：输入 dataset_id + gold_spu_id，输出固定 split。"""
    digest = hashlib.sha256(f"{dataset_id}+{gold_spu_id}".encode()).digest()
    bucket = int.from_bytes(digest[:8], "big") / (1 << 64)
    return SPLIT_DEVELOPMENT if bucket < _SPLIT_RATIO_DEVELOPMENT else SPLIT_HOLDOUT


# ---------------------------------------------------------------------------
# 采集契约（§5）
# ---------------------------------------------------------------------------


def is_private_host(host: str) -> bool:
    """回环、链路本地与 RFC 1918 内网地址不允许作为采集目标（与 ImageRef 同规则）。"""
    if host in ("localhost", "::1", "0.0.0.0", "metadata.google.internal"):
        return True
    if host.endswith(".local"):
        return True
    if host.startswith("127.") or host.startswith("10.") or host.startswith("192.168."):
        return True
    if host.startswith("172."):
        try:
            return 16 <= int(host.split(".")[1]) <= 31
        except (IndexError, ValueError):
            return False
    return False


def _public_url_or_error(url: str) -> str:
    """校验公网 http/https URL；拒绝内网、回环、本地文件与非 HTTP 协议。"""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("url 只允许公网 http/https")
    host = (parsed.hostname or "").lower()
    if is_private_host(host):
        raise ValueError("url 不允许指向内网、回环或本机地址")
    return url


class SourceSpec(BaseModel):
    """采集源清单行（§5.1）。"""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    category_id: str = Field(min_length=1)
    official_identity_url: str | None = None
    notes: str | None = None

    @field_validator("url", "official_identity_url")
    @classmethod
    def _validate_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _public_url_or_error(v)


_CAPTURE_STATUSES = ("ok", "unavailable", "manual_required", "invalid")


class CaptureRecord(BaseModel):
    """采集结果（§5.2）。status 固定为 ok/unavailable/manual_required/invalid。"""

    model_config = ConfigDict(extra="forbid")

    capture_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    status: Literal["ok", "unavailable", "manual_required", "invalid"]
    http_status: int | None = None
    fetched_at: str | None = None
    final_url: str | None = None
    final_url_hmac: str | None = None
    content_sha256: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    evidence_path: str | None = None  # workspace 相对路径
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Gold 标签（§6.2）
# ---------------------------------------------------------------------------


class GoldLabelDraft(BaseModel):
    """私有标注草稿：source_id → Gold 身份（prepare 阶段脱敏前的中间产物）。

    只存在于私有 workspace，不随数据集提交。label_source 固定为 agent。
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    gold_spu_id: str = Field(min_length=1)
    gold_sku_id: str = Field(min_length=1)
    identity_attributes: dict[str, str] = Field(default_factory=dict[str, str])
    variant_attributes: dict[str, str] = Field(default_factory=dict[str, str])
    evidence_refs: list[str] = Field(default_factory=list[str])
    label_rationale: str = Field(min_length=1)


class OfferGoldLabel(BaseModel):
    """Agent Gold 标签目录行（§6.2）。"""

    model_config = ConfigDict(extra="forbid")

    offer_id: str = Field(min_length=1)
    gold_spu_id: str = Field(min_length=1)
    gold_sku_id: str = Field(min_length=1)
    category_id: str = Field(min_length=1)
    identity_attributes: dict[str, str] = Field(default_factory=dict[str, str])
    variant_attributes: dict[str, str] = Field(default_factory=dict[str, str])
    evidence_refs: list[str] = Field(default_factory=list[str])
    label_source: Literal["agent", "human", "adjudicated"] = "agent"
    label_rationale: str = Field(min_length=1)
    split: Literal["development", "holdout"]


# ---------------------------------------------------------------------------
# 评测样本元数据（§7.1–§7.2）
# ---------------------------------------------------------------------------


class EvalAssetRef(BaseModel):
    """真实数据图片引用（§7.1）：提交数据不保存图片 URL，只保存引用与摘要。"""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1)
    content_type: ImageContentType
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EvalSampleMeta(BaseModel):
    """样本元数据（§7.2）。provisional 数据校验器要求该字段必填。"""

    model_config = ConfigDict(extra="forbid")

    dataset_version: str = Field(min_length=1)
    split: Literal["development", "holdout"]
    category_id: str = Field(min_length=1)
    subject_ids: list[str] = Field(default_factory=list[str])
    source_refs: list[str] = Field(default_factory=list[str])
    label_source: Literal["agent", "human", "adjudicated"]


# ---------------------------------------------------------------------------
# 资产清单与映射
# ---------------------------------------------------------------------------


class AssetInventoryEntry(BaseModel):
    """asset_inventory.jsonl 行（§6.1）：只提交 asset_id、类型、SHA-256、宽高、来源哈希。"""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1)
    content_type: ImageContentType
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    source_content_hash: str | None = None


class AssetMapEntry(BaseModel):
    """私有 asset_map.jsonl 行：asset_id → 本地相对路径（相对 assets 根目录）。"""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1)
    content_type: ImageContentType
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    local_path: str = Field(min_length=1)
    source_content_hash: str | None = None


class AssetBinding(BaseModel):
    """私有 asset_bindings.jsonl 行：asset_id → source_id（识别样本主图绑定）。"""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)


class OfferSourceMap(BaseModel):
    """私有 offer_source_map.jsonl 行：脱敏 offer_id → source_id（可追溯性）。"""

    model_config = ConfigDict(extra="forbid")

    offer_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)


def load_asset_map(path: Path) -> dict[str, AssetMapEntry]:
    entries: dict[str, AssetMapEntry] = {}
    if not path.exists():
        return entries
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            entry = AssetMapEntry.model_validate_json(line)
            if entry.asset_id in entries:
                raise ValueError(f"asset_map.jsonl:{line_no} 重复 asset_id: {entry.asset_id}")
            entries[entry.asset_id] = entry
    return entries


def verify_asset_sha256(entry: AssetMapEntry, assets_dir: Path) -> Path:
    """校验资产文件存在且 SHA-256 与清单一致；返回文件路径。"""
    path = assets_dir / entry.local_path
    if not path.is_file():
        raise ValueError(f"资产文件缺失: {entry.local_path}")
    actual = sha256_hex(path.read_bytes())
    if actual != entry.sha256:
        raise ValueError(f"资产摘要不一致 {entry.asset_id}: 期望 {entry.sha256}，实际 {actual}")
    return path


def asset_to_data_url(entry: AssetMapEntry, assets_dir: Path) -> str:
    """本地资产 → data URL（§7.1 live 运行时解析）。校验 SHA-256 后构建。"""
    path = verify_asset_sha256(entry, assets_dir)
    data = path.read_bytes()
    import base64

    return f"data:{entry.content_type.value};base64,{base64.b64encode(data).decode('ascii')}"


def asset_ref_to_image_ref(
    asset_ref: EvalAssetRef, assets_dir: Path, asset_map: dict[str, AssetMapEntry]
) -> ImageRef:
    """EvalAssetRef → ImageRef(data URL)。找不到或摘要不符时抛 ValueError。"""
    entry = asset_map.get(asset_ref.asset_id)
    if entry is None:
        raise ValueError(f"asset_map 中不存在 asset_id: {asset_ref.asset_id}")
    if entry.sha256 != asset_ref.sha256:
        raise ValueError(f"asset 摘要与样本引用不一致: {asset_ref.asset_id}")
    return ImageRef(
        image_id=asset_ref.asset_id,
        uri=asset_to_data_url(entry, assets_dir),
        content_type=asset_ref.content_type,
        sha256=asset_ref.sha256,
    )


# ---------------------------------------------------------------------------
# HMAC 脱敏（§6.1）
# ---------------------------------------------------------------------------


class HmacKeyStore:
    """本地脱敏密钥：首次使用生成 32 字节随机密钥，之后复用。

    仓库只保存掩码结果与 key_id，不保存密钥（密钥文件位于私有 workspace）。
    """

    def __init__(self, key_file: Path) -> None:
        self._key_file = key_file

    @property
    def key_id(self) -> str:
        return "k:" + sha256_hex(self._load())[:16]

    def _load(self) -> bytes:
        if self._key_file.exists():
            data = self._key_file.read_bytes()
            if len(data) == 32:
                return data
            raise ValueError(f"HMAC 密钥文件格式无效: {self._key_file}")
        data = secrets.token_bytes(32)
        self._key_file.parent.mkdir(parents=True, exist_ok=True)
        self._key_file.write_bytes(data)
        return data

    def mask(self, value: str) -> str:
        """HMAC-SHA256 掩码（十六进制）。"""
        return hmac.new(self._load(), value.encode("utf-8"), hashlib.sha256).hexdigest()


def mask_id(prefix: str, key: HmacKeyStore, value: str) -> str:
    """确定性掩码 ID：off:/shop:/spid: 前缀 + HMAC 摘要。"""
    return f"{prefix}{key.mask(value)}"


def sha256_hmac_url(key: HmacKeyStore, url: str) -> str:
    """规范化 URL 的 HMAC 标识（source_product_id 缺失时的去重键，§4.1）。"""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return key.mask(normalized)


# ---------------------------------------------------------------------------
# 数据集清单（§7.3）
# ---------------------------------------------------------------------------


class DatasetManifest(BaseModel):
    """数据集清单。manifest 自身不进入 files 哈希映射，避免自引用。"""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1)
    dataset_schema_version: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    taxonomy_version: str = Field(min_length=1)
    trust_level: Literal["provisional", "frozen"]
    label_method: Literal["agent_only", "human", "adjudicated"]
    gate_eligible: bool
    created_at: str
    as_of: str
    categories: dict[str, int]
    counts_by_file: dict[str, int]
    counts_by_split: dict[str, int]
    counts_by_platform: dict[str, int]
    offer_count: int
    spu_count: int
    asset_count: int
    files: dict[str, str]
    # 扩展字段（§7.3 必填项之外，用于样本 source ref 解析与来源说明）
    source_ids: list[str] = Field(default_factory=list[str])
    image_domain: str | None = None
    known_limitations: list[str] = Field(default_factory=list[str])


MANIFEST_FILENAME = "manifest.json"


def load_manifest(datasets_dir: Path) -> DatasetManifest | None:
    path = datasets_dir / MANIFEST_FILENAME
    if not path.exists():
        return None
    return DatasetManifest.model_validate_json(path.read_text(encoding="utf-8"))


def compute_files_sha256(datasets_dir: Path) -> dict[str, str]:
    """提交目录内全部数据文件的 SHA-256（排除 manifest 自身）。"""
    files: dict[str, str] = {}
    for path in sorted(datasets_dir.iterdir()):
        if not path.is_file() or path.name == MANIFEST_FILENAME:
            continue
        files[path.name] = sha256_hex(path.read_bytes())
    return files


def build_manifest(
    *,
    dataset_id: str,
    dataset_version: str,
    taxonomy_version: str,
    created_at: str,
    as_of: str,
    categories: dict[str, int],
    counts_by_file: dict[str, int],
    counts_by_split: dict[str, int],
    counts_by_platform: dict[str, int],
    offer_count: int,
    spu_count: int,
    asset_count: int,
    source_ids: list[str],
    known_limitations: list[str],
    files: dict[str, str],
    image_domain: str | None = None,
) -> DatasetManifest:
    return DatasetManifest(
        dataset_id=dataset_id,
        dataset_schema_version=DATASET_SCHEMA_VERSION,
        dataset_version=dataset_version,
        taxonomy_version=taxonomy_version,
        trust_level=TRUST_LEVEL_PROVISIONAL,
        label_method=LABEL_METHOD_AGENT,
        gate_eligible=GATE_ELIGIBLE_FALSE,
        created_at=created_at,
        as_of=as_of,
        categories=categories,
        counts_by_file=counts_by_file,
        counts_by_split=counts_by_split,
        counts_by_platform=counts_by_platform,
        offer_count=offer_count,
        spu_count=spu_count,
        asset_count=asset_count,
        files=files,
        source_ids=sorted(source_ids),
        image_domain=image_domain,
        known_limitations=known_limitations,
    )


# ---------------------------------------------------------------------------
# JSONL 工具
# ---------------------------------------------------------------------------


def write_jsonl[T: BaseModel](path: Path, rows: list[T], *, sort_key: str | None = None) -> None:
    """按 id 排序写出字节一致的 JSONL（§6.1：输出按 id 排序）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if sort_key is not None:
        rows = sorted(rows, key=lambda r: getattr(r, sort_key))
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(row.model_dump_json(exclude_none=True) + "\n")


def load_jsonl_rows[T: BaseModel](path: Path, model: type[T]) -> list[T]:
    """逐行加载 jsonl 并严格校验；解析失败立即报错（数据必须干净）。"""
    rows: list[T] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(model.model_validate_json(line))
            except Exception as exc:
                raise ValueError(f"{path.name}:{line_no} 校验失败: {exc}") from exc
    return rows


def as_iso(dt: Any) -> str:
    """任意 datetime/字符串 → UTC ISO 时间戳。"""
    if isinstance(dt, str):
        return dt
    return dt.isoformat()
