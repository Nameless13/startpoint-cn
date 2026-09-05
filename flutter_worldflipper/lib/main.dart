import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'gacha_page.dart';
import 'models/player.dart';
import 'pages/login_page.dart';
import 'services/auth_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const WorldFlipperApp());
}

class CharacterRecord {
  const CharacterRecord({required this.id, required this.fields});

  final String id;
  final Map<String, dynamic> fields;

  String get codeName => _string('code_name', id);
  String get iconPath => 'assets/game/character_icons/$codeName.webp';
  String get fullShotPath => 'assets/game/character_shots/$codeName.webp';
  String get displayName => _string('name', codeName);
  String get englishName => _string('name_en', codeName);
  String get description => _string('description', '暂无角色描述');
  String get title => _string('title', '');
  String get voiceActor => _string('cv', '未收录');
  int get rarity => _int('rarity');
  int get element => _int('element');
  String get race => _string('race', 'Unknown');
  String get gender => _string('gender', 'Unknown');
  String get leaderAbility => _string('leader_ability', '');

  List<String> get abilityIds => [
        for (var index = 1; index <= 6; index++) _string('ability_$index', ''),
      ].where((ability) => ability.isNotEmpty).toList();

  String _string(String key, String fallback) {
    final value = fields[key]?.toString().trim() ?? '';
    return value.isEmpty ? fallback : value;
  }

  int _int(String key) => int.tryParse(fields[key]?.toString() ?? '') ?? 0;
}

class AbilityRecord {
  const AbilityRecord({required this.id, required this.fields, this.descriptions = const []});

  final String id;
  final Map<String, dynamic> fields;
  final List<String> descriptions;

  String get stringId => _string('string_id', id);
  String get chineseDescription => descriptions.isEmpty ? stringId : descriptions.join('\n');
  String get rarity => _string('rarity', '未定义');
  String get trigger => _string('trigger', '未定义');
  int get battlePower => _int('battle_power');

  List<String> get triggerDetails {
    const triggerKeys = [
      'trigger.values.precondition',
      'trigger.values.precondition2',
      'trigger.values.precondition3',
      'trigger.values.instant_trigger',
      'trigger.values.during_trigger',
      'trigger.values.opening',
    ];
    return [
      for (final key in triggerKeys)
        if (_hasValue(fields[key])) key.replaceFirst('trigger.values.', ''),
    ];
  }

  String _string(String key, String fallback) {
    final value = fields[key]?.toString().trim() ?? '';
    return value.isEmpty ? fallback : value;
  }

  int _int(String key) => int.tryParse(fields[key]?.toString() ?? '') ?? 0;

  static bool _hasValue(Object? value) {
    if (value == null) return false;
    if (value is num) return value != 0;
    final text = value.toString().trim();
    return text.isNotEmpty && text != '0';
  }
}

class CharacterRepository {
  const CharacterRepository({required this.characters, required this.abilities});

  final List<CharacterRecord> characters;
  final Map<String, AbilityRecord> abilities;

  static Future<CharacterRepository> load() async {
    final characterContent = await rootBundle.loadString(
      'assets/exported/master_character_character.json',
    );
    final textContent = await rootBundle.loadString(
      'assets/exported/master_character_character_text.json',
    );
    final abilityContent = await rootBundle.loadString(
      'assets/exported/master_ability_ability.json',
    );
    final descriptionContent = await rootBundle.loadString(
      'assets/exported/ability_descriptions.json',
    );
    final decoded = jsonDecode(characterContent) as Map<String, dynamic>;
    final textDecoded = jsonDecode(textContent) as Map<String, dynamic>;
    final abilityDecoded = jsonDecode(abilityContent) as Map<String, dynamic>;
    final descriptionDecoded = jsonDecode(descriptionContent) as Map<String, dynamic>;
    final characters = decoded.entries
        .map((entry) {
          final fields = Map<String, dynamic>.from(entry.value as Map);
          final textFields = textDecoded[entry.key];
          if (textFields is Map) {
            fields.addAll(Map<String, dynamic>.from(textFields));
          }
          return CharacterRecord(id: entry.key, fields: fields);
        })
        .toList()
      ..sort((first, second) => second.rarity.compareTo(first.rarity));
    final abilities = <String, AbilityRecord>{};
    for (final entry in abilityDecoded.entries) {
      final value = entry.value;
      final fields = value is List && value.isNotEmpty
          ? value.first
          : value;
      if (fields is Map) {
        abilities[entry.key] = AbilityRecord(
          id: entry.key,
          fields: Map<String, dynamic>.from(fields),
          descriptions: [
            for (final item in (descriptionDecoded[entry.key] as List? ?? const []))
              item.toString(),
          ],
        );
      }
    }
    return CharacterRepository(characters: characters, abilities: abilities);
  }
}

class WorldFlipperApp extends StatefulWidget {
  const WorldFlipperApp({super.key});

  @override
  State<WorldFlipperApp> createState() => _WorldFlipperAppState();
}

class _WorldFlipperAppState extends State<WorldFlipperApp> {
  final _authService = AuthService();
  late final Future<Player?> _initialPlayer = _restoreSession();
  Player? _player;

  Future<Player?> _restoreSession() async {
    if (!await _authService.isLoggedIn()) return null;
    return _authService.getPlayerInfo();
  }

  void _onLoggedIn(Player player) => setState(() => _player = player);

  Future<void> _logout() async {
    await _authService.logout();
    if (mounted) setState(() => _player = null);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'World Flipper Research Client',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xffe4572e),
          brightness: Brightness.light,
        ),
        scaffoldBackgroundColor: const Color(0xfff7f3ed),
        useMaterial3: true,
      ),
      home: _player != null
          ? ResearchHomePage(player: _player!, onLogout: _logout)
          : FutureBuilder<Player?>(
              future: _initialPlayer,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Scaffold(body: Center(child: CircularProgressIndicator()));
                }
                if (snapshot.hasData) {
                  WidgetsBinding.instance.addPostFrameCallback((_) {
                    if (mounted && _player == null) setState(() => _player = snapshot.data);
                  });
                  return const Scaffold(body: Center(child: CircularProgressIndicator()));
                }
                return LoginPage(onLoggedIn: _onLoggedIn);
              },
            ),
    );
  }
}

class CharacterHomePage extends StatefulWidget {
  const CharacterHomePage({this.player, super.key});

  final Player? player;

  @override
  State<CharacterHomePage> createState() => _CharacterHomePageState();
}

class ResearchHomePage extends StatefulWidget {
  const ResearchHomePage({required this.player, required this.onLogout, super.key});

  final Player player;
  final Future<void> Function() onLogout;

  @override
  State<ResearchHomePage> createState() => _ResearchHomePageState();
}

class _ResearchHomePageState extends State<ResearchHomePage> {
  int _selectedIndex = 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _selectedIndex,
        children: [CharacterHomePage(player: widget.player), const GachaPage()],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: (index) => setState(() => _selectedIndex = index),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.people_outline), label: '角色'),
          NavigationDestination(icon: Icon(Icons.casino_outlined), label: '扭蛋'),
        ],
      ),
    );
  }
}

class _CharacterHomePageState extends State<CharacterHomePage> {
  late final Future<CharacterRepository> _repository = CharacterRepository.load();
  String _search = '';
  int? _element;
  List<OwnedCharacter>? _ownedCharacters;
  bool _showLocked = false;

  @override
  void initState() {
    super.initState();
    _loadOwnedCharacters();
  }

  Future<void> _loadOwnedCharacters() async {
    try {
      final ownedList = await AuthService().getOwnedCharacters();
      debugPrint('获取到已拥有角色列表，共 ${ownedList.length} 个');
      for (var i = 0; i < ownedList.length && i < 15; i++) {
        final c = ownedList[i];
        debugPrint('  [$i] id=${c.id} (type: ${c.id.runtimeType}), entryCount=${c.entryCount}');
      }
      if (mounted) {
        setState(() {
          _ownedCharacters = ownedList;
        });
      }
    } catch (e) {
      debugPrint('获取已拥有角色列表失败: $e');
      if (mounted) {
        setState(() {
          _ownedCharacters = [];
        });
      }
    }
  }

  /// 获取角色的拥有信息（用于显示重复数等）
  OwnedCharacter? _getOwnedInfo(String characterId) {
    try {
      final idAsInt = int.tryParse(characterId);
      if (idAsInt == null) return null;
      return _ownedCharacters!.firstWhere(
        (c) => c.id == idAsInt,
      );
    } catch (e) {
      debugPrint('_getOwnedInfo 错误: $e');
      return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('世界弹射物语 · 研究客户端'),
        actions: [
          IconButton(
            onPressed: () => setState(() {}),
            icon: const Icon(Icons.refresh),
            tooltip: '重新加载数据',
          ),
        ],
      ),
      body: FutureBuilder<CharacterRepository>(
        future: _repository,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return Center(child: Text('数据加载失败：${snapshot.error}'));
          }
          if (!snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final characters = snapshot.data!.characters.where(_matches).toList();
          final ownedCount = _ownedCharacters?.length ?? 0;
          final totalCount = characters.length;
          return Column(
            children: [
              if (widget.player != null) _PlayerStatusBar(player: widget.player!),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 8),
                child: Row(
                  children: [
                    const Text('角色列表', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                    const Spacer(),
                    if (_ownedCharacters != null)
                      Text(
                        '已拥有 $ownedCount / $totalCount',
                        style: const TextStyle(fontSize: 12, color: Colors.grey),
                      ),
                    const SizedBox(width: 8),
                    Switch(
                      value: _showLocked,
                      onChanged: (value) => setState(() => _showLocked = value),
                      trackColor: WidgetStateProperty.all(Colors.grey),
                    ),
                    const SizedBox(width: 4),
                    const Text('显示未拥有'),
                  ],
                ),
              ),
              _buildHeader(snapshot.data!.characters.length, characters.length),
              Expanded(
                child: characters.isEmpty
                    ? const Center(child: Text('没有匹配的角色'))
                    : GridView.builder(
                        padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
                        gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                          maxCrossAxisExtent: 310,
                          mainAxisExtent: 142,
                          crossAxisSpacing: 12,
                          mainAxisSpacing: 12,
                        ),
                        itemCount: characters.length,
                        itemBuilder: (context, index) {
                          final character = characters[index];
                          debugPrint('角色 ${character.id} (${character.codeName}) 检查中...');
                          final ownedInfo = _getOwnedInfo(character.id);
                          final isOwned = ownedInfo != null;
                          if (index < 5) {
                            debugPrint('  [前5个] character.id=${character.id}, isOwned=$isOwned');
                          }
                          return _CharacterCard(
                            character: character,
                            isOwned: isOwned,
                            ownedInfo: ownedInfo,
                            onTap: isOwned ? () => _showDetails(context, snapshot.data!, character) : null,
                          );
                        },
                      ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildHeader(int total, int visible) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
      child: Wrap(
        spacing: 12,
        runSpacing: 10,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          SizedBox(
            width: 280,
            child: TextField(
              onChanged: (value) => setState(() => _search = value.trim().toLowerCase()),
              decoration: const InputDecoration(
                labelText: '搜索角色编号或名称',
                prefixIcon: Icon(Icons.search),
                border: OutlineInputBorder(),
              ),
            ),
          ),
          DropdownButton<int?>(
            value: _element,
            hint: const Text('全部属性'),
            items: [
              const DropdownMenuItem<int?>(value: null, child: Text('全部属性')),
              for (var element = 0; element < 6; element++)
                DropdownMenuItem(value: element, child: Text(_elementName(element))),
            ],
            onChanged: (value) => setState(() => _element = value),
          ),
          Text('$visible / $total 个角色'),
        ],
      ),
    );
  }

  bool _matches(CharacterRecord character) {
    final haystack = '${character.id} ${character.codeName} ${character.displayName}'.toLowerCase();
    return haystack.contains(_search) &&
        (_element == null || character.element == _element);
  }

  void _showDetails(
    BuildContext context,
    CharacterRepository repository,
    CharacterRecord character,
  ) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('${character.displayName}  ·  ${character.id}'),
        content: SizedBox(
          width: 440,
          child: ListView(
            shrinkWrap: true,
            children: [
              CharacterPortrait(character: character),
              const SizedBox(height: 12),
              Text(character.title.isEmpty ? '暂无角色标题' : character.title),
              const SizedBox(height: 8),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  CharacterPortrait(character: character),
                  const SizedBox(width: 12),
                  Expanded(child: Text(character.description)),
                ],
              ),
              const Divider(),
              Text('英文名：${character.englishName}'),
              Text('CV：${character.voiceActor}'),
              const SizedBox(height: 12),
              Text('稀有度 ${character.rarity}  ·  ${_elementName(character.element)}'),
              Text('种族 ${character.race}  ·  ${character.gender}'),
              Text('队长技：${character.leaderAbility.isEmpty ? '未定义' : character.leaderAbility}'),
              const SizedBox(height: 12),
              Text('能力列表', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              if (character.abilityIds.isEmpty)
                const Text('未定义')
              else
                for (var index = 0; index < character.abilityIds.length; index++)
                  _AbilityCard(
                    index: index + 1,
                    abilityId: character.abilityIds[index],
                    ability: repository.abilities[character.abilityIds[index]],
                  ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('关闭')),
        ],
      ),
    );
  }
}

class CharacterPortrait extends StatelessWidget {
  const CharacterPortrait({required this.character, super.key});

  final CharacterRecord character;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(maxHeight: 280),
      child: Image.asset(
        character.fullShotPath,
        fit: BoxFit.contain,
        errorBuilder: (context, error, stackTrace) => CharacterAvatar(
          character: character,
          size: 120,
        ),
      ),
    );
  }
}

class _AbilityCard extends StatelessWidget {
  const _AbilityCard({
    required this.index,
    required this.abilityId,
    required this.ability,
  });

  final int index;
  final String abilityId;
  final AbilityRecord? ability;

  @override
  Widget build(BuildContext context) {
    if (ability == null) {
      return Card(
        child: ListTile(
          leading: CircleAvatar(child: Text('$index')),
          title: Text('能力槽 $index · $abilityId'),
          subtitle: const Text('能力表中未找到对应记录'),
        ),
      );
    }

    final record = ability!;
    return Card(
      child: ListTile(
        leading: CircleAvatar(child: Text('$index')),
        title: Text(record.chineseDescription),
        subtitle: Text(
          'ID：$abilityId · ${record.stringId}\n'
          '类别：${record.rarity}  ·  战斗力：${record.battlePower}\n'
          '触发：${record.triggerDetails.isEmpty ? record.trigger : record.triggerDetails.join('、')}',
        ),
        isThreeLine: true,
      ),
    );
  }
}

class _PlayerStatusBar extends StatelessWidget {
  const _PlayerStatusBar({required this.player});

  final Player player;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.fromLTRB(20, 12, 20, 0),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Wrap(
          spacing: 18,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text(player.name.isEmpty ? '玩家 #${player.id}' : player.name, style: Theme.of(context).textTheme.titleMedium),
            Text('等级 ${player.rankPoint}'),
            Text('体力 ${player.stamina}/10'),
            Text('金币 ${player.vmoney + player.freeVmoney}'),
          ],
        ),
      ),
    );
  }
}

class _CharacterCard extends StatelessWidget {
  const _CharacterCard({
    required this.character,
    required this.isOwned,
    required this.ownedInfo,
    required this.onTap,
  });

  final CharacterRecord character;
  final bool isOwned;
  final OwnedCharacter? ownedInfo;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
      color: isOwned ? null : Colors.grey.withValues(alpha: 0.3),
      child: InkWell(
        onTap: onTap,
        child: Stack(
          children: [
            Row(
              children: [
                Container(width: 9, color: isOwned ? _elementColor(character.element) : Colors.grey),
                Padding(
                  padding: const EdgeInsets.all(12),
                  child: CharacterAvatar(character: character, size: 76),
                ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.all(15),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisAlignment: MainAxisAlignment.center,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                character.displayName,
                                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                  color: isOwned ? null : Colors.grey,
                                ),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            if (isOwned && ownedInfo!.entryCount > 1)
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                margin: const EdgeInsets.only(left: 4),
                                decoration: BoxDecoration(
                                  color: Colors.orange.shade100,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Text(
                                  'x${ownedInfo!.entryCount}',
                                  style: const TextStyle(fontSize: 11, color: Colors.orange),
                                ),
                              ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Text(
                          character.englishName,
                          style: const TextStyle(fontSize: 12, color: Colors.grey),
                        ),
                        Text(
                          character.title.isEmpty ? character.id : character.title,
                          style: const TextStyle(fontSize: 12, color: Colors.grey),
                        ),
                        if (!isOwned) ...[
                          const SizedBox(height: 8),
                          const Row(
                            children: [
                              Icon(Icons.lock_outline, size: 14, color: Colors.grey),
                              SizedBox(width: 4),
                              Text('未获得', style: TextStyle(fontSize: 12, color: Colors.grey)),
                            ],
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.only(right: 12),
                  child: isOwned
                      ? (ownedInfo != null && (ownedInfo!.evolutionLevel > 0 || ownedInfo!.overLimitStep > 0)
                          ? Text(
                              '${ownedInfo!.evolutionLevel}.${ownedInfo!.overLimitStep}',
                              style: const TextStyle(fontSize: 10, color: Colors.grey),
                            )
                          : const Icon(Icons.chevron_right, size: 20, color: Colors.grey))
                      : null,
                ),
              ],
            ),
            if (!isOwned)
              Container(
                color: Colors.black.withValues(alpha: 0.4),
                child: const Center(
                  child: Icon(Icons.lock, color: Colors.white, size: 32),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class CharacterAvatar extends StatelessWidget {
  const CharacterAvatar({required this.character, required this.size, super.key});

  final CharacterRecord character;
  final double size;

  @override
  Widget build(BuildContext context) {
    return ClipOval(
      child: Image.asset(
        character.iconPath,
        width: size,
        height: size,
        fit: BoxFit.cover,
        errorBuilder: (context, error, stackTrace) => _AvatarFallback(
          character: character,
          size: size,
        ),
      ),
    );
  }
}

class _AvatarFallback extends StatelessWidget {
  const _AvatarFallback({required this.character, required this.size});

  final CharacterRecord character;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      color: _elementColor(character.element).withValues(alpha: 0.2),
      alignment: Alignment.center,
      child: Text(
        character.displayName.isEmpty ? '?' : character.displayName.substring(0, 1),
        style: TextStyle(
          color: _elementColor(character.element),
          fontSize: size * 0.38,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }
}

String _elementName(int element) => const ['火', '水', '雷', '风', '光', '暗'][element.clamp(0, 5)];

Color _elementColor(int element) => const [
      Color(0xffe4572e),
      Color(0xff2878c8),
      Color(0xffd89b16),
      Color(0xff43a047),
      Color(0xffd8a928),
      Color(0xff6d4c8d),
    ][element.clamp(0, 5)];
