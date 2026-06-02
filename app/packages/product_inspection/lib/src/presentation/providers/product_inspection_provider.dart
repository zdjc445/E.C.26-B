import 'package:app_core/app_core.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../domain/entities/price_history_entity.dart';
import '../../domain/entities/review_summary_entity.dart';
import '../../domain/usecases/get_price_history.dart';
import '../../domain/usecases/get_review_summary.dart';
import '../../data/datasources/product_inspection_remote_data_source.dart';
import '../../data/repositories/product_inspection_repo_impl.dart';

// ── Data sources ──────────────────────────────────────────
final _inspectionRemoteProvider = Provider<ProductInspectionRemoteDataSource>(
  (ref) => ProductInspectionRemoteDataSource(ref.read(appDioProvider)),
);

final _inspectionRepoProvider = Provider<ProductInspectionRepositoryImpl>(
  (ref) => ProductInspectionRepositoryImpl(ref.read(_inspectionRemoteProvider)),
);

// ── Use cases ─────────────────────────────────────────────

final getPriceHistoryUseCaseProvider = Provider<GetPriceHistory>(
  (ref) => GetPriceHistory(ref.read(_inspectionRepoProvider)),
);

final getReviewSummaryUseCaseProvider = Provider<GetReviewSummary>(
  (ref) => GetReviewSummary(ref.read(_inspectionRepoProvider)),
);

// ── State ─────────────────────────────────────────────────

/// UI state for the product inspection feature.
class ProductInspectionState {
  final PriceHistoryEntity? priceHistory;
  final ReviewSummaryEntity? reviewSummary;
  final bool isLoadingPrice;
  final bool isLoadingReview;
  final String? error;

  const ProductInspectionState({
    this.priceHistory,
    this.reviewSummary,
    this.isLoadingPrice = false,
    this.isLoadingReview = false,
    this.error,
  });

  ProductInspectionState copyWith({
    PriceHistoryEntity? priceHistory,
    ReviewSummaryEntity? reviewSummary,
    bool? isLoadingPrice,
    bool? isLoadingReview,
    String? error,
  }) {
    return ProductInspectionState(
      priceHistory: priceHistory ?? this.priceHistory,
      reviewSummary: reviewSummary ?? this.reviewSummary,
      isLoadingPrice: isLoadingPrice ?? this.isLoadingPrice,
      isLoadingReview: isLoadingReview ?? this.isLoadingReview,
      error: error,
    );
  }
}

class ProductInspectionNotifier extends StateNotifier<ProductInspectionState> {
  final GetPriceHistory _getPriceHistory;
  final GetReviewSummary _getReviewSummary;

  ProductInspectionNotifier(
    this._getPriceHistory,
    this._getReviewSummary,
  ) : super(const ProductInspectionState());

  Future<void> loadPriceHistory({
    required String platformProductId,
    int days = 90,
  }) async {
    state = state.copyWith(isLoadingPrice: true, error: null);
    final result = await _getPriceHistory(
      GetPriceHistoryParams(platformProductId: platformProductId, days: days),
    );
    result.fold(
      (failure) => state = state.copyWith(
        isLoadingPrice: false,
        error: _failureMessage(failure),
      ),
      (history) => state = state.copyWith(
        isLoadingPrice: false,
        priceHistory: history,
      ),
    );
  }

  Future<void> loadReviewSummary({
    required String platformProductId,
  }) async {
    state = state.copyWith(isLoadingReview: true, error: null);
    final result = await _getReviewSummary(
      GetReviewSummaryParams(platformProductId: platformProductId),
    );
    result.fold(
      (failure) => state = state.copyWith(
        isLoadingReview: false,
        error: _failureMessage(failure),
      ),
      (summary) => state = state.copyWith(
        isLoadingReview: false,
        reviewSummary: summary,
      ),
    );
  }

  /// Load both price history and review summary for a product.
  Future<void> loadAll({
    required String platformProductId,
    int days = 90,
  }) async {
    await loadPriceHistory(platformProductId: platformProductId, days: days);
    await loadReviewSummary(platformProductId: platformProductId);
  }

  void clearError() => state = state.copyWith(error: null);

  String _failureMessage(Failure failure) {
    return switch (failure) {
      ServerFailure(:final message) => message,
      NetworkFailure(:final message) => message,
      AuthFailure(:final message) => message,
      ValidationFailure(:final errors) => errors.values.join('；'),
      UnexpectedFailure(:final message) => message,
      CacheFailure(:final message) => message,
    };
  }
}

final productInspectionProvider =
    StateNotifierProvider<ProductInspectionNotifier, ProductInspectionState>(
        (ref) {
  return ProductInspectionNotifier(
    ref.read(getPriceHistoryUseCaseProvider),
    ref.read(getReviewSummaryUseCaseProvider),
  );
});
