import 'package:app_core/app_core.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../domain/entities/recommendation_entity.dart';
import '../../domain/usecases/create_recommendation.dart';
import '../../data/datasources/recommendation_remote_data_source.dart';
import '../../data/repositories/recommendation_repo_impl.dart';

// ── Data sources ──────────────────────────────────────────
final _recommendationRemoteProvider = Provider<RecommendationRemoteDataSource>(
  (ref) => RecommendationRemoteDataSource(ref.read(appDioProvider)),
);

final _recommendationRepoProvider = Provider<RecommendationRepositoryImpl>(
  (ref) =>
      RecommendationRepositoryImpl(ref.read(_recommendationRemoteProvider)),
);

// ── Use cases ─────────────────────────────────────────────

final createRecommendationUseCaseProvider = Provider<CreateRecommendation>(
  (ref) => CreateRecommendation(ref.read(_recommendationRepoProvider)),
);

// ── State ─────────────────────────────────────────────────

/// UI state for the recommendation feature.
class RecommendationState {
  final RecommendationEntity? recommendation;
  final bool isLoading;
  final String? error;

  const RecommendationState({
    this.recommendation,
    this.isLoading = false,
    this.error,
  });

  RecommendationState copyWith({
    RecommendationEntity? recommendation,
    bool? isLoading,
    String? error,
  }) {
    return RecommendationState(
      recommendation: recommendation ?? this.recommendation,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

class RecommendationNotifier extends StateNotifier<RecommendationState> {
  final CreateRecommendation _createRecommendation;

  RecommendationNotifier(this._createRecommendation)
      : super(const RecommendationState());

  Future<void> createRecommendation({
    required String searchTaskId,
    required String userQuery,
    required List<String> candidateIds,
  }) async {
    state = state.copyWith(isLoading: true, error: null);
    final result = await _createRecommendation(
      CreateRecommendationParams(
        searchTaskId: searchTaskId,
        userQuery: userQuery,
        candidateIds: candidateIds,
      ),
    );
    result.fold(
      (failure) => state = state.copyWith(
        isLoading: false,
        error: _failureMessage(failure),
      ),
      (recommendation) => state = RecommendationState(
        recommendation: recommendation,
        isLoading: false,
      ),
    );
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

final recommendationProvider =
    StateNotifierProvider<RecommendationNotifier, RecommendationState>((ref) {
  return RecommendationNotifier(ref.read(createRecommendationUseCaseProvider));
});
