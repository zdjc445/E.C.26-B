package com.ec26b.shoppingagent.product;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class CategoryResolverTest {

    private final CategoryResolver resolver = CategoryResolver.defaultResolver();

    @Test
    void shouldResolveHeadsetAliasesToHeadphones() {
        assertEquals("耳机", resolver.resolveName("头戴式蓝牙耳机"));
        assertEquals("耳机", resolver.resolveName("真无线蓝牙耳机"));
    }

    @Test
    void shouldResolveShoeAliasesToRunningShoes() {
        assertEquals("运动鞋", resolver.resolveName("跑鞋"));
    }

    @Test
    void shouldResolveHairDryerAliases() {
        assertEquals("吹风机", resolver.resolveName("电吹风"));
    }

    @Test
    void shouldResolveBackpackAliases() {
        assertEquals("背包", resolver.resolveName("双肩包"));
    }

    @Test
    void shouldResolveSmartwatchAliases() {
        assertEquals("智能手表", resolver.resolveName("运动手表"));
    }

    @Test
    void shouldReturnNullForUnknownText() {
        assertNull(resolver.resolveName("无法识别的东西"));
    }

    @Test
    void shouldExposeCategoryAttributes() {
        assertTrue(resolver.attributesFor("耳机").contains("降噪"));
        assertTrue(resolver.attributesFor("耳机").contains("续航"));
    }

    @Test
    void shouldExposeSupportedCategoryNames() {
        assertTrue(resolver.supportedCategoryNames().contains("运动鞋"));
        assertTrue(resolver.supportedCategoryNames().contains("智能手表"));
    }
}
