import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../models/image_dto.dart';

/// Calls POST /api/images (multipart upload) via Dio.
class ImageRemoteDataSource {
  final Dio _dio;

  ImageRemoteDataSource(this._dio);

  /// Upload an image file to the backend and return the resulting DTO.
  Future<ImageDto> uploadImage(String filePath) async {
    final formData = FormData.fromMap({
      'file': await MultipartFile.fromFile(filePath),
    });

    final resp = await _dio.post(
      '/api/images',
      data: formData,
      options: Options(
        headers: {'Content-Type': 'multipart/form-data'},
      ),
    );

    final apiResp = ApiResponse<ImageDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) => ImageDto.fromJson(node as Map<String, dynamic>),
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
