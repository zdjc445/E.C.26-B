import 'package:app_core/app_core.dart';

/// A single suggestion card returned by the recognition backend.
class SuggestionCard {
  final String title;
  final String description;
  final SuggestionAction action;
  final String? actionLabel;
  final String? iconUrl;
  final Map<String, dynamic>? payload;

  const SuggestionCard({
    required this.title,
    required this.description,
    required this.action,
    this.actionLabel,
    this.iconUrl,
    this.payload,
  });

  factory SuggestionCard.fromJson(Map<String, dynamic> json) {
    return SuggestionCard(
      title: json['title'] as String,
      description: json['description'] as String? ?? '',
      action: SuggestionAction.fromApi(json['action'] as String? ?? 'compare'),
      actionLabel: json['actionLabel'] as String?,
      iconUrl: json['iconUrl'] as String?,
      payload: json['payload'] as Map<String, dynamic>?,
    );
  }

  Map<String, dynamic> toJson() => {
    'title': title,
    'description': description,
    'action': action.name,
    if (actionLabel != null) 'actionLabel': actionLabel,
    if (iconUrl != null) 'iconUrl': iconUrl,
    if (payload != null) 'payload': payload,
  };

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is SuggestionCard && title == other.title && action == other.action;

  @override
  int get hashCode => Object.hash(title, action);
}
