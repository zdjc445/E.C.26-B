package com.ec26b.shoppingagent.ai;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public class RecognitionResult {

    private final String recognitionId;
    private final String imageId;
    private String category;
    private String brand;
    private String model;
    private List<String> keywords;
    private Map<String, Object> attributes;
    private double confidence;
    private String aiProvider;
    private boolean fallbackUsed;
    private String explanation;
    private List<String> notices;
    private OffsetDateTime createdAt;

    public RecognitionResult(String imageId, String category, String brand, String model,
                             List<String> keywords, Map<String, Object> attributes,
                             double confidence, String aiProvider, boolean fallbackUsed,
                             String explanation, List<String> notices) {
        this.recognitionId = UUID.randomUUID().toString();
        this.imageId = imageId;
        this.category = category;
        this.brand = brand;
        this.model = model;
        this.keywords = keywords != null ? new ArrayList<>(keywords) : new ArrayList<>();
        this.attributes = attributes != null ? new LinkedHashMap<>(attributes) : new LinkedHashMap<>();
        this.confidence = confidence;
        this.aiProvider = aiProvider;
        this.fallbackUsed = fallbackUsed;
        this.explanation = explanation;
        this.notices = notices != null ? new ArrayList<>(notices) : new ArrayList<>();
        this.createdAt = OffsetDateTime.now();
    }

    // Getters
    public String getRecognitionId() { return recognitionId; }
    public String getImageId() { return imageId; }
    public String getCategory() { return category; }
    public String getBrand() { return brand; }
    public String getModel() { return model; }
    public List<String> getKeywords() { return List.copyOf(keywords); }
    public Map<String, Object> getAttributes() { return Map.copyOf(attributes); }
    public double getConfidence() { return confidence; }
    public String getAiProvider() { return aiProvider; }
    public boolean isFallbackUsed() { return fallbackUsed; }
    public String getExplanation() { return explanation; }
    public List<String> getNotices() { return List.copyOf(notices); }
    public OffsetDateTime getCreatedAt() { return createdAt; }

    // Mutation for correction
    public void setCategory(String category) { this.category = category; }
    public void setBrand(String brand) { this.brand = brand; }
    public void setModel(String model) { this.model = model; }
    public void setKeywords(List<String> keywords) { this.keywords = new ArrayList<>(keywords); }
    public void setAttributes(Map<String, Object> attributes) { this.attributes = new LinkedHashMap<>(attributes); }
    public void setAiProvider(String aiProvider) { this.aiProvider = aiProvider; }
    public void setFallbackUsed(boolean fallbackUsed) { this.fallbackUsed = fallbackUsed; }
    public void setExplanation(String explanation) { this.explanation = explanation; }
    public void setNotices(List<String> notices) { this.notices = new ArrayList<>(notices); }
    public void addNotice(String notice) { this.notices.add(notice); }
    public void setCreatedAt(OffsetDateTime createdAt) { this.createdAt = createdAt; }
}
