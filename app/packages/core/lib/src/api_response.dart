import 'dart:convert';

/// Generic wrapper for the backend's unified response format:
/// ```json
/// { "code": 0, "message": "success", "data": {...} }
/// ```
///
/// [data] is absent or null when the response carries no payload.
class ApiResponse<T> {
  final int code;
  final String message;
  final T? data;

  const ApiResponse({required this.code, required this.message, this.data});

  bool get isSuccess => code == 0;

  /// Parse from a raw JSON map. [dataParser] is a closure that extracts `T`
  /// from the decoded `data` node (which may be `Map<String, dynamic>`, `List`,
  /// or a primitive).
  factory ApiResponse.fromJson(
    Map<String, dynamic> json, {
    required T? Function(dynamic dataNode) dataParser,
  }) {
    final code = json['code'] as int? ?? -1;
    final message = json['message'] as String? ?? 'unknown';
    final dataNode = json['data'];
    final data = dataNode != null ? dataParser(dataNode) : null;
    return ApiResponse(code: code, message: message, data: data);
  }

  /// Convenience helper that treats `data` as a raw JSON value (no transform).
  static ApiResponse<dynamic> fromRawJson(Map<String, dynamic> json) {
    return ApiResponse<dynamic>.fromJson(json, dataParser: (node) => node);
  }

  Map<String, dynamic> toJson() {
    return {
      'code': code,
      'message': message,
      'data': data,
    };
  }

  @override
  String toString() => 'ApiResponse(code: $code, message: $message, data: $data)';
}

/// Parse a JSON string (e.g. from a Dio response body) into [ApiResponse].
ApiResponse<T> parseApiResponse<T>(
  String rawJson, {
  required T? Function(dynamic dataNode) dataParser,
}) {
  final map = jsonDecode(rawJson) as Map<String, dynamic>;
  return ApiResponse.fromJson(map, dataParser: dataParser);
}
