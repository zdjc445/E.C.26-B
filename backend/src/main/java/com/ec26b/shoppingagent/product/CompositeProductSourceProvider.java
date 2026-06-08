package com.ec26b.shoppingagent.product;

import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * Primary product source for the current delivery.
 */
@Primary
@Component
public class CompositeProductSourceProvider implements ProductSourceProvider {

    private final MockProductSourceProvider mock;
    private final PublicDatasetProductSourceProvider publicDataset;
    private final String mode;

    public CompositeProductSourceProvider(MockProductSourceProvider mock,
                                          PublicDatasetProductSourceProvider publicDataset,
                                          @org.springframework.beans.factory.annotation.Value(
                                                  "${app.product-source.mode:public-dataset}")
                                          String mode) {
        this.mock = mock;
        this.publicDataset = publicDataset;
        this.mode = mode;
    }

    @Override
    public ProductSearchResult search(ProductSearchQuery query) {
        if ("mock".equalsIgnoreCase(mode)) {
            return mock.search(query);
        }
        if ("public-dataset-only".equalsIgnoreCase(mode)) {
            return publicDataset.search(query);
        }

        ProductSearchResult publicResult = publicDataset.search(query);
        ProductSearchResult mockResult = mock.search(query);
        List<ProductOffer> products = new ArrayList<>();
        products.addAll(publicResult.products());
        products.addAll(mockResult.products());
        return ProductSearchResults.fromProducts(products, query.sortBy());
    }

    @Override
    public String sourceName() {
        return "mock".equalsIgnoreCase(mode) ? "mock" : "public-dataset+mock";
    }
}
