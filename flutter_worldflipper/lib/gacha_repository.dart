import 'dart:convert';

import 'package:flutter/services.dart';

class GachaCharacter {
  const GachaCharacter({
    required this.id,
    required this.name,
    required this.rarity,
  });

  final String id;
  final String name;
  final int rarity;
}

class GachaRecord {
  const GachaRecord({required this.id, required this.fields});

  final String id;
  final List<dynamic> fields;

  String get name => _string(1, id);
  int get pageKind => _int(4);
  int get singleCost => _int(5);
  int get multiCost => _int(6);
  String get rarityOddsId => _string(11, '未定义');
  int get guaranteeRarity => _int(10);
  bool get isCharacterGacha => _string(13, '') == '0';

  String get currencyLabel {
    if (pageKind == 3 || pageKind == 4 || pageKind == 5) return '抽卡券';
    return '免费水晶 / 付费水晶';
  }

  String _string(int index, String fallback) {
    if (index >= fields.length) return fallback;
    final value = fields[index]?.toString().trim() ?? '';
    return value.isEmpty || value == '(None)' ? fallback : value;
  }

  int _int(int index) => int.tryParse(_string(index, '0')) ?? 0;
}

class GachaRepository {
  const GachaRepository({required this.gachas, required this.characters});

  final List<GachaRecord> gachas;
  final List<GachaCharacter> characters;

  static Future<GachaRepository> load() async {
    final gachaContent = await rootBundle.loadString(
      'assets/exported/master_gacha_gacha.json',
    );
    final characterContent = await rootBundle.loadString(
      'assets/exported/master_character_character.json',
    );
    final textContent = await rootBundle.loadString(
      'assets/exported/master_character_character_text.json',
    );
    final gachaDecoded = jsonDecode(gachaContent) as Map<String, dynamic>;
    final characterDecoded = jsonDecode(characterContent) as Map<String, dynamic>;
    final textDecoded = jsonDecode(textContent) as Map<String, dynamic>;

    final gachas = [
      for (final entry in gachaDecoded.entries)
        if (entry.value is List)
          GachaRecord(
            id: entry.key,
            fields: List<dynamic>.from(entry.value as List),
          ),
    ].where((gacha) => gacha.isCharacterGacha).toList();
    gachas.sort((first, second) => first.name.compareTo(second.name));

    final characters = [
      for (final entry in characterDecoded.entries)
        if (entry.value is Map)
          GachaCharacter(
            id: entry.key,
            name: _characterName(entry.key, entry.value, textDecoded),
            rarity: _characterRarity(entry.value),
          ),
    ].where((character) => character.rarity >= 3).toList();

    return GachaRepository(gachas: gachas, characters: characters);
  }

  static String _characterName(
    String id,
    dynamic value,
    Map<String, dynamic> textDecoded,
  ) {
    final text = textDecoded[id];
    if (text is Map && text['name']?.toString().trim().isNotEmpty == true) {
      return text['name'].toString();
    }
    final fields = value as Map;
    return fields['code_name']?.toString() ?? id;
  }

  static int _characterRarity(dynamic value) {
    final fields = value as Map;
    return int.tryParse(fields['rarity']?.toString() ?? '') ?? 0;
  }
}
