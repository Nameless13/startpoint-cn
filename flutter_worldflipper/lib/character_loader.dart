import 'dart:convert';

import 'package:flutter/services.dart';

/// 加载角色 ID 列表（用于战斗页等场景）
Future<List<String>> loadCharacterIds() async {
  final content = await rootBundle.loadString(
    'assets/exported/master_character_character.json',
  );
  final map = jsonDecode(content) as Map<String, dynamic>;
  return map.keys.toList();
}
