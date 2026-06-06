package com.ec26b.shoppingagent.ai;

import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class RecognitionStore {

    private final Map<String, RecognitionResult> store = new ConcurrentHashMap<>();

    public void save(RecognitionResult result) {
        store.put(result.getRecognitionId(), result);
    }

    public Optional<RecognitionResult> findById(String recognitionId) {
        return Optional.ofNullable(store.get(recognitionId));
    }
}
