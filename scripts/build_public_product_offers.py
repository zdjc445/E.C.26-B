#!/usr/bin/env python3
"""Build the public product resource from the referenced Flipkart CSV."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tempfile
import urllib.request
from pathlib import Path


SOURCE_NAME = "jason1966/PromptCloudHQ_flipkart-products"
SOURCE_PAGE = (
    "https://huggingface.co/datasets/"
    "jason1966/PromptCloudHQ_flipkart-products"
)
SOURCE_FILE = "flipkart_com-ecommerce_sample.csv"
SOURCE_DOWNLOAD = (
    f"{SOURCE_PAGE}/resolve/main/{SOURCE_FILE}"
)
SOURCE_SHA256 = "56f8f699c9e847356666c2eab3c3ab1244340f6a98ad08e39ea2199ebe993ad1"
PLATFORM = "Flipkart-sample"

CATEGORY_RULES = (
    ("运动鞋", ("sports shoes", "running shoes")),
    ("耳机", ("headphone", "headset", "earphone")),
    ("吹风机", ("hair dryer",)),
    ("背包", ("backpack",)),
)


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        help="Existing flipkart_com-ecommerce_sample.csv path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            repo_root
            / "backend"
            / "src"
            / "main"
            / "resources"
            / "data"
            / "public-product-offers.json"
        ),
    )
    return parser.parse_args()


def download_source() -> Path:
    target = Path(tempfile.gettempdir()) / SOURCE_FILE
    urllib.request.urlretrieve(SOURCE_DOWNLOAD, target)
    return target


def verify_source(source_path: Path) -> None:
    digest = hashlib.sha256()
    with source_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != SOURCE_SHA256:
        raise ValueError(
            f"Source SHA-256 mismatch: expected {SOURCE_SHA256}, got {actual}"
        )


def parse_number(raw: str | None) -> float | None:
    value = (raw or "").strip().replace(",", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_rating(row: dict[str, str]) -> float:
    for field in ("product_rating", "overall_rating"):
        rating = parse_number(row.get(field))
        if rating is not None and 0 <= rating <= 5:
            return rating
    return 0.0


def first_image(raw: str | None) -> str:
    try:
        images = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return ""
    if not isinstance(images, list):
        return ""
    for image in images:
        if isinstance(image, str) and image.startswith(("http://", "https://")):
            return image
    return ""


def resolve_category(row: dict[str, str]) -> str | None:
    searchable = (
        f"{row.get('product_category_tree', '')} "
        f"{row.get('product_name', '')}"
    ).lower()
    for category, terms in CATEGORY_RULES:
        if any(term in searchable for term in terms):
            return category
    return None


def build_product(row: dict[str, str], category: str) -> dict[str, object] | None:
    pid = (row.get("pid") or "").strip()
    title = (row.get("product_name") or "").strip()
    product_url = (row.get("product_url") or "").strip()
    image_url = first_image(row.get("image"))
    price = parse_number(row.get("discounted_price"))

    if not pid or not title or not product_url or not image_url or price is None:
        return None

    original_price = parse_number(row.get("retail_price"))
    if original_price is None or original_price < price:
        original_price = price

    brand = (row.get("brand") or "").strip()
    raw_rating = (row.get("product_rating") or "").strip()

    return {
        "productId": f"flipkart-{pid}",
        "category": category,
        "title": title,
        "platform": PLATFORM,
        "price": price,
        "originalPrice": original_price,
        "shopName": brand or PLATFORM,
        "imageUrl": image_url,
        "productUrl": product_url,
        "rating": parse_rating(row),
        "sales": 0,
        "brand": brand,
        "tags": ["public_dataset", "flipkart_sample"],
        "sourceCategory": (row.get("product_category_tree") or "").strip(),
        "rawRating": raw_rating,
    }


def build_catalog(source_path: Path) -> list[dict[str, object]]:
    products: list[dict[str, object]] = []
    seen_ids: set[str] = set()

    with source_path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            category = resolve_category(row)
            if category is None:
                continue
            product = build_product(row, category)
            if product is None:
                continue
            product_id = str(product["productId"])
            if product_id in seen_ids:
                continue
            seen_ids.add(product_id)
            products.append(product)

    category_order = {
        category: index for index, (category, _) in enumerate(CATEGORY_RULES)
    }
    products.sort(
        key=lambda product: (
            category_order[str(product["category"])],
            str(product["productId"]),
        )
    )
    return products


def main() -> None:
    args = parse_args()
    source_path = args.input.resolve() if args.input else download_source()
    verify_source(source_path)
    products = build_catalog(source_path)
    payload = {
        "source": {
            "name": SOURCE_NAME,
            "url": SOURCE_PAGE,
            "file": SOURCE_FILE,
        },
        "products": products,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    counts = {
        category: sum(product["category"] == category for product in products)
        for category, _ in CATEGORY_RULES
    }
    print(f"Wrote {len(products)} products to {args.output}")
    for category, count in counts.items():
        print(f"{category}: {count}")


if __name__ == "__main__":
    main()
