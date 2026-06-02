/// Immutable value object for monetary amounts.
/// Mirrors the backend's `Money` schema: `{ "amount": "199.00", "currency": "CNY" }`.
class Money {
  final String amount;
  final String currency;

  const Money({this.amount = '0.00', this.currency = 'CNY'});

  factory Money.fromJson(Map<String, dynamic> json) {
    final rawAmount = json['amount'];
    return Money(
      amount: rawAmount is num
          ? rawAmount.toStringAsFixed(2)
          : rawAmount?.toString() ?? '0.00',
      currency: json['currency']?.toString() ?? 'CNY',
    );
  }

  Map<String, dynamic> toJson() => {'amount': amount, 'currency': currency};

  double get amountAsDouble => double.tryParse(amount) ?? 0.0;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Money && amount == other.amount && currency == other.currency;

  @override
  int get hashCode => Object.hash(amount, currency);

  @override
  String toString() => '$amount $currency';
}
