package com.ec26b.shoppingagent.ai;

import java.util.List;
import java.util.Map;

public record RefineParseResult(
        Map<String, Object> filters,
        String provider,
        boolean fallbackUsed,
        List<String> notices
) {
}
