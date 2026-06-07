package com.ec26b.shoppingagent.product;

import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

/**
 * Routing provider that prefers {@link RealEcommerceProvider} when enabled, and
 * falls back to {@link MockProductSourceProvider} on empty / failed responses.
 *
 * <p>Marked {@code @Primary} so any consumer asking for a {@link ProductSourceProvider}
 * gets this composite. Direct {@code MockProductSourceProvider} consumers (e.g. tests)
 * still receive the mock implementation by type.
 */
@Primary
@Component
public class CompositeProductSourceProvider implements ProductSourceProvider {

    private final RealEcommerceProvider real;
    private final MockProductSourceProvider mock;

    public CompositeProductSourceProvider(RealEcommerceProvider real,
                                          MockProductSourceProvider mock) {
        this.real = real;
        this.mock = mock;
    }

    @Override
    public ProductSearchResult search(ProductSearchQuery query) {
        if (real.enabled()) {
            ProductSearchResult result = real.search(query);
            if (result != null && !result.products().isEmpty()) {
                return result;
            }
        }
        return mock.search(query);
    }

    @Override
    public String sourceName() {
        return real.enabled() ? "real+mock-fallback" : "mock";
    }
}
