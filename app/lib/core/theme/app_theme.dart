import 'package:flutter/material.dart';

/// Shared product theme for the Flutter app.

const _accent = Color(0xFF4F46E5);
const _accentStrong = Color(0xFF3730A3);
const _signal = Color(0xFF2453A6);
const _inkMain = Color(0xFF111827);
const _inkSoft = Color(0xFF667085);
const _line = Color(0xFFE5E7EB);
const _panel = Color(0xFFFFFFFF);
const _panelSoft = Color(0xFFF9FAFB);
const _background = Color(0xFFF7F8FA);
const _warn = Color(0xFFA16207);
const _good = Color(0xFF047857);
const _priceRed = Color(0xFFB42318);

ThemeData buildAppTheme() {
  const colorScheme = ColorScheme.light(
    primary: _accent,
    onPrimary: Colors.white,
    secondary: _accentStrong,
    surface: _panel,
    surfaceContainerHighest: _panelSoft,
    error: _priceRed,
    onSurface: _inkMain,
    outline: _line,
  );

  return ThemeData(
    useMaterial3: true,
    fontFamily: 'Microsoft YaHei',
    fontFamilyFallback: const ['Bahnschrift', 'Segoe UI', 'Arial'],
    colorScheme: colorScheme,
    scaffoldBackgroundColor: _background,
    appBarTheme: const AppBarTheme(
      backgroundColor: _panel,
      foregroundColor: _inkMain,
      elevation: 0,
      scrolledUnderElevation: 1,
      centerTitle: false,
      titleTextStyle: TextStyle(
        fontSize: 18,
        fontWeight: FontWeight.w700,
        color: _inkMain,
      ),
    ),
    cardTheme: CardThemeData(
      color: _panel,
      elevation: 1,
      margin: EdgeInsets.zero,
      shadowColor: Colors.black.withAlpha(10),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: const BorderSide(color: _line),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: _panel,
      contentPadding:
          const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: const BorderSide(color: _line),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: const BorderSide(color: _line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: const BorderSide(color: _accent, width: 2),
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: _accent,
        foregroundColor: Colors.white,
        minimumSize: const Size.fromHeight(38),
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
      ),
    ),
    bottomNavigationBarTheme: const BottomNavigationBarThemeData(
      backgroundColor: _panel,
      selectedItemColor: _accent,
      unselectedItemColor: _inkSoft,
      type: BottomNavigationBarType.fixed,
      selectedLabelStyle:
          TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
      unselectedLabelStyle: TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.w400,
      ),
    ),
    dividerTheme: const DividerThemeData(color: _line, thickness: 1),
    textTheme: const TextTheme(
      headlineLarge: TextStyle(
        fontSize: 28,
        fontWeight: FontWeight.w700,
        color: _inkMain,
      ),
      headlineSmall: TextStyle(
        fontSize: 21,
        fontWeight: FontWeight.w700,
        color: _inkMain,
      ),
      titleMedium: TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.w700,
        color: _inkMain,
      ),
      titleSmall: TextStyle(
        fontSize: 14,
        fontWeight: FontWeight.w600,
        color: _inkMain,
      ),
      bodyLarge: TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.w400,
        color: _inkMain,
      ),
      bodyMedium: TextStyle(
        fontSize: 15,
        fontWeight: FontWeight.w400,
        color: _inkMain,
      ),
      bodySmall: TextStyle(
        fontSize: 14,
        fontWeight: FontWeight.w400,
        color: _inkSoft,
      ),
      labelMedium: TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.w600,
        color: _inkSoft,
      ),
    ),
  );
}

/// Convenience accessors for common colors.
class AppColors {
  static const accent = _accent;
  static const accentStrong = _accentStrong;
  static const signal = _signal;
  static const inkMain = _inkMain;
  static const inkSoft = _inkSoft;
  static const line = _line;
  static const panel = _panel;
  static const panelSoft = _panelSoft;
  static const background = _background;
  static const warn = _warn;
  static const good = _good;
  static const priceRed = _priceRed;
}
