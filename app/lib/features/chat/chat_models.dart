class ImageUploadResult {
  final String imageId;
  final String fileName;
  final String contentType;
  final int size;

  const ImageUploadResult({
    required this.imageId,
    required this.fileName,
    required this.contentType,
    required this.size,
  });

  factory ImageUploadResult.fromJson(Map<String, dynamic> json) {
    return ImageUploadResult(
      imageId: json['imageId'] as String,
      fileName: json['fileName'] as String,
      contentType: json['contentType'] as String,
      size: json['size'] as int,
    );
  }
}

class SessionResult {
  final String sessionId;
  final String createdAt;

  const SessionResult({required this.sessionId, required this.createdAt});

  factory SessionResult.fromJson(Map<String, dynamic> json) {
    return SessionResult(
      sessionId: json['sessionId'] as String,
      createdAt: json['createdAt'] as String,
    );
  }
}

class AgentReply {
  final String replyId;
  final String replyType; // "clarification" or "recommendation"
  final String text;
  final List<ReplyCard> cards;

  const AgentReply({
    required this.replyId,
    required this.replyType,
    required this.text,
    required this.cards,
  });

  factory AgentReply.fromJson(Map<String, dynamic> json) {
    return AgentReply(
      replyId: json['replyId'] as String,
      replyType: json['replyType'] as String,
      text: json['text'] as String,
      cards: (json['cards'] as List)
          .map((c) => ReplyCard.fromJson(c as Map<String, dynamic>))
          .toList(),
    );
  }
}

class ReplyCard {
  final String cardType;
  final String title;
  final String? productName;
  final String? platform;
  final double? price;
  final String? reason;
  final List<ClarificationOption>? options;

  const ReplyCard({
    required this.cardType,
    required this.title,
    this.productName,
    this.platform,
    this.price,
    this.reason,
    this.options,
  });

  factory ReplyCard.fromJson(Map<String, dynamic> json) {
    return ReplyCard(
      cardType: json['cardType'] as String,
      title: json['title'] as String,
      productName: json['productName'] as String?,
      platform: json['platform'] as String?,
      price: (json['price'] as num?)?.toDouble(),
      reason: json['reason'] as String?,
      options: (json['options'] as List?)
          ?.map((o) => ClarificationOption.fromJson(o as Map<String, dynamic>))
          .toList(),
    );
  }
}

class ClarificationOption {
  final String optionId;
  final String label;

  const ClarificationOption({required this.optionId, required this.label});

  factory ClarificationOption.fromJson(Map<String, dynamic> json) {
    return ClarificationOption(
      optionId: json['optionId'] as String,
      label: json['label'] as String,
    );
  }
}

/// A chat message displayed in the UI.
class ChatMessage {
  final String id;
  final ChatRole role;
  final String? text;
  final List<String> imagePaths; // local preview paths
  final List<String> imageIds; // uploaded image IDs
  final AgentReply? agentReply;
  final bool isLoading;

  const ChatMessage({
    required this.id,
    required this.role,
    this.text,
    this.imagePaths = const [],
    this.imageIds = const [],
    this.agentReply,
    this.isLoading = false,
  });

  ChatMessage copyWith({
    String? id,
    ChatRole? role,
    String? text,
    List<String>? imagePaths,
    List<String>? imageIds,
    AgentReply? agentReply,
    bool? isLoading,
  }) {
    return ChatMessage(
      id: id ?? this.id,
      role: role ?? this.role,
      text: text ?? this.text,
      imagePaths: imagePaths ?? this.imagePaths,
      imageIds: imageIds ?? this.imageIds,
      agentReply: agentReply ?? this.agentReply,
      isLoading: isLoading ?? this.isLoading,
    );
  }
}

enum ChatRole { user, assistant }
