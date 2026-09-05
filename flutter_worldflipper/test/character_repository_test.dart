import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_worldflipper/main.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('loads the exported character table', () async {
    final repository = await CharacterRepository.load();
    final character = repository.characters.firstWhere((item) => item.id == '1');

    expect(repository.characters, hasLength(513));
    expect(character.displayName, isNotEmpty);
    expect(character.displayName, isNot(equals(character.codeName)));
    expect(character.iconPath, 'assets/game/character_icons/alk.webp');
    expect(character.fullShotPath, 'assets/game/character_shots/alk.webp');
    expect(character.englishName, 'AERKE');
    expect(character.voiceActor, '逢坂良太');
    expect(character.title, '觅星少年');
    expect(character.description, contains('星见镇'));
    expect(character.fields, contains('element'));
    expect(character.abilityIds, hasLength(6));
    expect(repository.abilities, contains('11'));
    expect(repository.abilities['11']!.stringId, 'alk_1');
    expect(repository.abilities['11']!.rarity, 'attack_common');
    expect(repository.abilities['11']!.chineseDescription, contains('攻击力'));
  });
}
