import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../network/dio_client.dart';

class BattleService {
  BattleService(this._dio);

  final Dio _dio;

  // ─────────────────────────────────────────────
  // QuestCategory（与后端 enum 一致）
  // ─────────────────────────────────────────────
  /// MAIN = 0
  static const int questCategoryMain = 1;
  /// PRACTICE = 11
  static const int questCategoryPractice = 12;

  // ─────────────────────────────────────────────
  // startBattle
  // ─────────────────────────────────────────────
  /// 返回扣除后的剩余体力
  Future<int> startBattle({
    required int questId,
    required int category,
    required int partyId,
    bool useBoostPoint = false,
    bool useBossBoostPoint = false,
    bool isAutoStartMode = false,
    String playId = '',
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/v2/game/battle/start',
        data: {
          'quest_id': questId,
          'category': category,
          'party_id': partyId,
          'use_boost_point': useBoostPoint,
          'use_boss_boost_point': useBossBoostPoint,
          'is_auto_start_mode': isAutoStartMode,
          'play_id': playId,
        },
      );
      final data = response.data ?? const <String, dynamic>{};
      if (data['ok'] != true) {
        final error = data['error']?.toString() ?? '战斗开始失败';
        throw BattleException(error);
      }
      final stamina = (data['stamina'] as num?)?.toInt() ?? 0;
      return stamina;
    } on DioException catch (e) {
      final error = e.response?.data?['error']?.toString() ?? e.message ?? '网络错误';
      throw BattleException(error);
    }
  }

  // ─────────────────────────────────────────────
  // finishBattle
  // ─────────────────────────────────────────────
  /// 返回结算数据
  Future<BattleFinishData> finishBattle({
    required int questId,
    required int category,
    required bool isAccomplished,
    required int score,
    required int elapsedTimeMs,
    int addMana = 0,
    int continueCount = 0,
    required List<int> partyCharacterIds,
    int maxCombo = 0,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/v2/game/battle/finish',
        data: {
          'quest_id': questId,
          'category': category,
          'is_accomplished': isAccomplished,
          'score': score,
          'elapsed_time_ms': elapsedTimeMs,
          'add_mana': addMana,
          'continue_count': continueCount,
          'statistics': {
            'party': {
              'characters': [
                for (final id in partyCharacterIds) {'id': id},
              ],
              'unison_characters': [],
            },
            'max_combo_count': maxCombo,
          },
        },
      );
      final data = response.data ?? const <String, dynamic>{};
      if (data['ok'] != true) {
        final error = data['error']?.toString() ?? '战斗结束失败';
        throw BattleException(error);
      }
      return BattleFinishData.fromJson(data);
    } on DioException catch (e) {
      final error = e.response?.data?['error']?.toString() ?? e.message ?? '网络错误';
      throw BattleException(error);
    }
  }

  // ─────────────────────────────────────────────
  // abortBattle
  // ─────────────────────────────────────────────
  Future<void> abortBattle({
    required int questId,
    required int category,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/v2/game/battle/abort',
        data: {
          'quest_id': questId,
          'category': category,
        },
      );
      final data = response.data ?? const <String, dynamic>{};
      if (data['ok'] != true) {
        final error = data['error']?.toString() ?? '战斗中止失败';
        throw BattleException(error);
      }
    } on DioException catch (e) {
      final error = e.response?.data?['error']?.toString() ?? e.message ?? '网络错误';
      throw BattleException(error);
    }
  }

  // ─────────────────────────────────────────────
  // continueBattle
  // ─────────────────────────────────────────────
  Future<int> continueBattle({
    required int questId,
    required int category,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/v2/game/battle/play_continue',
        data: {
          'quest_id': questId,
          'category': category,
        },
      );
      final data = response.data ?? const <String, dynamic>{};
      if (data['ok'] != true) {
        final error = data['error']?.toString() ?? '继续战斗失败';
        throw BattleException(error);
      }
      return (data['continue_count'] as num?)?.toInt() ?? 0;
    } on DioException catch (e) {
      final error = e.response?.data?['error']?.toString() ?? e.message ?? '网络错误';
      throw BattleException(error);
    }
  }
}

/// 战斗结算数据
class BattleFinishData {
  BattleFinishData({
    required this.clearRank,
    required this.newRankPoint,
    required this.newFreeVmoney,
    required this.newFreeMana,
    required this.newExpPool,
    required this.newStamina,
    required this.items,
    required this.characters,
  });

  final int clearRank;
  final int newRankPoint;
  final int newFreeVmoney;
  final int newFreeMana;
  final int newExpPool;
  final int newStamina;
  final Map<String, int> items;
  final List<Map<String, dynamic>> characters;

  factory BattleFinishData.fromJson(Map<String, dynamic> json) {
    return BattleFinishData(
      clearRank: (json['clear_rank'] as num?)?.toInt() ?? 5,
      newRankPoint: (json['new_rank_point'] as num?)?.toInt() ?? 0,
      newFreeVmoney: (json['new_free_vmoney'] as num?)?.toInt() ?? 0,
      newFreeMana: (json['new_free_mana'] as num?)?.toInt() ?? 0,
      newExpPool: (json['new_exp_pool'] as num?)?.toInt() ?? 0,
      newStamina: (json['new_stamina'] as num?)?.toInt() ?? 0,
      items: Map<String, int>.from(
        (json['items'] as Map<String, dynamic>?) ?? {},
      ),
      characters:
          (json['characters'] as List<dynamic>?)
                  ?.map((e) => e as Map<String, dynamic>)
                  .toList() ??
              [],
    );
  }
}

class BattleException implements Exception {
  BattleException(this.message);
  final String message;

  @override
  String toString() => message;
}
