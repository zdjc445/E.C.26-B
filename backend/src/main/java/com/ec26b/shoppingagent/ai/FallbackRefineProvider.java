package com.ec26b.shoppingagent.ai;

import java.util.List;
import java.util.Map;

public class FallbackRefineProvider implements AiRefineProvider {
    private final AiRefineProvider primary;
    private final AiRefineProvider fallback;

    public FallbackRefineProvider(AiRefineProvider primary, AiRefineProvider fallback) {
        this.primary = primary;
        this.fallback = fallback;
    }

    @Override
    public RefineParseResult parse(String text, Map<String, Object> existingFilters) {
        try {
            RefineParseResult result = primary.parse(text, existingFilters);
            if (result.filters() != null && !result.filters().isEmpty()) {
                return result;
            }
            RefineParseResult fallbackResult = fallback.parse(text, existingFilters);
            return new RefineParseResult(fallbackResult.filters(), fallback.providerName(), true, List.of("LLM 未解析出有效筛选条件，已回退规则解析。"));
        } catch (RuntimeException ex) {
            RefineParseResult fallbackResult = fallback.parse(text, existingFilters);
            return new RefineParseResult(fallbackResult.filters(), fallback.providerName(), true, List.of("LLM refine 调用失败，已回退规则解析。"));
        }
    }

    @Override
    public String providerName() {
        return primary.providerName() + "+fallback";
    }
}
