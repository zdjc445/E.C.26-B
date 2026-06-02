import 'package:app_core/app_core.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../domain/entities/comparison_entity.dart';
import '../../domain/usecases/create_comparison.dart';
import '../../data/datasources/comparison_remote_data_source.dart';
import '../../data/repositories/comparison_repo_impl.dart';

// ── Data sources ──────────────────────────────────────────
final _comparisonRemoteProvider = Provider<ComparisonRemoteDataSource>(
  (ref) => ComparisonRemoteDataSource(ref.read(appDioProvider)),
);

final _comparisonRepoProvider = Provider<ComparisonRepositoryImpl>(
  (ref) => ComparisonRepositoryImpl(ref.read(_comparisonRemoteProvider)),
);

// ── Use cases ─────────────────────────────────────────────

final createComparisonUseCaseProvider = Provider<CreateComparison>(
  (ref) => CreateComparison(ref.read(_comparisonRepoProvider)),
);

// ── State ─────────────────────────────────────────────────

/// UI state for the comparison feature.
class ComparisonState {
  final ComparisonEntity? comparison;
  final bool isLoading;
  final String? error;

  const ComparisonState({this.comparison, this.isLoading = false, this.error});

  ComparisonState copyWith({
    ComparisonEntity? comparison,
    bool? isLoading,
    String? error,
  }) {
    return ComparisonState(
      comparison: comparison ?? this.comparison,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

class ComparisonNotifier extends StateNotifier<ComparisonState> {
  final CreateComparison _createComparison;

  ComparisonNotifier(this._createComparison) : super(const ComparisonState());

  Future<void> createComparison({
    required String searchTaskId,
    required List<String> platformProductIds,
  }) async {
    state = state.copyWith(isLoading: true, error: null);
    final result = await _createComparison(
      CreateComparisonParams(
        searchTaskId: searchTaskId,
        platformProductIds: platformProductIds,
      ),
    );
    result.fold(
      (failure) => state = state.copyWith(
        isLoading: false,
        error: _failureMessage(failure),
      ),
      (comparison) => state = ComparisonState(
        comparison: comparison,
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

final comparisonProvider =
    StateNotifierProvider<ComparisonNotifier, ComparisonState>((ref) {
  return ComparisonNotifier(ref.read(createComparisonUseCaseProvider));
});
