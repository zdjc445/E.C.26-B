import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;

class VoiceTranscription {
  final String text;
  final String provider;
  final bool fallbackUsed;
  final String? notice;

  const VoiceTranscription({
    required this.text,
    required this.provider,
    required this.fallbackUsed,
    this.notice,
  });

  factory VoiceTranscription.fromJson(Map<String, dynamic> json) {
    return VoiceTranscription(
      text: json['text'] as String? ?? '',
      provider: json['provider'] as String? ?? 'mock',
      fallbackUsed: json['fallbackUsed'] as bool? ?? false,
      notice: json['notice'] as String?,
    );
  }
}

class VoiceApi {
  final String baseUrl;

  const VoiceApi({required this.baseUrl});

  /// Sends raw audio bytes (preferred when synthesising directly from the
  /// process, e.g. captured by `record` plugin or fake byte buffer used in tests).
  Future<VoiceTranscription> transcribeBytes(List<int> bytes, {
    String filename = 'voice.m4a',
    String contentType = 'audio/m4a',
  }) async {
    final uri = Uri.parse('$baseUrl/api/voice/transcribe');
    final request = http.MultipartRequest('POST', uri)
      ..files.add(http.MultipartFile.fromBytes('file', bytes,
          filename: filename));
    final streamed = await request.send();
    final response = await http.Response.fromStream(streamed);
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode == 200 && body['code'] == 0) {
      return VoiceTranscription.fromJson(body['data'] as Map<String, dynamic>);
    }
    throw Exception(body['message'] as String? ?? '语音转写失败');
  }

  Future<VoiceTranscription> transcribeFile(File file) async {
    return transcribeBytes(await file.readAsBytes(),
        filename: file.uri.pathSegments.last);
  }
}
