package com.ec26b.shoppingagent.ai;

import java.util.Map;

public interface AiRefineProvider {
    RefineParseResult parse(String text, Map<String, Object> existingFilters);

    String providerName();
}
