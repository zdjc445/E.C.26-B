import 'dart:convert';
import 'package:http/http.dart' as http;
import 'price_alert_models.dart';

class PriceAlertApi {
  final String baseUrl;

  const PriceAlertApi({required this.baseUrl});

  Future<PriceAlertItem> create(Map<String, dynamic> payload, {String? token}) async {
    final uri = Uri.parse('$baseUrl/api/price-alerts');
    final response = await http.post(uri,
        headers: _headers(token), body: jsonEncode(payload));
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode == 200 && body['code'] == 0) {
      return PriceAlertItem.fromJson(body['data'] as Map<String, dynamic>);
    }
    throw Exception(body['message'] as String? ?? '创建提醒失败');
  }

  Future<List<PriceAlertItem>> list({String? token}) async {
    final uri = Uri.parse('$baseUrl/api/price-alerts');
    final response = await http.get(uri, headers: _headers(token));
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode == 200 && body['code'] == 0) {
      final data = body['data'] as Map<String, dynamic>;
      return (data['alerts'] as List)
          .map((m) => PriceAlertItem.fromJson(m as Map<String, dynamic>))
          .toList();
    }
    throw Exception(body['message'] as String? ?? '获取提醒失败');
  }

  Future<void> delete(int alertId, {String? token}) async {
    final uri = Uri.parse('$baseUrl/api/price-alerts/$alertId');
    final response = await http.delete(uri, headers: _headers(token));
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode != 200 || body['code'] != 0) {
      throw Exception(body['message'] as String? ?? '删除提醒失败');
    }
  }

  Future<PriceAlertCheckResult> check({String? token}) async {
    final uri = Uri.parse('$baseUrl/api/price-alerts/check');
    final response = await http.post(uri, headers: _headers(token));
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode == 200 && body['code'] == 0) {
      return PriceAlertCheckResult.fromJson(body['data'] as Map<String, dynamic>);
    }
    throw Exception(body['message'] as String? ?? '检测失败');
  }

  Map<String, String> _headers(String? token) {
    return {
      'Content-Type': 'application/json',
      if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
    };
  }
}
