import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';

import '../models/player.dart';
import '../services/battle_service.dart';
import '../../network/dio_client.dart';

class BattlePage extends StatefulWidget {
  const BattlePage({
    super.key,
    required this.player,
    required this.characterIds,
    required this.onBack,
    this.questId = 9001001,
    this.category = BattleService.questCategoryMain,
  });

  final Player player;
  final List<String> characterIds;
  final VoidCallback onBack;
  final int questId;
  final int category;

  @override
  State<BattlePage> createState() => _BattlePageState();
}

enum _BattleState {
  preparing,  // 战斗中…
  fighting,   // 模拟中
  result,     // 结算
}

class _BattlePageState extends State<BattlePage> {
  late final BattleService _battleService;
  _BattleState _state = _BattleState.preparing;
  String _statusText = '正在进入关卡…';
  BattleFinishData? _result;
  String? _errorMsg;
  int _staminaRemaining = 0;
  Timer? _fightTimer;
  int _elapsedMs = 0;

  // 模拟用的队伍（取传入的角色 ID）
  late final List<int> _partyIds;
  int _currentStep = 0;
  final Random _rand = Random();

  @override
  void initState() {
    super.initState();
    _battleService = BattleService(DioClient.instance);
    // 将字符串 ID（如"111001"）转为 int，取前5个作为队伍
    _partyIds = widget.characterIds
        .map((s) => int.tryParse(s))
        .whereType<int>()
        .take(5)
        .toList();
    _startBattle();
  }

  @override
  void dispose() {
    _fightTimer?.cancel();
    super.dispose();
  }

  Future<void> _startBattle() async {
    setState(() {
      _state = _BattleState.preparing;
      _statusText = '正在进入关卡…';
      _errorMsg = null;
    });
    try {
      _staminaRemaining = await _battleService.startBattle(
        questId: widget.questId,
        category: widget.category,
        partyId: 1,
      );
      if (!mounted) return;
      setState(() => _state = _BattleState.fighting);
      _simulateFight();
    } on BattleException catch (e) {
      if (!mounted) return;
      setState(() {
        _state = _BattleState.result;
        _errorMsg = e.message;
      });
    }
  }

  void _simulateFight() {
    const totalMs = 3000;
    const interval = 100;
    var elapsed = 0;

    _fightTimer = Timer.periodic(const Duration(milliseconds: interval), (timer) {
      elapsed += interval;
      _elapsedMs = elapsed;
      _currentStep = (elapsed / totalMs * 5).toInt().clamp(0, 5);

      if (elapsed >= totalMs) {
        timer.cancel();
        _finishBattle(elapsed);
      } else {
        setState(() {});
      }
    });
  }

  Future<void> _finishBattle(int elapsedMs) async {
    try {
      final result = await _battleService.finishBattle(
        questId: widget.questId,
        category: widget.category,
        isAccomplished: true,
        score: _rand.nextInt(5000) + 5000,
        elapsedTimeMs: elapsedMs,
        partyCharacterIds: _partyIds,
        maxCombo: _rand.nextInt(20) + 5,
      );
      if (!mounted) return;
      setState(() {
        _state = _BattleState.result;
        _result = result;
        _errorMsg = null;
      });
    } on BattleException catch (e) {
      if (!mounted) return;
      setState(() {
        _state = _BattleState.result;
        _errorMsg = e.message;
      });
    }
  }

  bool get _canStartBattle => _staminaRemaining > 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('战斗'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: _state == _BattleState.fighting
              ? null
              : widget.onBack,
        ),
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    switch (_state) {
      case _BattleState.preparing:
        return const Center(child: CircularProgressIndicator());
      case _BattleState.fighting:
        return _buildFighting();
      case _BattleState.result:
        return _errorMsg != null
            ? _buildError()
            : _result != null
                ? _buildResult()
                : _buildNoBattle();
    }
  }

  Widget _buildFighting() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(
            width: 120,
            height: 120,
            child: CircularProgressIndicator(strokeWidth: 6),
          ),
          const SizedBox(height: 24),
          Text(
            '战斗中… $_elapsedMs ms',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 8),
          Text(
            '队伍: ${_partyIds.take(_currentStep).length}/${_partyIds.length} 回合',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
        ],
      ),
    );
  }

  Widget _buildResult() {
    final r = _result!;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildResultCard(
            title: '战斗完成！',
            subtitle: '评分: ${r.clearRank}S',
          ),
          const SizedBox(height: 12),
          _buildRewardRow('排名积分', '+${r.newRankPoint} RP'),
          _buildRewardRow('自由币', '+${r.newFreeVmoney}'),
          _buildRewardRow('法力', '+${r.newFreeMana}'),
          _buildRewardRow('经验池', '+${r.newExpPool}'),
          _buildRewardRow('剩余体力', '${r.newStamina} / $_staminaRemaining'),
          if (r.items.isNotEmpty) ...[
            const SizedBox(height: 12),
            const Text('掉落物品:', style: TextStyle(fontWeight: FontWeight.bold)),
            for (final entry in r.items.entries)
              _buildRewardRow(entry.key, '+${entry.value}'),
          ],
          if (r.characters.isNotEmpty) ...[
            const SizedBox(height: 12),
            const Text('获得角色:', style: TextStyle(fontWeight: FontWeight.bold)),
            for (final c in r.characters)
              _buildRewardRow(c['name']?.toString() ?? '', '+${c['entryCount']}'),
          ],
          const SizedBox(height: 24),
          FilledButton(
            onPressed: () {
              if (_canStartBattle) {
                _startBattle();
              }
            },
            child: Text(
              _canStartBattle ? '再来一次' : '体力不足',
              style: const TextStyle(color: Colors.white),
            ),
          ),
          const SizedBox(height: 12),
          OutlinedButton(
            onPressed: widget.onBack,
            child: const Text('返回'),
          ),
        ],
      ),
    );
  }

  Widget _buildResultCard({
    required String title,
    required String subtitle,
  }) {
    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Text(title,
                style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 4),
            Text(subtitle,
                style: Theme.of(context).textTheme.titleMedium),
          ],
        ),
      ),
    );
  }

  Widget _buildRewardRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label),
          Text(value,
              style: const TextStyle(fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }

  Widget _buildError() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 64, color: Colors.red),
            const SizedBox(height: 16),
            Text(
              _errorMsg ?? '战斗失败',
              style: Theme.of(context).textTheme.titleLarge,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: () {
                if (_canStartBattle) {
                  _startBattle();
                }
              },
              child: Text(_canStartBattle ? '重试' : '体力不足'),
            ),
            const SizedBox(height: 12),
            OutlinedButton(
              onPressed: widget.onBack,
              child: const Text('返回'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNoBattle() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('尚未开始战斗'),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _canStartBattle ? _startBattle : null,
            child: Text(_canStartBattle ? '开始战斗' : '体力不足 ($_staminaRemaining)'),
          ),
        ],
      ),
    );
  }
}
