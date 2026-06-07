import 'dart:convert';
import 'package:http/http.dart' as http;
import 'auth_models.dart';

class AuthApi {
  final String baseUrl;

  const AuthApi({required this.baseUrl});

  Future<AuthSession> register(String username, String password, String? displayName) async {
    return _postAuth('/api/auth/register', {
      'username': username,
      'password': password,
      if (displayName != null && displayName.isNotEmpty) 'displayName': displayName,
    });
  }

  Future<AuthSession> login(String username, String password) async {
    return _postAuth('/api/auth/login', {
      'username': username,
      'password': password,
    });
  }

  Future<AuthSession> _postAuth(String path, Map<String, dynamic> body) async {
    final uri = Uri.parse('$baseUrl$path');
    final response = await http.post(uri,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(body));
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode == 200 && decoded['code'] == 0) {
      return AuthSession.fromJson(decoded['data'] as Map<String, dynamic>);
    }
    throw AuthApiException(decoded['message'] as String? ?? '请求失败',
        code: decoded['code'] as int? ?? 0);
  }

  Future<CurrentUserInfo> me(String? token) async {
    final uri = Uri.parse('$baseUrl/api/auth/me');
    final response = await http.get(uri,
        headers: token == null || token.isEmpty ? const {} : {'Authorization': 'Bearer $token'});
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode == 200 && decoded['code'] == 0) {
      return CurrentUserInfo.fromJson(decoded['data'] as Map<String, dynamic>);
    }
    throw AuthApiException(decoded['message'] as String? ?? '获取当前用户失败',
        code: decoded['code'] as int? ?? 0);
  }
}

class AuthApiException implements Exception {
  final String message;
  final int code;
  const AuthApiException(this.message, {required this.code});

  @override
  String toString() => message;
}
