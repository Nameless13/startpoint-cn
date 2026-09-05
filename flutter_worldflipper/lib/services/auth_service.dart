import 'dart:convert';
import 'dart:developer' as developer;
import 'package:dio/dio.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/player.dart';
import '../network/dio_client.dart';

/// 玩家拥有的角色数据
class OwnedCharacter {
  const OwnedCharacter({
    required this.id,
    required this.entryCount,
    required this.evolutionLevel,
    required this.overLimitStep,
    required this.joinTime,
  });

  final int id;
  final int entryCount; // 同调次数（重复抽到会累加）
  final int evolutionLevel; // 进化等级
  final int overLimitStep; // 超限步数
  final DateTime joinTime; // 获得时间

  factory OwnedCharacter.fromJson(Map<String, dynamic> json) {
    return OwnedCharacter(
      id: json['id'] as int,
      entryCount: json['entryCount'] as int? ?? 1,
      evolutionLevel: json['evolutionLevel'] as int? ?? 0,
      overLimitStep: json['overLimitStep'] as int? ?? 0,
      joinTime: DateTime.tryParse(json['joinTime'] as String? ?? '') ?? DateTime.now(),
    );
  }
}

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
    }
    return player;
  }

  Future<bool> isLoggedIn() async {
    String? token = DioClient.sessionToken;
    try {
      final preferences = await SharedPreferences.getInstance();
      token = preferences.getString(tokenKey) ?? token;
    } on MissingPluginException {
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

  Future<List<OwnedCharacter>> getOwnedCharacters() async {
    developer.log('调用 getOwnedCharacters API...');
    final sessionResponse = await _client.get<Map<String, dynamic>>('/api/v2/game/session');
    final sessionData = sessionResponse.data ?? const <String, dynamic>{};
    final playerId = sessionData['playerId'] as int?;
    
    if (playerId == null) {
      developer.log('未获取到 playerId');
      return [];
    }
    
    developer.log('使用 playerId=$playerId 获取角色详情');
    
    final response = await _client.get<Map<String, dynamic>>(
      '/api/v2/game/player/$playerId/detail',
    );
    developer.log('响应状态码: ${response.statusCode}');
    
    final data = response.data ?? const <String, dynamic>{};
    
    List<dynamic> raw;
    if (data['characters'] is List) {
      raw = data['characters'] as List<dynamic>;
      developer.log('从 characters 字段提取，共 ${raw.length} 个角色');
    } else {
      developer.log('未找到 characters 字段，可用字段: ${data.keys}');
      raw = [];
    }
    
    return raw.map((e) {
      if (e is Map<String, dynamic>) {
        final code = e['code'] ?? e['id'];
        final intId = code is int ? code : int.tryParse(code.toString());
        if (intId == null) {
          developer.log('  无效的角色ID: $code');
          return null;
        }
        developer.log('  角色: code=$code, entryCount=${e['entryCount']}');
        return OwnedCharacter(
          id: intId,
          entryCount: e['entryCount'] as int? ?? 1,
          evolutionLevel: e['evolutionLevel'] as int? ?? 0,
          overLimitStep: e['overLimitStep'] as int? ?? 0,
          joinTime: DateTime.tryParse(e['joinTime'] as String? ?? '') ?? DateTime.now(),
        );
      } else {
        developer.log('  意外的角色数据类型: ${e.runtimeType}');
        return null;
      }
    }).whereType<OwnedCharacter>().toList();
  }

  Future<void> logout() async {
    DioClient.sessionToken = null;
    try {
      final preferences = await SharedPreferences.getInstance();
      await preferences.remove(tokenKey);
      await preferences.remove(playerKey);
    } on MissingPluginException {
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
