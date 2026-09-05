import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/player.dart';
import '../network/dio_client.dart';

class AuthService {
  AuthService({Dio? client}) : _client = client ?? DioClient.instance;

  static const tokenKey = 'auth_token';
  static const playerKey = 'auth_player';
  final Dio _client;

  Future<Player> login(String username, String password) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/api/v2/game/login',
      data: {'username': username, 'password': password},
    );
    final data = response.data ?? const <String, dynamic>{};
    if (data['ok'] != true || data['token'] == null) {
      throw AuthException(data['error']?.toString() ?? '登录失败');
    }
    final player = Player.fromJson(Map<String, dynamic>.from(data['player'] as Map? ?? {}));
    DioClient.sessionToken = data['token'].toString();
    try {
      final preferences = await SharedPreferences.getInstance();
      await preferences.setString(tokenKey, DioClient.sessionToken!);
      await _savePlayer(preferences, player);
    } on MissingPluginException {
      // The in-memory token keeps this session usable until a full restart.
    }
    return player;
  }

  Future<bool> isLoggedIn() async {
    String? token = DioClient.sessionToken;
    try {
      final preferences = await SharedPreferences.getInstance();
      token = preferences.getString(tokenKey) ?? token;
    } on MissingPluginException {
      // The plugin becomes available after a full application restart.
    }
    if (token == null || token.isEmpty) return false;
    try {
      final response = await _client.get<Map<String, dynamic>>('/api/v2/game/session');
      return response.data?['authenticated'] == true;
    } on DioException {
      return false;
    }
  }

  Future<Player?> getPlayerInfo() async {
    SharedPreferences? preferences;
    try {
      preferences = await SharedPreferences.getInstance();
    } on MissingPluginException {
      // Fetching from the server still works without local cache support.
    }
    final cached = preferences?.getString(playerKey);
    Player? player = cached == null ? null : Player.fromJson(jsonDecode(cached));
    try {
      final response = await _client.get<Map<String, dynamic>>('/api/v2/game/player');
      final data = response.data?['player'] ?? response.data;
      if (data is Map) {
        player = Player.fromJson(Map<String, dynamic>.from(data));
        if (preferences != null) await _savePlayer(preferences, player);
      }
    } on DioException catch (error) {
      if (error.response?.statusCode != 404 && error.response?.statusCode != 405 && player == null) {
        rethrow;
      }
    }
    return player;
  }

  Future<void> logout() async {
    DioClient.sessionToken = null;
    try {
      final preferences = await SharedPreferences.getInstance();
      await preferences.remove(tokenKey);
      await preferences.remove(playerKey);
    } on MissingPluginException {
      // Nothing else is required for an in-memory session.
    }
  }

  Future<void> _savePlayer(SharedPreferences preferences, Player player) async {
    await preferences.setString(playerKey, jsonEncode(player.toJson()));
  }
}

class AuthException implements Exception {
  const AuthException(this.code);

  final String code;

  @override
  String toString() => code;
}