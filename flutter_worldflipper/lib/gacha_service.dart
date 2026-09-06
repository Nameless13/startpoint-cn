import 'dart:math';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import 'gacha_repository.dart';
import 'network/dio_client.dart';

/// 扭蛋抽卡结果，包含角色信息和稀有度。
class GachaDrawResult {
  const GachaDrawResult({
    required this.character,
    required this.rankUp,
  });

  /// 抽到的角色
  final GachaCharacter character;

  /// 是否为升星（游戏内特殊标记）
  final bool rankUp;
}

/// 扭蛋服务，支持模拟和真实网络请求两种模式。
class GachaService {
  GachaService(this.repository, {Random? random}) : _random = random ?? Random();

  final GachaRepository repository;
  final Random _random;

  // --------------------------------------------------------------------------
  // 公共入口
  // --------------------------------------------------------------------------

  /// 抽卡入口，默认使用 [realDraw] 对接真实后端。
  ///
  /// 如果需要回退到模拟模式，可以调用 [drawGacha]。
  Future<List<GachaDrawResult>> draw(
    String gachaId, {
    int count = 1,
  }) =>
      realDraw(gachaId, count: count);

  // --------------------------------------------------------------------------
  // 真实网络请求（对接 POST /api/v2/gacha/draw）
  // --------------------------------------------------------------------------

  /// 对接后端接口 POST /api/v2/gacha/draw。
  ///
  /// 请求体：
  /// ```json
  /// { "gachaId": "...", "times": 1 }
  /// ```
  ///
  /// 响应体（后端实际返回）：
  /// ```json
  /// {
  ///   "ok": true,
  ///   "characters": [361005, 200001, ...],
  ///   "items": {},
  ///   "draw": [{ "character_id": 361005, "movie_id": ..., "seed": ..., "entry_count": ... }]
  /// }
  /// ```
  Future<List<GachaDrawResult>> realDraw(
    String gachaId, {
    int count = 1,
  }) async {
    try {
      final response = await DioClient.instance.post<Map<String, dynamic>>(
        '/api/v2/game/gacha/draw',
        data: {'gachaId': gachaId, 'times': count},
      );

      final data = response.data ?? const <String, dynamic>{};
      if (data['ok'] != true) {
        final error = data['error']?.toString() ?? '抽卡失败';
        throw GachaException(error);
      }

      // 后端返回 character_id 数字 ID 列表
      final characterIds = data['characters'] as List<dynamic>? ?? [];
      final results = <GachaDrawResult>[];

      for (final id in characterIds) {
        final idStr = id.toString();
        final character = repository.characters.firstWhere(
          (c) => c.id == idStr,
          orElse: () => GachaCharacter(id: idStr, name: idStr, rarity: 0),
        );
        results.add(GachaDrawResult(character: character, rankUp: false));
      }

      return results;
    } on DioException catch (e) {
      // 后端接口未实现或网络错误时，fallback 到模拟模式
      if (e.type == DioExceptionType.connectionError ||
          e.response?.statusCode == 404 ||
          e.response?.statusCode == 501) {
        debugPrint('扭蛋后端接口尚未实现，回退到模拟模式');
        return drawGacha(gachaId, count: count);
      }
      final error = e.response?.data?['error']?.toString() ?? e.message ?? '网络错误';
      throw GachaException(error);
    } catch (e) {
      rethrow;
    }
  }

  // --------------------------------------------------------------------------
  // 模拟抽卡（备选方案）
  // --------------------------------------------------------------------------

  /// 本地模拟抽卡，不依赖后端。
  Future<List<GachaDrawResult>> drawGacha(
    String gachaId, {
    int count = 1,
  }) async {
    final draws = <GachaDrawResult>[];
    for (var index = 0; index < count; index++) {
      draws.add(GachaDrawResult(character: _drawCharacter(), rankUp: false));
    }
    return draws;
  }

  GachaCharacter _drawCharacter() {
    final rarity = _drawRarity();
    final candidates = repository.characters
        .where((character) => character.rarity == rarity)
        .toList();
    final pool = candidates.isEmpty ? repository.characters : candidates;
    return pool[_random.nextInt(pool.length)];
  }

  int _drawRarity() {
    final roll = _random.nextInt(1000);
    if (roll < 50) return 5;
    if (roll < 300) return 4;
    return 3;
  }
}

/// 扭蛋服务异常。
class GachaException implements Exception {
  const GachaException(this.message);

  final String message;

  @override
  String toString() => message;
}
