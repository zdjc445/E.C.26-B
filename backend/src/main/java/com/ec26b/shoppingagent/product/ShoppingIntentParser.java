package com.ec26b.shoppingagent.product;

public interface ShoppingIntentParser {
    ShoppingIntent parse(String text);
    String providerName();
}
