import 'dart:math';

import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_worldflipper/gacha_repository.dart';
import 'package:flutter_worldflipper/gacha_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('loads gacha pools and simulates requested draw count', () async {
    final repository = await GachaRepository.load();

    expect(repository.gachas, isNotEmpty);
    expect(repository.characters, isNotEmpty);

    final service = GachaService(repository, random: Random(7));
    final results = await service.drawGacha(repository.gachas.first.id, count: 10);

    expect(results, hasLength(10));
    expect(results.every((result) => result.character.rarity >= 3), isTrue);
  });
}