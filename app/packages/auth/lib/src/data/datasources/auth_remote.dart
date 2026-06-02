import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../models/auth_dto.dart';

/// Remote datasource: calls the /api/auth/* endpoints directly via Dio.
class AuthRemoteDataSource {
  final Dio _dio;

  AuthRemoteDataSource(this._dio);

  Future<AuthResponseDto> register({
    required String username,
    required String password,
    String? nickname,
  }) async {
    final resp = await _dio.post('/api/auth/register', data: {
      'username': username,
      'password': password,
      if (nickname != null) 'nickname': nickname,
    });
    final apiResp = ApiResponse<AuthResponseDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) => AuthResponseDto.fromJson(node as Map<String, dynamic>),
    );
    _assertSuccess(apiResp);
    return apiResp.data!;
  }

  Future<AuthResponseDto> login({
    required String username,
    required String password,
  }) async {
    final resp = await _dio.post('/api/auth/login', data: {
      'username': username,
      'password': password,
    });
    final apiResp = ApiResponse<AuthResponseDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) => AuthResponseDto.fromJson(node as Map<String, dynamic>),
    );
    _assertSuccess(apiResp);
    return apiResp.data!;
  }

  Future<RefreshResponseDto> refresh(String refreshToken) async {
    final resp = await _dio.post('/api/auth/refresh', data: {
      'refreshToken': refreshToken,
    });
    final apiResp = ApiResponse<RefreshResponseDto>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) => RefreshResponseDto.fromJson(node as Map<String, dynamic>),
    );
    _assertSuccess(apiResp);
    return apiResp.data!;
  }

  Future<void> logout(String refreshToken) async {
    await _dio.post('/api/auth/logout', data: {
      'refreshToken': refreshToken,
    });
  }

  Future<Map<String, dynamic>> getCurrentUser() async {
    final resp = await _dio.get('/api/auth/me');
    final apiResp = ApiResponse<Map<String, dynamic>>.fromJson(
      resp.data as Map<String, dynamic>,
      dataParser: (node) => Map<String, dynamic>.from(node as Map),
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
