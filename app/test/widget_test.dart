import 'package:flutter_test/flutter_test.dart';
import 'package:nestra/models.dart';
import 'package:nestra/state/home_controller.dart';

Map<String, dynamic> _snapshot() => {
      'name': 'Test Home',
      'time': '2026-11-09T14:00:00',
      'outside': {'temperature': 30.0, 'humidity': 70.0},
      'rooms': [
        {
          'id': 'living_room',
          'name': 'Living Room',
          'environment': {'temperature': 27.5, 'humidity': 65.0, 'ambient_light': 40.0, 'occupied': true},
          'devices': [
            {'id': 'fan', 'type': 'fan', 'name': 'Air Circulator', 'room_id': 'living_room', 'on': true, 'speed': 85.0},
            {'id': 'lamp', 'type': 'light', 'name': 'Lamp', 'room_id': 'living_room', 'on': false, 'brightness': 40.0},
          ],
        },
      ],
      'activity': [
        {'id': 1, 'time': '2026-11-09T13:59:00', 'title': 'Simulator started', 'detail': '', 'source': 'system'},
      ],
    };

void main() {
  test('snapshot populates rooms, devices and activity', () {
    final c = HomeController()..handleMessage({'type': 'snapshot', 'data': _snapshot()});
    expect(c.loaded, isTrue);
    expect(c.selectedRoom?.name, 'Living Room');
    expect(c.devicesIn('living_room').map((d) => d.name), ['Air Circulator', 'Lamp']);
    expect(c.activity.single.title, 'Simulator started');
  });

  test('live events update state', () {
    final c = HomeController()..handleMessage({'type': 'snapshot', 'data': _snapshot()});
    c.handleMessage({
      'type': 'device',
      'data': {'id': 'fan', 'type': 'fan', 'name': 'Air Circulator', 'room_id': 'living_room', 'on': true, 'speed': 55.0, 'source': 'voice'},
    });
    c.handleMessage({
      'type': 'environment',
      'data': {'room_id': 'living_room', 'temperature': 26.0, 'humidity': 60.0, 'ambient_light': 30.0, 'occupied': true},
    });
    c.handleMessage({
      'type': 'activity',
      'data': {'id': 2, 'time': '2026-11-09T14:01:00', 'title': 'Fan lowered', 'source': 'voice'},
    });
    expect(c.devices['fan']!.speed, 55);
    expect(c.selectedRoom!.environment.temperature, 26);
    expect(c.activity.first.title, 'Fan lowered');
  });

  test('command result parses clarification options and fuzzy explanations', () {
    final r = CommandResult.fromJson({
      'ok': false,
      'reply': 'Which AC?',
      'needs_clarification': true,
      'options': [
        {'room_id': 'bedroom', 'room_name': 'Bedroom'},
      ],
      'explanations': [
        {
          'device_name': 'Fan',
          'system': 'fan_comfort',
          'output': 'fan_speed',
          'value': 54.5,
          'term': 'medium',
          'inputs': {'temperature': 27.5},
          'rules': [
            {'rule': 'IF temperature is warm THEN fan_speed is medium', 'strength': 0.33},
          ],
        },
      ],
    });
    expect(r.options.single.roomName, 'Bedroom');
    expect(r.explanations.single.rules.single.strength, closeTo(0.33, 1e-9));
  });
}
