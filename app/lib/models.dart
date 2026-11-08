// Data models mirroring the backend JSON (see backend/README.md).

double _num(Object? v, [double fallback = 0]) => (v as num?)?.toDouble() ?? fallback;

class Device {
  const Device(this.json);

  /// Raw backend fields, kept as-is so new device attributes don't need model changes.
  final Map<String, dynamic> json;

  String get id => json['id'] as String;
  String get name => json['name'] as String;
  String get type => json['type'] as String;
  String get roomId => json['room_id'] as String;

  bool get on => json['on'] == true;
  double get brightness => _num(json['brightness']);
  double get speed => _num(json['speed']);
  double get setpoint => _num(json['setpoint'], 24);
  double get position => _num(json['position']);
  bool get locked => json['locked'] != false;
  String get mode => (json['mode'] as String?) ?? 'cool';

  bool get isPowered => type == 'light' || type == 'fan' || type == 'ac';

  /// Whether the device is "doing something" (drives status dots and highlights).
  bool get isActive => switch (type) {
        'blinds' => position > 0,
        'lock' => !locked,
        _ => on,
      };

  Device copyWith(Map<String, dynamic> changes) => Device({...json, ...changes});
}

class Environment {
  const Environment({
    required this.temperature,
    required this.humidity,
    required this.ambientLight,
    required this.occupied,
  });

  factory Environment.fromJson(Map<String, dynamic> j) => Environment(
        temperature: _num(j['temperature']),
        humidity: _num(j['humidity']),
        ambientLight: _num(j['ambient_light']),
        occupied: j['occupied'] != false,
      );

  final double temperature;
  final double humidity;
  final double ambientLight;
  final bool occupied;
}

class Room {
  const Room({required this.id, required this.name, required this.environment});

  final String id;
  final String name;
  final Environment environment;

  Room withEnvironment(Environment env) => Room(id: id, name: name, environment: env);
}

class ActivityEntry {
  const ActivityEntry({
    required this.id,
    required this.time,
    required this.title,
    required this.detail,
    required this.source,
  });

  factory ActivityEntry.fromJson(Map<String, dynamic> j) => ActivityEntry(
        id: j['id'] as int,
        time: DateTime.tryParse(j['time'] as String? ?? '') ?? DateTime.now(),
        title: j['title'] as String? ?? '',
        detail: j['detail'] as String? ?? '',
        source: j['source'] as String? ?? 'system',
      );

  final int id;
  final DateTime time;
  final String title;
  final String detail;
  final String source;
}

class RuleFiring {
  const RuleFiring(this.rule, this.strength);
  final String rule;
  final double strength;
}

/// The fuzzy engine's trace for one device: which rules fired and the result.
class Explanation {
  const Explanation({
    required this.deviceName,
    required this.system,
    required this.output,
    required this.value,
    required this.term,
    required this.inputs,
    required this.rules,
  });

  factory Explanation.fromJson(Map<String, dynamic> j) => Explanation(
        deviceName: j['device_name'] as String? ?? '',
        system: j['system'] as String? ?? '',
        output: j['output'] as String? ?? '',
        value: _num(j['value']),
        term: j['term'] as String? ?? '',
        inputs: {
          for (final e in ((j['inputs'] as Map?) ?? {}).entries) e.key as String: _num(e.value),
        },
        rules: [
          for (final r in (j['rules'] as List? ?? []))
            RuleFiring(r['rule'] as String, _num(r['strength'])),
        ],
      );

  final String deviceName;
  final String system;
  final String output;
  final double value;
  final String term;
  final Map<String, double> inputs;
  final List<RuleFiring> rules;
}

class RoomOption {
  const RoomOption(this.roomId, this.roomName);
  final String roomId;
  final String roomName;
}

class CommandResult {
  const CommandResult({
    required this.ok,
    required this.reply,
    this.needsClarification = false,
    this.needsConfirmation = false,
    this.options = const [],
    this.explanations = const [],
  });

  factory CommandResult.fromJson(Map<String, dynamic> j) => CommandResult(
        ok: j['ok'] == true,
        reply: j['reply'] as String? ?? '',
        needsClarification: j['needs_clarification'] == true,
        needsConfirmation: j['needs_confirmation'] == true,
        options: [
          for (final o in (j['options'] as List? ?? []))
            RoomOption(o['room_id'] as String, o['room_name'] as String),
        ],
        explanations: [
          for (final e in (j['explanations'] as List? ?? []))
            Explanation.fromJson(e as Map<String, dynamic>),
        ],
      );

  final bool ok;
  final String reply;
  final bool needsClarification;
  final bool needsConfirmation;
  final List<RoomOption> options;
  final List<Explanation> explanations;
}
