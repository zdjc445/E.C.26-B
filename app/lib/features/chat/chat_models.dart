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
  // product fields (legacy)
  final List<ProductItem>? products;
  final Map<String, dynamic>? platformStats;
  // recommendation explanation fields
  final int? decisionScore;
  final List<DecisionSignal>? decisionSignals;
  final List<RecommendationEvidence>? evidence;
  final List<String>? risks;
  final List<ProductAnalysis>? productAnalyses;
  final String? intentProvider;
  final bool? intentFallbackUsed;
  final String? explanationProvider;
  final bool? explanationFallbackUsed;
  final List<String>? notices;
  final List<String> filterSummary;
  // product group fields (new)
  final List<ProductGroup>? groups;
  final String? emptyReason;

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
    this.products,
    this.platformStats,
    this.decisionScore,
    this.decisionSignals,
    this.evidence,
    this.risks,
    this.productAnalyses,
    this.intentProvider,
    this.intentFallbackUsed,
    this.explanationProvider,
    this.explanationFallbackUsed,
    this.notices,
    this.filterSummary = const [],
    this.groups,
    this.emptyReason,
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
      imageId: json['imageId'] as String?,
      category: json['category'] as String?,
      brand: json['brand'] as String?,
      model: json['model'] as String?,
      keywords: (json['keywords'] as List?)?.map((k) => k.toString()).toList(),
      attributes: _stringMap(json['attributes']),
      confidence: (json['confidence'] as num?)?.toDouble(),
      aiProvider: json['aiProvider'] as String?,
      fallbackUsed: json['fallbackUsed'] as bool?,
      explanation: json['explanation'] as String?,
      recognitionId: json['recognitionId'] as String?,
      products: (json['products'] as List?)
          ?.map((p) => ProductItem.fromJson(p as Map<String, dynamic>))
          .toList(),
      platformStats: _stringMap(json['platformStats']),
      decisionScore: (json['decisionScore'] as num?)?.round(),
      decisionSignals: (json['decisionSignals'] as List?)
          ?.map((s) => DecisionSignal.fromJson(s as Map<String, dynamic>))
          .toList(),
      evidence: (json['evidence'] as List?)
          ?.map((e) =>
              RecommendationEvidence.fromJson(e as Map<String, dynamic>))
          .toList(),
      risks: (json['risks'] as List?)?.map((v) => v.toString()).toList(),
      productAnalyses: (json['productAnalyses'] as List?)
          ?.map((a) => ProductAnalysis.fromJson(a as Map<String, dynamic>))
          .toList(),
      intentProvider: json['intentProvider'] as String?,
      intentFallbackUsed: json['intentFallbackUsed'] as bool?,
      explanationProvider: json['explanationProvider'] as String?,
      explanationFallbackUsed: json['explanationFallbackUsed'] as bool?,
      notices: (json['notices'] as List?)?.map((v) => v.toString()).toList(),
      filterSummary:
          (json['filterSummary'] as List?)?.map((v) => v.toString()).toList() ??
              const [],
      groups: (json['groups'] as List?)
          ?.map((g) => ProductGroup.fromJson(g as Map<String, dynamic>))
          .toList(),
      emptyReason: json['emptyReason'] as String?,
    );
  }
}

class DecisionSignal {
  final String key;
  final String label;
  final int score;
  final String explanation;

  const DecisionSignal({
    required this.key,
    required this.label,
    required this.score,
    required this.explanation,
  });

  factory DecisionSignal.fromJson(Map<String, dynamic> json) {
    return DecisionSignal(
      key: json['key'] as String? ?? '',
      label: json['label'] as String? ?? '',
      score: (json['score'] as num?)?.round() ?? 0,
      explanation: json['explanation'] as String? ?? '',
    );
  }
}

class RecommendationEvidence {
  final String type;
  final String content;

  const RecommendationEvidence({required this.type, required this.content});

  factory RecommendationEvidence.fromJson(Map<String, dynamic> json) {
    return RecommendationEvidence(
      type: json['type'] as String? ?? '',
      content: json['content'] as String? ?? '',
    );
  }
}

class ProductAnalysis {
  final String productId;
  final String platform;
  final String title;
  final int rank;
  final int score;
  final List<String> strengths;
  final List<String> weaknesses;

  const ProductAnalysis({
    required this.productId,
    required this.platform,
    required this.title,
    required this.rank,
    required this.score,
    required this.strengths,
    required this.weaknesses,
  });

  factory ProductAnalysis.fromJson(Map<String, dynamic> json) {
    return ProductAnalysis(
      productId: json['productId'] as String? ?? '',
      platform: json['platform'] as String? ?? '',
      title: json['title'] as String? ?? '',
      rank: (json['rank'] as num?)?.round() ?? 0,
      score: (json['score'] as num?)?.round() ?? 0,
      strengths:
          (json['strengths'] as List?)?.map((v) => v.toString()).toList() ??
              const [],
      weaknesses:
          (json['weaknesses'] as List?)?.map((v) => v.toString()).toList() ??
              const [],
    );
  }
}

class ProductGroup {
  final String groupId;
  final String? sameItemKey;
  final String displayTitle;
  final String? category;
  final String? brand;
  final String? thumbnailUrl;
  final double bestPrice;
  final double originalPrice;
  final PriceRange? priceRange;
  final int platformCount;
  final List<PlatformOfferSummary> platforms;
  final List<String> highlights;
  final String? matchLevel;

  const ProductGroup({
    required this.groupId,
    this.sameItemKey,
    required this.displayTitle,
    this.category,
    this.brand,
    this.thumbnailUrl,
    required this.bestPrice,
    required this.originalPrice,
    this.priceRange,
    required this.platformCount,
    required this.platforms,
    required this.highlights,
    this.matchLevel,
  });

  factory ProductGroup.fromJson(Map<String, dynamic> json) {
    return ProductGroup(
      groupId: json['groupId'] as String,
      sameItemKey: json['sameItemKey'] as String?,
      displayTitle: json['displayTitle'] as String,
      category: json['category'] as String?,
      brand: json['brand'] as String?,
      thumbnailUrl: json['thumbnailUrl'] as String?,
      bestPrice: (json['bestPrice'] as num).toDouble(),
      originalPrice: (json['originalPrice'] as num).toDouble(),
      priceRange: json['priceRange'] != null
          ? PriceRange.fromJson(json['priceRange'] as Map<String, dynamic>)
          : null,
      platformCount: json['platformCount'] as int,
      platforms: (json['platforms'] as List)
          .map((p) => PlatformOfferSummary.fromJson(p as Map<String, dynamic>))
          .toList(),
      highlights:
          (json['highlights'] as List).map((h) => h.toString()).toList(),
      matchLevel: json['matchLevel'] as String?,
    );
  }
}

class ProductSpec {
  final String label;
  final String value;

  const ProductSpec({required this.label, required this.value});

  factory ProductSpec.fromJson(Map<String, dynamic> json) {
    return ProductSpec(
      label: json['label'] as String? ?? '',
      value: json['value'] as String? ?? '',
    );
  }
}

class PriceRange {
  final double min;
  final double max;

  const PriceRange({required this.min, required this.max});

  factory PriceRange.fromJson(Map<String, dynamic> json) {
    return PriceRange(
      min: (json['min'] as num).toDouble(),
      max: (json['max'] as num).toDouble(),
    );
  }
}

class PlatformOfferSummary {
  final String productId;
  final String platform;
  final double price;
  final double originalPrice;
  final String shopName;
  final String productUrl;
  final double rating;
  final int sales;
  final List<String> tags;
  final List<String> reasons;
  final double score;
  final String title;
  final String imageUrl;
  final String brand;
  final List<double> priceHistory;
  final List<String> matchedPreferences;
  final List<ProductSpec> specs;

  const PlatformOfferSummary({
    required this.productId,
    required this.platform,
    required this.price,
    required this.originalPrice,
    required this.shopName,
    required this.productUrl,
    required this.rating,
    required this.sales,
    required this.tags,
    required this.reasons,
    this.score = 0,
    this.title = '',
    this.imageUrl = '',
    this.brand = '',
    this.priceHistory = const [],
    this.matchedPreferences = const [],
    this.specs = const [],
  });

  factory PlatformOfferSummary.fromJson(Map<String, dynamic> json) {
    return PlatformOfferSummary(
      productId: json['productId'] as String,
      platform: json['platform'] as String,
      price: (json['price'] as num).toDouble(),
      originalPrice: (json['originalPrice'] as num).toDouble(),
      shopName: json['shopName'] as String,
      productUrl: json['productUrl'] as String? ?? '',
      rating: (json['rating'] as num).toDouble(),
      sales: json['sales'] as int,
      tags: (json['tags'] as List).map((t) => t.toString()).toList(),
      reasons: (json['reasons'] as List).map((r) => r.toString()).toList(),
      score: (json['score'] as num?)?.toDouble() ?? 0,
      title: json['title'] as String? ?? '',
      imageUrl: json['imageUrl'] as String? ?? '',
      brand: json['brand'] as String? ?? '',
      priceHistory: (json['priceHistory'] as List?)
              ?.map((v) => (v as num).toDouble())
              .toList() ??
          const [],
      matchedPreferences: (json['matchedPreferences'] as List?)
              ?.map((v) => v.toString())
              .toList() ??
          const [],
      specs: (json['specs'] as List?)
              ?.map((s) => ProductSpec.fromJson(s as Map<String, dynamic>))
              .toList() ??
          const [],
    );
  }
}

Map<String, dynamic>? _stringMap(Object? value) {
  if (value == null) return null;
  return Map<String, dynamic>.from(value as Map);
}

class ProductItem {
  final String productId;
  final String title;
  final String platform;
  final double price;
  final double originalPrice;
  final String shopName;
  final String imageUrl;
  final String productUrl;
  final double rating;
  final int sales;
  final List<String> tags;
  final List<String> reasons;
  final double score;
  final String? brand;
  final List<double> priceHistory;
  final List<String> matchedPreferences;

  const ProductItem({
    required this.productId,
    required this.title,
    required this.platform,
    required this.price,
    required this.originalPrice,
    required this.shopName,
    required this.imageUrl,
    required this.productUrl,
    required this.rating,
    required this.sales,
    required this.tags,
    required this.reasons,
    required this.score,
    this.brand,
    this.priceHistory = const [],
    this.matchedPreferences = const [],
  });

  factory ProductItem.fromJson(Map<String, dynamic> json) {
    return ProductItem(
      productId: json['productId'] as String,
      title: json['title'] as String,
      platform: json['platform'] as String,
      price: (json['price'] as num).toDouble(),
      originalPrice: (json['originalPrice'] as num).toDouble(),
      shopName: json['shopName'] as String,
      imageUrl: json['imageUrl'] as String? ?? '',
      productUrl: json['productUrl'] as String? ?? '',
      rating: (json['rating'] as num).toDouble(),
      sales: json['sales'] as int,
      tags: (json['tags'] as List).map((t) => t.toString()).toList(),
      reasons: (json['reasons'] as List).map((r) => r.toString()).toList(),
      score: (json['score'] as num).toDouble(),
      brand: json['brand'] as String?,
      priceHistory: (json['priceHistory'] as List?)
              ?.map((v) => (v as num).toDouble())
              .toList() ??
          const [],
      matchedPreferences: (json['matchedPreferences'] as List?)
              ?.map((v) => v.toString())
              .toList() ??
          const [],
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
