package com.ec26b.shoppingagent.product;

import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

/**
 * Primary product source for the current delivery.
 *
 * <p>Marked {@code @Primary} so any consumer asking for a {@link ProductSourceProvider}
 * gets deterministic mock data. Real ecommerce calls are intentionally outside
 * the current delivery scope.
 */
@Primary
@Component
public class CompositeProductSourceProvider implements ProductSourceProvider {

    private final MockProductSourceProvider mock;

    public CompositeProductSourceProvider(MockProductSourceProvider mock) {
        this.mock = mock;
    }

    @Override
    public ProductSearchResult search(ProductSearchQuery query) {
        return mock.search(query);
    }

    @Override
    public String sourceName() {
        return "mock";
    }
}
