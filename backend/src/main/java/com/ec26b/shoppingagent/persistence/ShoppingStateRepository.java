package com.ec26b.shoppingagent.persistence;

import com.ec26b.shoppingagent.api.ApiModels.*;
import com.ec26b.shoppingagent.service.ShoppingService.UserAccount;

public interface ShoppingStateRepository {
    void saveUser(UserAccount user);

    void saveRefreshSession(String refreshTokenHash, long userId);

    void deleteRefreshSession(String refreshTokenHash);

    void saveImage(long userId, ImageDto image, boolean deleted);

    void saveRecognition(long userId, RecognitionDto recognition);

    void saveSearchTask(long userId, SearchTaskDto searchTask);

    void saveRefinement(long userId, RefineSearchTaskPayload refinement);

    void saveComparison(long userId, ComparisonDto comparison);

    void saveRecommendation(long userId, RecommendationDto recommendation, String userQuery);

    void saveFavorite(long userId, FavoriteDto favorite);

    void deleteFavorite(long userId, long favoriteId);

    void savePriceAlert(long userId, PriceAlertDto priceAlert);

    void deletePriceAlert(long userId, long priceAlertId);
}
