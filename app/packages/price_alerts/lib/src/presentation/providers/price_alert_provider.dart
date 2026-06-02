import 'package:app_core/app_core.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../domain/entities/price_alert_entity.dart';
import '../../domain/usecases/create_alert.dart';
import '../../domain/usecases/update_alert.dart';
import '../../domain/usecases/delete_alert.dart';
import '../../domain/usecases/list_alerts.dart';
import '../../data/datasources/price_alert_remote_datasource.dart';
import '../../data/repositories/price_alert_repository_impl.dart';

// ── Data sources ──────────────────────────────────────────
final _alertRemoteProvider = Provider<PriceAlertRemoteDataSource>(
  (ref) => PriceAlertRemoteDataSource(ref.read(appDioProvider)),
);

final _alertRepoProvider = Provider<PriceAlertRepositoryImpl>(
  (ref) => PriceAlertRepositoryImpl(ref.read(_alertRemoteProvider)),
);

// ── Use cases ─────────────────────────────────────────────
final createAlertProvider = Provider<CreateAlert>(
  (ref) => CreateAlert(ref.read(_alertRepoProvider)),
);

final updateAlertProvider = Provider<UpdateAlert>(
  (ref) => UpdateAlert(ref.read(_alertRepoProvider)),
);

final deleteAlertProvider = Provider<DeleteAlert>(
  (ref) => DeleteAlert(ref.read(_alertRepoProvider)),
);

final listAlertsProvider = Provider<ListAlerts>(
  (ref) => ListAlerts(ref.read(_alertRepoProvider)),
);

// ── Price alerts state ────────────────────────────────────
enum AlertsLoadStatus { initial, loading, loaded, error, empty }

class PriceAlertsState {
  final AlertsLoadStatus status;
  final List<PriceAlertEntity> alerts;
  final int page;
  final int total;
  final String? error;
  final bool hasMore;
  final String? actionError;

  const PriceAlertsState({
    this.status = AlertsLoadStatus.initial,
    this.alerts = const [],
    this.page = 1,
    this.total = 0,
    this.error,
    this.hasMore = true,
    this.actionError,
  });

  PriceAlertsState copyWith({
    AlertsLoadStatus? status,
    List<PriceAlertEntity>? alerts,
    int? page,
    int? total,
    String? error,
    bool? hasMore,
    String? actionError,
  }) {
    return PriceAlertsState(
      status: status ?? this.status,
      alerts: alerts ?? this.alerts,
      page: page ?? this.page,
      total: total ?? this.total,
      error: error,
      hasMore: hasMore ?? this.hasMore,
      actionError: actionError,
    );
  }
}

class PriceAlertNotifier extends StateNotifier<PriceAlertsState> {
  final CreateAlert _createAlert;
  final UpdateAlert _updateAlert;
  final DeleteAlert _deleteAlert;
  final ListAlerts _listAlerts;

  PriceAlertNotifier({
    required CreateAlert createAlert,
    required UpdateAlert updateAlert,
    required DeleteAlert deleteAlert,
    required ListAlerts listAlerts,
  })  : _createAlert = createAlert,
        _updateAlert = updateAlert,
        _deleteAlert = deleteAlert,
        _listAlerts = listAlerts,
        super(const PriceAlertsState());

  /// Load the first page of price alerts.
  Future<void> loadAlerts() async {
    state = state.copyWith(status: AlertsLoadStatus.loading, error: null);
    final result = await _listAlerts(const ListAlertsParams(page: 1));
    result.fold(
      (failure) => state = state.copyWith(
        status: AlertsLoadStatus.error,
        error: _failureMessage(failure),
      ),
      (data) => state = PriceAlertsState(
        status: data.items.isEmpty
            ? AlertsLoadStatus.empty
            : AlertsLoadStatus.loaded,
        alerts: data.items,
        page: data.page,
        total: data.total,
        hasMore: data.items.length >= data.pageSize &&
            data.items.length < data.total,
      ),
    );
  }

  /// Load the next page (append to current list).
  Future<void> loadMore() async {
    if (!state.hasMore || state.status == AlertsLoadStatus.loading) return;
    final nextPage = state.page + 1;
    state = state.copyWith(status: AlertsLoadStatus.loading);
    final result =
        await _listAlerts(ListAlertsParams(page: nextPage, pageSize: 20));
    result.fold(
      (failure) => state = state.copyWith(
        status: AlertsLoadStatus.loaded,
        error: _failureMessage(failure),
      ),
      (data) {
        final allItems = [...state.alerts, ...data.items];
        state = state.copyWith(
          status: AlertsLoadStatus.loaded,
          alerts: allItems,
          page: data.page,
          total: data.total,
          hasMore: data.items.length >= data.pageSize &&
              allItems.length < data.total,
        );
      },
    );
  }

  /// Create a new price alert.
  Future<bool> createAlert({
    required String platformProductId,
    required Money targetPrice,
    bool enabled = true,
  }) async {
    final result = await _createAlert(CreateAlertParams(
      platformProductId: platformProductId,
      targetPrice: targetPrice,
      enabled: enabled,
    ));
    bool success = false;
    result.fold(
      (failure) =>
          state = state.copyWith(actionError: _failureMessage(failure)),
      (alert) {
        state = state.copyWith(
          alerts: [alert, ...state.alerts],
          total: state.total + 1,
          status: AlertsLoadStatus.loaded,
          actionError: null,
        );
        success = true;
      },
    );
    return success;
  }

  /// Update an existing price alert.
  Future<bool> updateAlert({
    required String priceAlertId,
    Money? targetPrice,
    bool? enabled,
  }) async {
    final result = await _updateAlert(UpdateAlertParams(
      priceAlertId: priceAlertId,
      targetPrice: targetPrice,
      enabled: enabled,
    ));
    bool success = false;
    result.fold(
      (failure) =>
          state = state.copyWith(actionError: _failureMessage(failure)),
      (updatedAlert) {
        state = state.copyWith(
          alerts: state.alerts.map((a) {
            return a.priceAlertId == priceAlertId ? updatedAlert : a;
          }).toList(),
          actionError: null,
        );
        success = true;
      },
    );
    return success;
  }

  /// Delete a price alert.
  Future<bool> deleteAlert(String priceAlertId) async {
    final previousAlerts = List<PriceAlertEntity>.from(state.alerts);
    state = state.copyWith(
      alerts:
          state.alerts.where((a) => a.priceAlertId != priceAlertId).toList(),
      total: state.total - 1,
    );
    if (state.alerts.isEmpty) {
      state = state.copyWith(status: AlertsLoadStatus.empty);
    }

    final result = await _deleteAlert(priceAlertId);
    bool success = true;
    result.fold(
      (failure) {
        state = state.copyWith(
          alerts: previousAlerts,
          total: state.total + 1,
          actionError: _failureMessage(failure),
        );
        success = false;
      },
      (_) {},
    );
    return success;
  }

  void clearError() => state = state.copyWith(error: null, actionError: null);

  void clearActionError() => state = state.copyWith(actionError: null);

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

final priceAlertProvider =
    StateNotifierProvider<PriceAlertNotifier, PriceAlertsState>((ref) {
  return PriceAlertNotifier(
    createAlert: ref.read(createAlertProvider),
    updateAlert: ref.read(updateAlertProvider),
    deleteAlert: ref.read(deleteAlertProvider),
    listAlerts: ref.read(listAlertsProvider),
  );
});
