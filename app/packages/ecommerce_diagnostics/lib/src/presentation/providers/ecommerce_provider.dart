import 'package:app_core/app_core.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../domain/entities/ecommerce_status_entity.dart';
import '../../domain/entities/ecommerce_diagnostics_entity.dart';
import '../../domain/usecases/get_ecommerce_status.dart';
import '../../domain/usecases/run_diagnostics.dart';
import '../../data/datasources/ecommerce_remote_datasource.dart';
import '../../data/repositories/ecommerce_repository_impl.dart';

// ── Data sources ──────────────────────────────────────────
// No auth needed for ecommerce endpoints, but we need a Dio instance.
final _ecomRemoteProvider = Provider<EcommerceRemoteDataSource>(
  (ref) => EcommerceRemoteDataSource(ref.read(appDioProvider)),
);

final _ecomRepoProvider = Provider<EcommerceRepositoryImpl>(
  (ref) => EcommerceRepositoryImpl(ref.read(_ecomRemoteProvider)),
);

// ── Use cases ─────────────────────────────────────────────
final getEcommerceStatusProvider = Provider<GetEcommerceStatus>(
  (ref) => GetEcommerceStatus(ref.read(_ecomRepoProvider)),
);

final runDiagnosticsProvider = Provider<RunDiagnostics>(
  (ref) => RunDiagnostics(ref.read(_ecomRepoProvider)),
);

// ── E-commerce state ──────────────────────────────────────
enum EcommerceLoadStatus { initial, loading, loaded, error }

class EcommerceState {
  final EcommerceLoadStatus status;
  final EcommerceStatusEntity? statusData;
  final EcommerceDiagnosticsEntity? diagnosticsData;
  final bool diagnosticsRunning;
  final String? error;
  final String? diagnosticsError;

  const EcommerceState({
    this.status = EcommerceLoadStatus.initial,
    this.statusData,
    this.diagnosticsData,
    this.diagnosticsRunning = false,
    this.error,
    this.diagnosticsError,
  });

  EcommerceState copyWith({
    EcommerceLoadStatus? status,
    EcommerceStatusEntity? statusData,
    EcommerceDiagnosticsEntity? diagnosticsData,
    bool? diagnosticsRunning,
    String? error,
    String? diagnosticsError,
  }) {
    return EcommerceState(
      status: status ?? this.status,
      statusData: statusData ?? this.statusData,
      diagnosticsData: diagnosticsData ?? this.diagnosticsData,
      diagnosticsRunning: diagnosticsRunning ?? this.diagnosticsRunning,
      error: error,
      diagnosticsError: diagnosticsError,
    );
  }
}

class EcommerceNotifier extends StateNotifier<EcommerceState> {
  final GetEcommerceStatus _getStatus;
  final RunDiagnostics _runDiag;

  EcommerceNotifier({
    required GetEcommerceStatus getStatus,
    required RunDiagnostics runDiag,
  })  : _getStatus = getStatus,
        _runDiag = runDiag,
        super(const EcommerceState());

  /// Load the e-commerce status.
  Future<void> loadStatus() async {
    state = state.copyWith(status: EcommerceLoadStatus.loading, error: null);
    final result = await _getStatus();
    result.fold(
      (failure) => state = state.copyWith(
        status: EcommerceLoadStatus.error,
        error: _failureMessage(failure),
      ),
      (data) => state = state.copyWith(
        status: EcommerceLoadStatus.loaded,
        statusData: data,
      ),
    );
  }

  /// Run diagnostics against configured providers.
  Future<void> runDiagnostics({
    String query = '',
    int pageSize = 3,
    String? platforms,
  }) async {
    state = state.copyWith(
      diagnosticsRunning: true,
      diagnosticsError: null,
    );
    final result = await _runDiag(RunDiagnosticsParams(
      query: query,
      pageSize: pageSize,
      platforms: platforms,
    ));
    result.fold(
      (failure) => state = state.copyWith(
        diagnosticsRunning: false,
        diagnosticsError: _failureMessage(failure),
      ),
      (data) => state = state.copyWith(
        diagnosticsRunning: false,
        diagnosticsData: data,
      ),
    );
  }

  void clearError() =>
      state = state.copyWith(error: null, diagnosticsError: null);

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

final ecommerceProvider =
    StateNotifierProvider<EcommerceNotifier, EcommerceState>((ref) {
  return EcommerceNotifier(
    getStatus: ref.read(getEcommerceStatusProvider),
    runDiag: ref.read(runDiagnosticsProvider),
  );
});
