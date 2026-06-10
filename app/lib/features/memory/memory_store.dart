import 'dart:convert';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Local storage wrapper for user memory.
///
/// Encapsulates shared_preferences so the storage backend can be swapped
/// (e.g. to a backend API) without changing the rest of the memory module.
final memoryStoreProvider = Provider<MemoryStore>((ref) => MemoryStore());

class MemoryStore {
  static const _keyProfile = 'memory_profile';
  static const _keyEvents = 'memory_events';
  static const _keyOnboardingDone = 'memory_onboarding_done';
  static const _keyPersonalizationEnabled = 'memory_personalization_enabled';
  static const _keyPrivacyAccepted = 'memory_privacy_accepted';

  SharedPreferences? _prefs;

  Future<SharedPreferences> get _p => _prefs != null
      ? Future.value(_prefs!)
      : SharedPreferences.getInstance().then((p) => _prefs = p);

  // ── Profile ────────────────────────────────────────────────

  Future<Map<String, dynamic>?> loadProfile() async {
    final raw = (await _p).getString(_keyProfile);
    if (raw == null || raw.isEmpty) return null;
    try {
      return jsonDecode(raw) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  Future<void> saveProfile(Map<String, dynamic> profile) async {
    await (await _p).setString(_keyProfile, jsonEncode(profile));
  }

  Future<void> clearProfile() async {
    await (await _p).remove(_keyProfile);
  }

  // ── Events ─────────────────────────────────────────────────

  Future<List<Map<String, dynamic>>> loadEvents() async {
    final raw = (await _p).getString(_keyEvents);
    if (raw == null || raw.isEmpty) return [];
    try {
      final list = jsonDecode(raw) as List<dynamic>;
      return list.cast<Map<String, dynamic>>();
    } catch (_) {
      return [];
    }
  }

  Future<void> saveEvents(List<Map<String, dynamic>> events) async {
    // Keep at most 500 events to bound storage
    final trimmed = events.length > 500 ? events.sublist(events.length - 500) : events;
    await (await _p).setString(_keyEvents, jsonEncode(trimmed));
  }

  Future<void> clearEvents() async {
    await (await _p).remove(_keyEvents);
  }

  // ── Flags ──────────────────────────────────────────────────

  Future<bool> isOnboardingDone() async =>
      (await _p).getBool(_keyOnboardingDone) ?? false;

  Future<void> setOnboardingDone() async =>
      await (await _p).setBool(_keyOnboardingDone, true);

  Future<bool> isPersonalizationEnabled() async =>
      (await _p).getBool(_keyPersonalizationEnabled) ?? true;

  Future<void> setPersonalizationEnabled(bool v) async =>
      await (await _p).setBool(_keyPersonalizationEnabled, v);

  Future<bool> isPrivacyAccepted() async =>
      (await _p).getBool(_keyPrivacyAccepted) ?? false;

  Future<void> setPrivacyAccepted() async =>
      await (await _p).setBool(_keyPrivacyAccepted, true);

  // ── Reset ──────────────────────────────────────────────────

  Future<void> clearAll() async {
    final p = await _p;
    await p.remove(_keyProfile);
    await p.remove(_keyEvents);
    await p.remove(_keyOnboardingDone);
    await p.remove(_keyPersonalizationEnabled);
    await p.remove(_keyPrivacyAccepted);
  }
}
