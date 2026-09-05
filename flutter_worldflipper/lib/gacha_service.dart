import 'dart:math';

import 'gacha_repository.dart';

class GachaDrawResult {
  const GachaDrawResult(this.character);

  final GachaCharacter character;
}

class GachaService {
  GachaService(this.repository, {Random? random}) : _random = random ?? Random();

  final GachaRepository repository;
  final Random _random;

  // Reserved for the future backend implementation.
  Future<List<GachaDrawResult>> drawGacha(
    String gachaId, {
    int count = 1,
  }) async {
    final draws = <GachaDrawResult>[];
    for (var index = 0; index < count; index++) {
      draws.add(GachaDrawResult(_drawCharacter()));
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
