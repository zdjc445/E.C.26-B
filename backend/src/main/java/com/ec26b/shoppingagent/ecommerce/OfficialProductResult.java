package com.ec26b.shoppingagent.ecommerce;

import com.ec26b.shoppingagent.service.MockCatalog;

import java.util.Optional;

public record OfficialProductResult(
        MockCatalog.ProductData product,
        MockCatalog.PlatformProductData platformProduct,
        Optional<MockCatalog.ReviewSummaryData> reviewSummary
) {
}
