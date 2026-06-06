package com.ec26b.shoppingagent.product;

public interface ProductSourceProvider {
    ProductSearchResult search(ProductSearchQuery query);
    String sourceName();
}
