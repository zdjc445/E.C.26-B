import 'package:flutter/material.dart';
import '../../domain/entities/product_entity.dart';
import 'product_card.dart';

/// A grid of product cards. Shows empty state when no results.
class ProductGrid extends StatelessWidget {
  final List<ProductEntity> products;
  final bool isLoading;
  final String? emptyMessage;
  final void Function(ProductEntity product)? onProductTap;

  const ProductGrid({
    super.key,
    required this.products,
    this.isLoading = false,
    this.emptyMessage,
    this.onProductTap,
  });

  @override
  Widget build(BuildContext context) {
    if (isLoading) {
      return const SliverFillRemaining(
        child: Center(child: CircularProgressIndicator()),
      );
    }

    if (products.isEmpty) {
      return SliverFillRemaining(
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.search_off, size: 64, color: Colors.grey.shade400),
              const SizedBox(height: 12),
              Text(
                emptyMessage ?? '暂无搜索结果',
                style: TextStyle(fontSize: 15, color: Colors.grey.shade600),
              ),
            ],
          ),
        ),
      );
    }

    return SliverPadding(
      padding: const EdgeInsets.all(8),
      sliver: SliverGrid(
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2,
          mainAxisSpacing: 8,
          crossAxisSpacing: 8,
          childAspectRatio: 0.62,
        ),
        delegate: SliverChildBuilderDelegate(
          (context, index) {
            final product = products[index];
            return ProductCard(
              product: product,
              onTap: onProductTap != null ? () => onProductTap!(product) : null,
            );
          },
          childCount: products.length,
        ),
      ),
    );
  }
}
