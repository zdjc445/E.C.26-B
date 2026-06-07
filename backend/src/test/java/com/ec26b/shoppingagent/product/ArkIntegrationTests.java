package com.ec26b.shoppingagent.product;

import com.ec26b.shoppingagent.ai.ArkClient;
import com.ec26b.shoppingagent.ai.ArkRecognitionProvider;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@ActiveProfiles("default")
class ArkIntegrationTests {

    @Autowired
    private RuleBasedShoppingIntentParser ruleParser;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void ruleParserShouldExtractKeywordAndPreferences() {
        ShoppingIntent intent = ruleParser.parse("我想买200以内黑色的耳机，便宜一点");
        assertEquals("耳机", intent.keyword());
        assertEquals(200.0, intent.maxPrice());
        assertEquals("黑色", intent.color());
        assertTrue(intent.lowestPrice());
        assertEquals("rule", intent.intentProvider());
        assertFalse(intent.intentFallbackUsed());
    }

    @Test
    void ruleParserShouldExtractOfficialStorePreference() {
        ShoppingIntent intent = ruleParser.parse("我要官方店铺的吹风机");
        assertEquals("吹风机", intent.keyword());
        assertTrue(intent.officialStore());
    }

    @Test
    void ruleParserShouldDefaultToRunningShoesWhenNoKeyword() {
        ShoppingIntent intent = ruleParser.parse("便宜的");
        assertEquals("运动鞋", intent.keyword());
    }

    @Test
    void supportedCategoryCheckShouldWork() {
        assertTrue(RuleBasedShoppingIntentParser.isSupportedCategory("运动鞋"));
        assertTrue(RuleBasedShoppingIntentParser.isSupportedCategory("耳机"));
        assertTrue(RuleBasedShoppingIntentParser.isSupportedCategory("吹风机"));
        assertFalse(RuleBasedShoppingIntentParser.isSupportedCategory("手机"));
        assertFalse(RuleBasedShoppingIntentParser.isSupportedCategory(null));
    }

    @Test
    void resolveKeywordShouldPrioritizeRecognitionCategory() {
        assertEquals("耳机",
                RuleBasedShoppingIntentParser.resolveKeyword("耳机", "运动鞋"));
        assertEquals("吹风机",
                RuleBasedShoppingIntentParser.resolveKeyword("吹风机", "耳机"));
        // unsupported recognition → fallback to parsed
        assertEquals("吹风机",
                RuleBasedShoppingIntentParser.resolveKeyword("手机", "吹风机"));
        // both null → default
        assertEquals("运动鞋",
                RuleBasedShoppingIntentParser.resolveKeyword(null, null));
    }

    @Test
    void arkFallbackShouldReturnRuleIntentWithFallbackFlag() {
        // Without real keys, the Ark client will throw — test the fallback
        ArkClient dummyClient = new ArkClient(objectMapper, "", "", "https://ark.cn-beijing.volces.com/api/v3");
        ArkShoppingIntentParser arkParser = new ArkShoppingIntentParser(dummyClient, objectMapper);
        FallbackShoppingIntentParser fallback = new FallbackShoppingIntentParser(arkParser, ruleParser);

        ShoppingIntent intent = fallback.parse("只看京东索尼评分4.8以上的耳机，300以内，价格从低到高");
        assertTrue(intent.intentFallbackUsed(), "should fallback to rule when Ark not configured");
        assertEquals("耳机", intent.keyword());
        assertEquals(300.0, intent.maxPrice());
        assertEquals("索尼", intent.brand());
        assertEquals(List.of("京东-mock"), intent.platforms());
        assertEquals("price_asc", intent.sortBy());
        assertEquals(4.8, intent.minRating());
        assertFalse(intent.notices().isEmpty(), "should have fallback notice");
    }

    @Test
    void arkExplainerShouldFallbackWhenNotConfigured() {
        ArkClient dummyClient = new ArkClient(objectMapper, "", "", "https://ark.cn-beijing.volces.com/api/v3");
        ArkRecommendationExplainer arkExplainer = new ArkRecommendationExplainer(dummyClient, objectMapper);

        // Build a rule explanation
        RecommendationExplanation ruleExp = new RecommendationExplanation(
                85,
                List.of(new DecisionSignal("price", "价格", 90, "价格合理")),
                List.of(new RecommendationEvidence("price", "价格证据")),
                List.of("Mock 风险"),
                List.of(new ProductAnalysis("p1", "京东-mock", "测试商品", 1, 85,
                        List.of("优势1"), List.of("不足1"))));

        ShoppingIntent intent = ShoppingIntent.fromRule("运动鞋",
                new UserPreference(200.0, null, false, false, true, false, false));
        RecommendationExplanation result = arkExplainer.explain(ruleExp, intent,
                new ProductSearchResult(List.of(), Map.of(), null));

        assertTrue(result.explanationFallbackUsed(), "should fallback when Ark not configured");
        assertEquals("rule", result.explanationProvider());
        assertFalse(result.notices().isEmpty());
    }

    @Test
    void rewriteAnalysesShouldPreserveOriginalProductIds() {
        ObjectMapper om = new ObjectMapper();
        // Use a simulated ArkClient that returns a JSON with a wrong productId
        ArkClient fakeArk = new ArkClient(om, "fake-key", "fake-ep", "https://example.com") {
            @Override
            public com.fasterxml.jackson.databind.JsonNode chatJson(List<Map<String, Object>> messages) {
                // Return JSON with productId = "hijacked-id" — must be ignored
                String fakeResponse = """
                    {
                      "summaryReason": "Ark改写摘要",
                      "signals": [
                        {"key": "price", "label": "价格", "explanation": "Ark改写解释"}
                      ],
                      "evidence": [
                        {"type": "price", "content": "Ark改写证据"}
                      ],
                      "risks": ["Ark改写风险"],
                      "analyses": [
                        {
                          "productId": "hijacked-id",
                          "strengths": ["Ark改写优势"],
                          "weaknesses": ["Ark改写不足"]
                        }
                      ]
                    }""";
                try {
                    return om.readTree(fakeResponse);
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            }
        };

        ArkRecommendationExplainer explainer = new ArkRecommendationExplainer(fakeArk, om);
        var origAnalyses = List.of(
                new ProductAnalysis("real-id-001", "京东-mock", "商品A", 1, 88,
                        List.of("原始优势"), List.of("原始不足")));
        var ruleExp = new RecommendationExplanation(
                80,
                List.of(new DecisionSignal("price", "价格", 90, "原始解释")),
                List.of(new RecommendationEvidence("price", "原始证据")),
                List.of("原始风险"),
                origAnalyses);

        RecommendationExplanation result = explainer.explain(ruleExp,
                ShoppingIntent.fromRule("运动鞋", UserPreference.empty()),
                new ProductSearchResult(List.of(), Map.of(), null));

        // productId MUST remain the original
        assertEquals(1, result.productAnalyses().size());
        assertEquals("real-id-001", result.productAnalyses().get(0).productId(),
                "productId must never be changed by Ark");
        assertEquals("京东-mock", result.productAnalyses().get(0).platform(),
                "platform must never be changed by Ark");
        assertEquals("商品A", result.productAnalyses().get(0).title(),
                "title must never be changed by Ark");
        // Ark CAN rewrite text fields
        assertEquals("Ark改写摘要", result.summaryReason());
        assertEquals("Ark改写解释", result.decisionSignals().get(0).explanation());
        assertEquals("Ark改写优势", result.productAnalyses().get(0).strengths().get(0));
        assertEquals("ark", result.explanationProvider());
        assertFalse(result.explanationFallbackUsed());
    }

    @Test
    void shouldNormalizeOctetStreamWithJpegHeaderToImageJpeg() {
        // JPEG magic: FF D8
        byte[] jpegBytes = new byte[]{(byte) 0xFF, (byte) 0xD8, (byte) 0xFF, (byte) 0xE0, 0, 0, 0, 0};
        String result = ArkRecognitionProvider.normalizeContentType(jpegBytes, "application/octet-stream");
        assertEquals("image/jpeg", result,
                "JPEG header should override application/octet-stream");
    }

    @Test
    void shouldNormalizePngHeaderToImagePng() {
        byte[] pngBytes = new byte[]{(byte) 0x89, (byte) 0x50, (byte) 0x4E, (byte) 0x47, 0, 0, 0, 0};
        String result = ArkRecognitionProvider.normalizeContentType(pngBytes, "application/octet-stream");
        assertEquals("image/png", result,
                "PNG header should override application/octet-stream");
    }

    @Test
    void shouldDefaultToImageJpegWhenHeaderUnknown() {
        byte[] unknown = new byte[]{0, 0, 0, 0};
        String result = ArkRecognitionProvider.normalizeContentType(unknown, "application/octet-stream");
        assertEquals("image/jpeg", result,
                "Unknown header with invalid declared type should default to image/jpeg");
    }

    @Test
    void shouldUseDeclaredTypeWhenHeaderUnknownButTypeValid() {
        byte[] unknown = new byte[]{0, 0, 0, 0};
        String result = ArkRecognitionProvider.normalizeContentType(unknown, "image/png");
        assertEquals("image/png", result,
                "Valid declared type should be used when header is unknown");
    }
}
