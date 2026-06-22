package com.ec26b.shoppingagent.product;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Locale;

/**
 * Primary product source for the public sample dataset.
 */
@Primary
@Component
public class CompositeProductSourceProvider implements ProductSourceProvider {

    public static final String MODE_PUBLIC_DATASET_ONLY = "public-dataset-only";
    public static final String MODE_PUBLIC_DATASET_PLATFORMS = "public-dataset-platforms";

    static final List<String> DOMESTIC_PLATFORMS = List.of(
            "拼多多-mock", "淘宝-mock", "天猫-mock", "京东-mock"
    );

    private final PublicDatasetProductSourceProvider publicDataset;
    private final String mode;

    @Autowired
    public CompositeProductSourceProvider(
            PublicDatasetProductSourceProvider publicDataset,
            @Value("${app.product-source.mode:public-dataset-platforms}") String mode) {
        this.publicDataset = publicDataset;
        this.mode = normalizeMode(mode);
    }

    public CompositeProductSourceProvider(PublicDatasetProductSourceProvider publicDataset) {
        this(publicDataset, MODE_PUBLIC_DATASET_PLATFORMS);
    }

    @Override
    public ProductSearchResult search(ProductSearchQuery query) {
        if (MODE_PUBLIC_DATASET_ONLY.equals(mode)) {
            return publicDataset.search(query);
        }
        return publicDataset.searchWithPlatformVariants(query, DOMESTIC_PLATFORMS);
    }

    @Override
    public String sourceName() {
        if (MODE_PUBLIC_DATASET_ONLY.equals(mode)) {
            return publicDataset.sourceName();
        }
        return MODE_PUBLIC_DATASET_PLATFORMS;
    }

    private static String normalizeMode(String mode) {
        String normalized = mode == null ? "" : mode.trim().toLowerCase(Locale.ROOT);
        if (MODE_PUBLIC_DATASET_ONLY.equals(normalized)) {
            return MODE_PUBLIC_DATASET_ONLY;
        }
        return MODE_PUBLIC_DATASET_PLATFORMS;
    }
}
