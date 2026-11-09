import 'package:flutter/material.dart';

import '../models.dart';
import '../state/home_controller.dart';
import '../theme.dart';
import 'device_tile.dart' show toggleLock;
import 'manage_dialogs.dart';

/// Room summary card in the "Rooms" grid. Tap to show that room's devices above.
class RoomCard extends StatelessWidget {
  const RoomCard({
    super.key,
    required this.room,
    required this.devices,
    required this.selected,
    required this.controller,
  });

  final Room room;
  final List<Device> devices;
  final bool selected;
  final HomeController controller;

  @override
  Widget build(BuildContext context) {
    final powered = devices.where((d) => d.isPowered).toList();
    final anyOn = powered.any((d) => d.on);
    final lock = devices.where((d) => d.type == 'lock').firstOrNull;
    final active = devices.any((d) => d.isActive);
    final types = {for (final d in devices) d.type}.toList();

    return Material(
      color: selected ? NestraColors.cardRaised : NestraColors.card,
      borderRadius: BorderRadius.circular(18),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: () => controller.selectRoom(room.id),
        onLongPress: () => showRoomForm(context, controller, room: room),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
            border: Border.all(
              color: selected ? NestraColors.purple.withValues(alpha: 0.7) : NestraColors.border,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(room.name, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                  ),
                  Container(
                    width: 7,
                    height: 7,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: active ? NestraColors.orange : NestraColors.textMuted,
                    ),
                  ),
                  const SizedBox(width: 2),
                  SizedBox.square(
                    dimension: 26,
                    child: IconButton(
                      tooltip: 'Edit room',
                      padding: EdgeInsets.zero,
                      iconSize: 16,
                      color: NestraColors.textMuted,
                      onPressed: () => showRoomForm(context, controller, room: room),
                      icon: const Icon(Icons.more_horiz_rounded),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                _summary(),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 12, color: NestraColors.textSecondary, height: 1.4),
              ),
              const Spacer(),
              Row(
                children: [
                  for (final t in types.take(4))
                    Padding(
                      padding: const EdgeInsets.only(right: 4),
                      child: CircleAvatar(
                        radius: 13,
                        backgroundColor: colorForDevice(t).withValues(alpha: 0.18),
                        child: Icon(iconForDevice(t), size: 14, color: colorForDevice(t)),
                      ),
                    ),
                  const Spacer(),
                  if (lock != null)
                    FilledButton.tonal(
                      style: FilledButton.styleFrom(
                        backgroundColor: NestraColors.purple,
                        foregroundColor: Colors.white,
                        visualDensity: VisualDensity.compact,
                        padding: const EdgeInsets.symmetric(horizontal: 14),
                      ),
                      onPressed: () => toggleLock(context, controller, lock),
                      child: Text(lock.locked ? 'Unlock' : 'Lock'),
                    )
                  else if (powered.isNotEmpty)
                    Switch(
                      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      value: anyOn,
                      onChanged: (on) => controller.setRoomPower(room.id, on),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _summary() {
    final env = room.environment;
    final parts = <String>[];
    final ac = devices.where((d) => d.type == 'ac' && d.on).firstOrNull;
    final acText = ac == null
        ? null
        : switch (ac.mode) {
            'heat' => 'Heating to ${formatTemp(ac.setpoint)}',
            'dry' => 'Drying the air',
            'fan' => 'Aircond fan only',
            _ => 'Cooling to ${formatTemp(ac.setpoint)}',
          };
    parts.add('${formatTemp(env.temperature)} · ${acText ?? '${env.humidity.round()}% humidity'}');

    final lights = devices.where((d) => d.type == 'light').toList();
    final lit = lights.where((d) => d.on).toList();
    if (lights.isNotEmpty) {
      if (lit.isEmpty) {
        parts.add('Lights off');
      } else {
        final avg = lit.map((d) => d.brightness).reduce((a, b) => a + b) / lit.length;
        parts.add('${lit.length} light${lit.length == 1 ? '' : 's'} on · ${avg.round()}% brightness');
      }
    }
    final lock = devices.where((d) => d.type == 'lock').firstOrNull;
    if (lock != null) parts.add(lock.locked ? 'Locked' : 'Unlocked');
    return parts.join('\n');
  }
}
