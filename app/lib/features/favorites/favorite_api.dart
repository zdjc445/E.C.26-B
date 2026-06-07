import 'dart:convert';
import 'package:http/http.dart' as http;
import 'favorite_models.dart';

class FavoriteApi {
  final String baseUrl;

  const FavoriteApi({required this.baseUrl});

  Future<FavoriteItem> add(Map<String, dynamic> payload, {String? token}) async {
    final uri = Uri.parse('$baseUrl/api/favorites');
    final response = await http.post(uri,
        headers: _headers(token), body: jsonEncode(payload));
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode == 200 && body['code'] == 0) {
      return FavoriteItem.fromJson(body['data'] as Map<String, dynamic>);
    }
    throw Exception(body['message'] as String? ?? '收藏失败');
  }

  Future<List<FavoriteItem>> list({String? token}) async {
    final uri = Uri.parse('$baseUrl/api/favorites');
    final response = await http.get(uri, headers: _headers(token));
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode == 200 && body['code'] == 0) {
      final data = body['data'] as Map<String, dynamic>;
      return (data['favorites'] as List)
          .map((m) => FavoriteItem.fromJson(m as Map<String, dynamic>))
          .toList();
    }
    throw Exception(body['message'] as String? ?? '获取收藏失败');
  }

  Future<void> delete(String productId, {String? token}) async {
    final uri = Uri.parse('$baseUrl/api/favorites/$productId');
    final response = await http.delete(uri, headers: _headers(token));
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode != 200 || body['code'] != 0) {
      throw Exception(body['message'] as String? ?? '取消收藏失败');
    }
  }

  Map<String, String> _headers(String? token) {
    return {
      'Content-Type': 'application/json',
      if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
    };
  }
}
