class Player {
  const Player({
    required this.id,
    required this.name,
    required this.stamina,
    required this.vmoney,
    required this.freeVmoney,
    required this.rankPoint,
    required this.role,
    required this.totalLoginDays,
    this.staminaHealTime,
  });

  final int id;
  final String name;
  final int stamina;
  final int vmoney;
  final int freeVmoney;
  final int rankPoint;
  final int role;
  final int totalLoginDays;
  final DateTime? staminaHealTime;

  factory Player.fromJson(Map<String, dynamic> json) {
    return Player(
      id: _int(json['id']),
      name: json['name']?.toString() ?? '',
      stamina: _int(json['stamina']),
      vmoney: _int(json['vmoney']),
      freeVmoney: _int(json['freeVmoney']),
      rankPoint: _int(json['rankPoint']),
      role: _int(json['role']),
      totalLoginDays: _int(json['totalLoginDays']),
      staminaHealTime: DateTime.tryParse(json['staminaHealTime']?.toString() ?? ''),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'stamina': stamina,
        'vmoney': vmoney,
        'freeVmoney': freeVmoney,
        'rankPoint': rankPoint,
        'role': role,
        'totalLoginDays': totalLoginDays,
        'staminaHealTime': staminaHealTime?.toIso8601String(),
      };

  static int _int(Object? value) => value is num ? value.toInt() : int.tryParse('$value') ?? 0;
}