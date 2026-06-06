package com.ec26b.shoppingagent.product;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

public class FallbackShoppingIntentParser implements ShoppingIntentParser {

    private static final Logger log = LoggerFactory.getLogger(FallbackShoppingIntentParser.class);

    private final ShoppingIntentParser primary;
    private final ShoppingIntentParser fallback;

    public FallbackShoppingIntentParser(ShoppingIntentParser primary, ShoppingIntentParser fallback) {
        this.primary = primary;
        this.fallback = fallback;
    }

    @Override
    public ShoppingIntent parse(String text) {
        try {
            ShoppingIntent result = primary.parse(text);
            if (result.needsClarification()) {
                log.info("Ark intent parser returned needsClarification, falling back to rule.");
                return fallback.parse(text);
            }
            return result;
        } catch (RuntimeException ex) {
            log.warn("Ark intent parser failed, falling back to rule: {}: {}",
                    ex.getClass().getSimpleName(), ex.getMessage());
            ShoppingIntent fb = fallback.parse(text);
            return new ShoppingIntent(fb.keyword(), fb.maxPrice(), fb.color(),
                    fb.officialStore(), fb.fastDelivery(), fb.lowestPrice(),
                    fb.highRating(), fb.highSales(),
                    fb.needsClarification(), fb.clarificationQuestion(),
                    fb.intentProvider(), true,
                    List.of("Ark 意图解析不可用，已回退规则解析。"));
        }
    }

    @Override
    public String providerName() {
        return primary.providerName() + "+fallback";
    }
}
