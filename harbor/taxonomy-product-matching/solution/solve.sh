#!/usr/bin/env bash
set -euo pipefail

install -m 0644 /solution/product_matching/normalization.py \
  /app/src/product_matching/normalization.py
install -m 0644 /solution/product_matching/same_item.py \
  /app/src/product_matching/same_item.py
install -m 0644 /solution/product_matching/sku.py \
  /app/src/product_matching/sku.py
