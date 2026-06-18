import 'dart:convert';
import 'package:http/http.dart' as http;

class EcommerceStatus {
  final String activeProvider;
  final bool realProviderEnabled;
  final bool realProviderActive;
  final String? realProviderBaseUrl;
  final List<String> samplePlatforms;
  final List<String> sampleCategories;
  final String? fallbackPolicy;

  const EcommerceStatus({
    required this.activeProvider,
    required this.realProviderEnabled,
    required this.realProviderActive,
    this.realProviderBaseUrl,
    required this.samplePlatforms,
    required this.sampleCategories,
    this.fallbackPolicy,
  });

  factory EcommerceStatus.fromJson(Map<String, dynamic> json) {
    return EcommerceStatus(
      activeProvider: json['activeProvider'] as String? ?? 'unknown',
      realProviderEnabled: json['realProviderEnabled'] as bool? ?? false,
      realProviderActive: json['realProviderActive'] as bool? ?? false,
      realProviderBaseUrl: json['realProviderBaseUrl'] as String?,
      samplePlatforms: (json['samplePlatforms'] as List?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
      sampleCategories: (json['sampleCategories'] as List?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
      fallbackPolicy: json['fallbackPolicy'] as String?,
    );
  }

  static const EcommerceStatus unknown = EcommerceStatus(
    activeProvider: 'unknown',
    realProviderEnabled: false,
    realProviderActive: false,
    samplePlatforms: [],
    sampleCategories: [],
  );
}

class EcommerceApi {
  final String baseUrl;

  const EcommerceApi({required this.baseUrl});

  Future<EcommerceStatus> status() async {
    final uri = Uri.parse('$baseUrl/api/ecommerce/status');
    final response = await http.get(uri);
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode == 200 && body['code'] == 0) {
      return EcommerceStatus.fromJson(body['data'] as Map<String, dynamic>);
    }
    throw Exception(body['message'] as String? ?? '获取电商状态失败');
  }
}
