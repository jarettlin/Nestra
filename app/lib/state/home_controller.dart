import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models.dart';
import '../services/api.dart';
import '../services/live.dart';

/// Holds the whole home's state and keeps it in sync with the backend.
///
/// The WebSocket is the source of truth: it sends a snapshot on connect, then
/// device / environment / activity events. User actions go out over REST and
/// are applied optimistically so sliders feel instant.
class HomeController extends ChangeNotifier {
  HomeController({NestraApi? api, LiveConnection? live, TokenProvider? token})
      : api = api ?? NestraApi(token: token),
        live = live ?? LiveConnection(token: token);

  final NestraApi api;
  final LiveConnection live;
  StreamSubscription<Map<String, dynamic>>? _sub;

  bool loaded = false;
  String homeName = '';
  DateTime? time;
  double outsideTemperature = 0;
  List<Room> rooms = [];
  final Map<String, Device> devices = {};
  List<ActivityEntry> activity = [];
  String? selectedRoomId;

  /// Last action error, shown once by the UI then cleared.
  String? error;

  bool get online => live.connected.value;

  Room? get selectedRoom {
    if (rooms.isEmpty) return null;
    return rooms.firstWhere((r) => r.id == selectedRoomId, orElse: () => rooms.first);
  }

  List<Device> devicesIn(String roomId) =>
      devices.values.where((d) => d.roomId == roomId).toList();

  void start() {
    _sub = live.messages.listen(handleMessage);
    live.connected.addListener(notifyListeners);
    live.start();
  }

  void selectRoom(String roomId) {
    selectedRoomId = roomId;
    notifyListeners();
  }

  @visibleForTesting
  void handleMessage(Map<String, dynamic> msg) {
    final data = msg['data'];
    switch (msg['type']) {
      case 'snapshot':
        _applySnapshot(data as Map<String, dynamic>);
      case 'device':
        final json = Map<String, dynamic>.of(data as Map<String, dynamic>)..remove('source');
        devices[json['id'] as String] = Device(json);
      case 'environment':
        final env = Environment.fromJson(data as Map<String, dynamic>);
        rooms = [
          for (final r in rooms) r.id == data['room_id'] ? r.withEnvironment(env) : r,
        ];
      case 'activity':
        final entry = ActivityEntry.fromJson(data as Map<String, dynamic>);
        if (activity.every((a) => a.id != entry.id)) {
          activity = [entry, ...activity].take(100).toList();
        }
      default:
        return;
    }
    notifyListeners();
  }

  void _applySnapshot(Map<String, dynamic> snap) {
    homeName = snap['name'] as String? ?? '';
    time = DateTime.tryParse(snap['time'] as String? ?? '');
    outsideTemperature = ((snap['outside'] as Map?)?['temperature'] as num?)?.toDouble() ?? 0;
    final roomList = (snap['rooms'] as List).cast<Map<String, dynamic>>();
    rooms = [
      for (final r in roomList)
        Room(
          id: r['id'] as String,
          name: r['name'] as String,
          environment: Environment.fromJson(r['environment'] as Map<String, dynamic>),
        ),
    ];
    devices
      ..clear()
      ..addAll({
        for (final r in roomList)
          for (final d in (r['devices'] as List).cast<Map<String, dynamic>>()) d['id'] as String: Device(d),
      });
    activity = [
      for (final a in (snap['activity'] as List? ?? []).cast<Map<String, dynamic>>())
        ActivityEntry.fromJson(a),
    ];
    if (rooms.every((r) => r.id != selectedRoomId)) {
      selectedRoomId = rooms.isEmpty ? null : rooms.first.id;
    }
    loaded = true;
  }

  /// Change device attributes, e.g. setDevice('fan_1', {'on': true, 'speed': 55}).
  Future<void> setDevice(String id, Map<String, dynamic> updates) async {
    final previous = devices[id];
    if (previous == null) return;
    devices[id] = previous.copyWith(updates);
    notifyListeners();
    try {
      await api.patchDevice(id, updates);
    } on ApiException catch (e) {
      devices[id] = previous;
      error = e.message;
      notifyListeners();
    }
  }

  Future<void> setRoomPower(String roomId, bool on) async {
    await Future.wait([
      for (final d in devicesIn(roomId))
        if (d.isPowered && d.on != on) setDevice(d.id, {'on': on}),
    ]);
  }

  // ------------------------------------------------------------ management
  // These wait for the backend and return an error message (null on success).
  // The WebSocket then delivers the updated home as a snapshot.

  Catalog? _catalog;

  Future<Catalog> catalog() async {
    try {
      return _catalog ??= await api.catalog();
    } on ApiException {
      return Catalog.fallback;
    }
  }

  Future<String?> _attempt(Future<void> Function() action) async {
    try {
      await action();
      return null;
    } on ApiException catch (e) {
      return e.message;
    }
  }

  Future<String?> addRoom(String name) => _attempt(() => api.createRoom(name));

  Future<String?> renameRoom(String id, String name) => _attempt(() => api.renameRoom(id, name));

  Future<String?> removeRoom(String id) => _attempt(() => api.deleteRoom(id));

  Future<String?> addDevice({required String type, required String name, required String roomId, String? kind}) =>
      _attempt(() => api.createDevice(type: type, name: name, roomId: roomId, kind: kind));

  /// Rename, move to another room, or change an appliance's kind.
  Future<String?> editDevice(String id, Map<String, dynamic> updates) =>
      _attempt(() => api.patchDevice(id, updates));

  Future<String?> removeDevice(String id) => _attempt(() => api.deleteDevice(id));

  /// Natural-language command. Defaults to the selected room as context, so
  /// "turn on the fan" means the fan in the room you're looking at.
  Future<CommandResult> runCommand(String text, {String? roomContext, bool confirm = false}) async {
    try {
      return await api.command(text, roomContext: roomContext ?? selectedRoomId, confirm: confirm);
    } on ApiException catch (e) {
      return CommandResult(ok: false, reply: e.message);
    }
  }

  String? takeError() {
    final e = error;
    error = null;
    return e;
  }

  @override
  void dispose() {
    _sub?.cancel();
    live.connected.removeListener(notifyListeners);
    live.dispose();
    super.dispose();
  }
}
