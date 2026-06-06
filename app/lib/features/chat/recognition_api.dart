import 'dart:convert';
import 'package:http/http.dart' as http;

/// API calls for recognition.
class RecognitionApi {
  final String baseUrl;

  const RecognitionApi({required this.baseUrl});

  /// Calls POST /api/recognition and returns the raw data map.
  Future<Map<String, dynamic>> recognizeImage(String imageId) async {
    final uri = Uri.parse('$baseUrl/api/recognition');
    final response = await http.post(
      uri,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'imageId': imageId}),
    );
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode == 200 && body['code'] == 0) {
      return body['data'] as Map<String, dynamic>;
    }
    throw Exception(body['message'] as String? ?? '识别失败');
  }

  Future<Map<String, dynamic>> updateAttributes(
      String recognitionId, Map<String, dynamic> payload) async {
    final uri =
        Uri.parse('$baseUrl/api/recognition/$recognitionId/attributes');
    final response = await http.patch(
      uri,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(payload),
    );
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode == 200 && body['code'] == 0) {
      return body['data'] as Map<String, dynamic>;
    }
    throw Exception(body['message'] as String? ?? '修正失败');
  }
}
