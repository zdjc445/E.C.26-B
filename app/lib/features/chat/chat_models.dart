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

class ChatSessionSummary {
  final String sessionId;
  final String title;
  final String createdAt;
  final String updatedAt;
  final int messageCount;

  const ChatSessionSummary({
    required this.sessionId,
    required this.title,
    required this.createdAt,
    required this.updatedAt,
    required this.messageCount,
  });

  factory ChatSessionSummary.fromJson(Map<String, dynamic> json) {
    return ChatSessionSummary(
      sessionId: json['sessionId'] as String,
      title: json['title'] as String,
      createdAt: json['createdAt'] as String,
      updatedAt: json['updatedAt'] as String,
      messageCount: json['messageCount'] as int,
    );
  }
}

class AgentReply {
  final String replyId;
  final String replyType;
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
  // recognition fields
  final String? imageId;
  final String? category;
  final String? brand;
  final String? model;
  final List<String>? keywords;
  final Map<String, dynamic>? attributes;
  final double? confidence;
  final String? aiProvider;
  final bool? fallbackUsed;
  final String? explanation;
  final String? recognitionId;

  const ReplyCard({
    required this.cardType,
    required this.title,
    this.productName,
    this.platform,
    this.price,
    this.reason,
    this.options,
    this.imageId,
    this.category,
    this.brand,
    this.model,
    this.keywords,
    this.attributes,
    this.confidence,
    this.aiProvider,
    this.fallbackUsed,
    this.explanation,
    this.recognitionId,
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
          ?.map((o) =>
              ClarificationOption.fromJson(o as Map<String, dynamic>))
          .toList(),
      imageId: json['imageId'] as String?,
      category: json['category'] as String?,
      brand: json['brand'] as String?,
      model: json['model'] as String?,
      keywords: (json['keywords'] as List?)
          ?.map((k) => k.toString())
          .toList(),
      attributes:
          json['attributes'] as Map<String, dynamic>?,
      confidence: (json['confidence'] as num?)?.toDouble(),
      aiProvider: json['aiProvider'] as String?,
      fallbackUsed: json['fallbackUsed'] as bool?,
      explanation: json['explanation'] as String?,
      recognitionId: json['recognitionId'] as String?,
    );
  }
}

class ClarificationOption {
  final String optionId;
  final String label;

  const ClarificationOption(
      {required this.optionId, required this.label});

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
  final List<String> imagePaths;
  final List<String> imageIds;
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
