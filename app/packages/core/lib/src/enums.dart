// Shared enumerations matching the backend API contract.
// These map to the OpenAPI schema enums in docs/openapi.yaml.

enum SourceType {
  mock,
  officialApi,
  sampleDataset;

  String get apiValue {
    switch (this) {
      case SourceType.mock:
        return 'mock';
      case SourceType.officialApi:
        return 'official_api';
      case SourceType.sampleDataset:
        return 'sample_dataset';
    }
  }

  static SourceType fromApi(String value) {
    switch (value) {
      case 'mock':
        return SourceType.mock;
      case 'official_api':
        return SourceType.officialApi;
      case 'sample_dataset':
        return SourceType.sampleDataset;
      default:
        return SourceType.mock;
    }
  }
}

enum Platform {
  jd,
  taobao,
  pdd,
  tmall,
  other;

  String get apiValue => name;

  static Platform fromApi(String value) {
    return Platform.values.firstWhere(
      (p) => p.apiValue == value,
      orElse: () => Platform.other,
    );
  }
}

enum SortMode {
  comprehensive,
  priceAsc,
  salesDesc,
  ratingDesc;

  String get apiValue {
    switch (this) {
      case SortMode.comprehensive:
        return 'comprehensive';
      case SortMode.priceAsc:
        return 'price_asc';
      case SortMode.salesDesc:
        return 'sales_desc';
      case SortMode.ratingDesc:
        return 'rating_desc';
    }
  }

  String get displayName {
    switch (this) {
      case SortMode.comprehensive:
        return '综合';
      case SortMode.priceAsc:
        return '低价';
      case SortMode.salesDesc:
        return '销量';
      case SortMode.ratingDesc:
        return '好评';
    }
  }

  static SortMode fromApi(String value) {
    switch (value) {
      case 'comprehensive':
        return SortMode.comprehensive;
      case 'price_asc':
        return SortMode.priceAsc;
      case 'sales_desc':
        return SortMode.salesDesc;
      case 'rating_desc':
        return SortMode.ratingDesc;
      default:
        return SortMode.comprehensive;
    }
  }
}

enum PriceTrend {
  low,
  normal,
  high,
  unknown;

  static PriceTrend fromApi(String value) {
    return PriceTrend.values.firstWhere(
      (t) => t.name == value,
      orElse: () => PriceTrend.unknown,
    );
  }
}

enum SuggestionAction {
  buy,
  wait,
  avoid,
  compare;

  static SuggestionAction fromApi(String value) {
    return SuggestionAction.values.firstWhere(
      (a) => a.name == value,
      orElse: () => SuggestionAction.compare,
    );
  }
}
