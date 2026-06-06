import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'chat_models.dart';

/// Low-level HTTP calls for the chat feature.
class ChatApi {
  final String baseUrl;

  const ChatApi({required this.baseUrl});

  Future<ImageUploadResult> uploadImage(File imageFile) async {
    final uri = Uri.parse('$baseUrl/api/images/upload');
    final request = http.MultipartRequest('POST', uri);
    request.files.add(await http.MultipartFile.fromPath('file', imageFile.path));
    final streamed = await request.send();
    final response = await http.Response.fromStream(streamed);
    final body = jsonDecode(response.body) as Map<String, dynamic>;

    if (response.statusCode == 200 && body['code'] == 0) {
      return ImageUploadResult.fromJson(body['data'] as Map<String, dynamic>);
    }
    throw ChatApiException(body['message'] as String? ?? '上传失败');
  }

  Future<SessionResult> createSession() async {
    final uri = Uri.parse('$baseUrl/api/chat/sessions');
    final response = await http.post(uri);
    final body = jsonDecode(response.body) as Map<String, dynamic>;

    if (response.statusCode == 200 && body['code'] == 0) {
      return SessionResult.fromJson(body['data'] as Map<String, dynamic>);
    }
    throw ChatApiException(body['message'] as String? ?? '创建会话失败');
  }

  Future<AgentReply> sendMessage({
    required String sessionId,
    String? text,
    List<String>? imageIds,
    List<String>? selectedOptionIds,
  }) async {
    final uri = Uri.parse('$baseUrl/api/chat/sessions/$sessionId/messages');
    final payload = <String, dynamic>{
      'text': text ?? '',
      'imageIds': imageIds ?? [],
      'selectedOptionIds': selectedOptionIds ?? [],
    };
    final response = await http.post(
      uri,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(payload),
    );
    final body = jsonDecode(response.body) as Map<String, dynamic>;

    if (response.statusCode == 200 && body['code'] == 0) {
      return AgentReply.fromJson(body['data'] as Map<String, dynamic>);
    }
    throw ChatApiException(body['message'] as String? ?? '发送消息失败');
  }
}

class ChatApiException implements Exception {
  final String message;
  const ChatApiException(this.message);

  @override
  String toString() => message;
}
