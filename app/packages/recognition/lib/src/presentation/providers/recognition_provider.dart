import 'package:app_core/app_core.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../domain/entities/recognition_entity.dart';
import '../../domain/usecases/recognize_product.dart';
import '../../domain/usecases/update_recognition_attrs.dart';
import '../../data/datasources/recognition_remote_datasource.dart';
import '../../data/repositories/recognition_repository_impl.dart';

// ── Data sources ──────────────────────────────────────────
final _recognitionRemoteProvider = Provider<RecognitionRemoteDataSource>(
  (ref) => RecognitionRemoteDataSource(ref.read(appDioProvider)),
);

final _recognitionRepoProvider = Provider<RecognitionRepositoryImpl>(
  (ref) => RecognitionRepositoryImpl(ref.read(_recognitionRemoteProvider)),
);

// ── Use cases ─────────────────────────────────────────────
final recognizeProductUseCaseProvider = Provider<RecognizeProduct>(
  (ref) => RecognizeProduct(ref.read(_recognitionRepoProvider)),
);

final updateRecognitionAttrsUseCaseProvider = Provider<UpdateRecognitionAttrs>(
  (ref) => UpdateRecognitionAttrs(ref.read(_recognitionRepoProvider)),
);

// ── Recognition state ────────────────────────────────────
enum RecognitionStatus { idle, loading, loaded, updating, error }

class RecognitionState {
  final RecognitionStatus status;
  final RecognitionEntity? recognition;
  final Map<String, dynamic> editingAttributes;
  final String? error;

  const RecognitionState({
    this.status = RecognitionStatus.idle,
    this.recognition,
    this.editingAttributes = const {},
    this.error,
  });

  RecognitionState copyWith({
    RecognitionStatus? status,
    RecognitionEntity? recognition,
    Map<String, dynamic>? editingAttributes,
    String? error,
  }) {
    return RecognitionState(
      status: status ?? this.status,
      recognition: recognition ?? this.recognition,
      editingAttributes: editingAttributes ?? this.editingAttributes,
      error: error,
    );
  }
}

class RecognitionNotifier extends StateNotifier<RecognitionState> {
  final RecognizeProduct _recognizeProduct;
  final UpdateRecognitionAttrs _updateAttrs;

  RecognitionNotifier({
    required RecognizeProduct recognizeProduct,
    required UpdateRecognitionAttrs updateAttrs,
  })  : _recognizeProduct = recognizeProduct,
        _updateAttrs = updateAttrs,
        super(const RecognitionState());

  /// Trigger recognition for the given imageId.
  Future<void> recognize(String imageId) async {
    state = state.copyWith(status: RecognitionStatus.loading, error: null);
    final result = await _recognizeProduct(imageId);
    result.fold(
      (failure) => state = state.copyWith(
        status: RecognitionStatus.error,
        error: _failureMessage(failure),
      ),
      (recognition) => state = state.copyWith(
        status: RecognitionStatus.loaded,
        recognition: recognition,
        editingAttributes: Map<String, dynamic>.from(recognition.attributes),
      ),
    );
  }

  /// Update a single editable attribute field locally (before submission).
  void setAttribute(String key, dynamic value) {
    final attrs = Map<String, dynamic>.from(state.editingAttributes);
    attrs[key] = value;
    state = state.copyWith(editingAttributes: attrs);
  }

  /// Set category locally.
  void setCategory(String category) {
    final r = state.recognition;
    if (r == null) return;
    state = state.copyWith(
      recognition: r.copyWith(category: category),
    );
  }

  /// Set brand locally.
  void setBrand(String brand) {
    final r = state.recognition;
    if (r == null) return;
    state = state.copyWith(
      recognition: r.copyWith(brand: brand),
    );
  }

  /// Set model locally.
  void setModel(String model) {
    final r = state.recognition;
    if (r == null) return;
    state = state.copyWith(
      recognition: r.copyWith(model: model),
    );
  }

  /// Submit attribute updates to the backend.
  Future<void> submitAttributeUpdates() async {
    final r = state.recognition;
    if (r == null) return;

    state = state.copyWith(status: RecognitionStatus.updating, error: null);
    final result = await _updateAttrs(UpdateRecognitionAttrsParams(
      recognitionId: r.recognitionId,
      category: r.category,
      brand: r.brand,
      model: r.model,
      attributes: state.editingAttributes,
    ));
    result.fold(
      (failure) => state = state.copyWith(
        status: RecognitionStatus.error,
        error: _failureMessage(failure),
      ),
      (updated) => state = state.copyWith(
        status: RecognitionStatus.loaded,
        recognition: updated,
        editingAttributes: Map<String, dynamic>.from(updated.attributes),
      ),
    );
  }

  void reset() {
    state = const RecognitionState();
  }

  String _failureMessage(Failure failure) {
    return switch (failure) {
      ServerFailure(:final message) => message,
      NetworkFailure(:final message) => message,
      ValidationFailure(:final errors) => errors.values.join('；'),
      UnexpectedFailure(:final message) => message,
      _ => '识别失败，请重试',
    };
  }
}

final recognitionProvider =
    StateNotifierProvider<RecognitionNotifier, RecognitionState>((ref) {
  return RecognitionNotifier(
    recognizeProduct: ref.read(recognizeProductUseCaseProvider),
    updateAttrs: ref.read(updateRecognitionAttrsUseCaseProvider),
  );
});
