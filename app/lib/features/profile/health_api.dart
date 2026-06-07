import 'dart:convert';
import 'package:http/http.dart' as http;

class HealthStatus {
  final String status;
  final String app;
  final String stage;
  final String aiProvider;
  final String chatHistoryStore;
  final bool authEnabled;
  final String ecommerceProvider;
  final String voiceProvider;
  final String timestamp;

  const HealthStatus({
    required this.status,
    required this.app,
    required this.stage,
    required this.aiProvider,
    required this.chatHistoryStore,
    required this.authEnabled,
    required this.ecommerceProvider,
    required this.voiceProvider,
    required this.timestamp,
  });

  factory HealthStatus.fromJson(Map<String, dynamic> json) {
    return HealthStatus(
      status: json['status'] as String? ?? 'unknown',
      app: json['app'] as String? ?? 'unknown',
      stage: json['stage'] as String? ?? 'unknown',
      aiProvider: json['aiProvider'] as String? ?? 'unknown',
      chatHistoryStore: json['chatHistoryStore'] as String? ?? 'unknown',
      authEnabled: json['authEnabled'] as bool? ?? false,
      ecommerceProvider: json['ecommerceProvider'] as String? ?? 'mock',
      voiceProvider: json['voiceProvider'] as String? ?? 'mock',
      timestamp: json['timestamp'] as String? ?? '',
    );
  }

  static const HealthStatus unknown = HealthStatus(
    status: 'unknown',
    app: 'unknown',
    stage: 'unknown',
    aiProvider: 'unknown',
    chatHistoryStore: 'unknown',
    authEnabled: false,
    ecommerceProvider: 'unknown',
    voiceProvider: 'unknown',
    timestamp: '',
  );
}

class HealthApi {
  final String baseUrl;

  const HealthApi({required this.baseUrl});

  Future<HealthStatus> fetch() async {
    final uri = Uri.parse('$baseUrl/api/health');
    final response = await http.get(uri);
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    return HealthStatus.fromJson(body);
  }
}
