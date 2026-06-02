import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../models/recognition_dto.dart';

/// Calls /api/recognitions endpoints via Dio.
class RecognitionRemoteDataSource {
  final Dio _dio;

  RecognitionRemoteDataSource(this._dio);

  /// POST /api/recognitions — submit an image for AI recognition.
  Future<RecognitionDto> recognizeProduct(String imageId) async {
    final resp = await _dio.post('/api/recognitions', data: {
      'imageId': imageId,
    });
    final apiResp = ApiResponse<RecognitionDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) =>
          RecognitionDto.fromJson(node as Map<String, dynamic>),
    );
    _assertSuccess(apiResp);
    return apiResp.data!;
  }

  /// PATCH /api/recognitions/{id}/attributes — update correction attributes.
  Future<RecognitionDto> updateAttributes({
    required String recognitionId,
    String? category,
    String? brand,
    String? model,
    Map<String, dynamic>? attributes,
  }) async {
    final body = <String, dynamic>{};
    if (category != null) body['category'] = category;
    if (brand != null) body['brand'] = brand;
    if (model != null) body['model'] = model;
    if (attributes != null) body['attributes'] = attributes;

    final resp = await _dio.patch(
      '/api/recognitions/$recognitionId/attributes',
      data: body,
    );
    final apiResp = ApiResponse<RecognitionDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) =>
          RecognitionDto.fromJson(node as Map<String, dynamic>),
    );
    _assertSuccess(apiResp);
    return apiResp.data!;
  }

  void _assertSuccess<T>(ApiResponse<T> resp) {
    if (!resp.isSuccess) {
      throw DioException(
        requestOptions: RequestOptions(path: ''),
        response: Response(
          requestOptions: RequestOptions(path: ''),
          statusCode: resp.code,
          data: {'code': resp.code, 'message': resp.message},
        ),
      );
    }
  }
}
