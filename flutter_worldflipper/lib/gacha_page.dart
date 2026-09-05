import 'package:flutter/material.dart';

import 'gacha_repository.dart';
import 'gacha_service.dart';

class GachaPage extends StatefulWidget {
  const GachaPage({super.key});

  @override
  State<GachaPage> createState() => _GachaPageState();
}

class _GachaPageState extends State<GachaPage> {
  late final Future<GachaRepository> _repository = GachaRepository.load();
  GachaRecord? _selected;
  GachaService? _service;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<GachaRepository>(
      future: _repository,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return Center(child: Text('扭蛋数据加载失败：${snapshot.error}'));
        }
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        final repository = snapshot.data!;
        _service ??= GachaService(repository);
        _selected ??= repository.gachas.isEmpty ? null : repository.gachas.first;
        if (_selected == null) return const Center(child: Text('没有可用的角色扭蛋池'));
        return _buildContent(context, repository);
      },
    );
  }

  Widget _buildContent(BuildContext context, GachaRepository repository) {
    final gacha = _selected!;
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
      children: [
        Text('扭蛋', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 12),
        DropdownButtonFormField<GachaRecord>(
          initialValue: gacha,
          decoration: const InputDecoration(labelText: '选择扭蛋池', border: OutlineInputBorder()),
          items: [
            for (final item in repository.gachas)
              DropdownMenuItem(value: item, child: Text(item.name)),
          ],
          onChanged: (value) => setState(() => _selected = value),
        ),
        const SizedBox(height: 16),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(gacha.name, style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 10),
                Text('消耗：${gacha.currencyLabel}'),
                Text('单抽：${gacha.singleCost}  ·  十连：${gacha.multiCost}'),
                Text('概率配置：${gacha.rarityOddsId}'),
                Text('十连保底：${gacha.guaranteeRarity > 0 ? '${gacha.guaranteeRarity} 星' : '无记录'}'),
              ],
            ),
          ),
        ),
        const SizedBox(height: 14),
        Row(
          children: [
            Expanded(
              child: FilledButton.icon(
                onPressed: () => _draw(context, gacha.id, 1),
                icon: const Icon(Icons.casino_outlined),
                label: const Text('单抽'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: FilledButton.tonalIcon(
                onPressed: () => _draw(context, gacha.id, 10),
                icon: const Icon(Icons.auto_awesome),
                label: const Text('十连抽'),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Future<void> _draw(BuildContext context, String gachaId, int count) async {
    final service = _service;
    if (service == null) return;
    final showLoading = count > 1;
    if (showLoading && context.mounted) {
      showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (context) => const Center(child: CircularProgressIndicator()),
      );
    }
    try {
      final results = await service.draw(gachaId, count: count);
      if (!context.mounted) return;
      if (showLoading) Navigator.pop(context);
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(count == 1 ? '单抽结果' : '十连抽结果'),
          content: SizedBox(
            width: 440,
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final result in results)
                  Chip(
                    avatar: CircleAvatar(child: Text('${result.character.rarity}')),
                    label: Text('${result.character.name}  ★${result.character.rarity}'),
                  ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('关闭')),
          ],
        ),
      );
    } on GachaException catch (error) {
      if (!context.mounted) return;
      if (showLoading) Navigator.pop(context);
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('抽卡失败'),
          content: Text(error.toString()),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('确定')),
          ],
        ),
      );
    }
  }
}
