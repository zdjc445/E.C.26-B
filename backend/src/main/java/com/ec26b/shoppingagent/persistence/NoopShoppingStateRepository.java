package com.ec26b.shoppingagent.persistence;

import com.ec26b.shoppingagent.api.ApiModels.*;
import com.ec26b.shoppingagent.service.ShoppingService.UserAccount;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("!postgres")
public class NoopShoppingStateRepository implements ShoppingStateRepository {
    @Override
    public void saveUser(UserAccount user) {
    }

    @Override
    public void saveRefreshSession(String refreshTokenHash, long userId) {
    }

    @Override
    public void deleteRefreshSession(String refreshTokenHash) {
    }

    @Override
    public void saveImage(long userId, ImageDto image, boolean deleted) {
    }

    @Override
    public void saveRecognition(long userId, RecognitionDto recognition) {
    }

    @Override
    public void saveSearchTask(long userId, SearchTaskDto searchTask) {
    }

    @Override
    public void saveRefinement(long userId, RefineSearchTaskPayload refinement) {
    }

    @Override
    public void saveComparison(long userId, ComparisonDto comparison) {
    }

    @Override
    public void saveRecommendation(long userId, RecommendationDto recommendation, String userQuery) {
    }

    @Override
    public void saveFavorite(long userId, FavoriteDto favorite) {
    }

    @Override
    public void deleteFavorite(long userId, long favoriteId) {
    }

    @Override
    public void savePriceAlert(long userId, PriceAlertDto priceAlert) {
    }

    @Override
    public void deletePriceAlert(long userId, long priceAlertId) {
    }
}
