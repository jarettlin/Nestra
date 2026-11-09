import 'package:flutter/material.dart';

import '../models.dart';
import '../state/home_controller.dart';
import '../theme.dart';
import 'manage_dialogs.dart';

/// Details for one device: power, aircond temperature/mode/fan speed, and timers.
/// Stays live: it rebuilds from the controller as changes arrive.
Future<void> showDevicePanel(BuildContext context, HomeController controller, String deviceId) => showDialog(
      context: context,
      builder: (_) => _DevicePanel(controller: controller, deviceId: deviceId),
    );

const _modes = [
  ('cool', 'Cool', Icons.ac_unit_rounded),
  ('dry', 'Dry', Icons.water_drop_outlined),
  ('fan', 'Fan', Icons.air_rounded),
  ('heat', 'Heat', Icons.wb_sunny_outlined),
  ('auto', 'Auto', Icons.autorenew_rounded),
];
const _fanSpeeds = [('auto', 'Auto'), ('low', 'Low'), ('medium', 'Med'), ('high', 'High')];
const _offAfter = [(30, '30 min'), (60, '1 h'), (120, '2 h'), (240, '4 h'), (480, '8 h')];

String _clock(DateTime t) => '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';

class _DevicePanel extends StatelessWidget {
  const _DevicePanel({required this.controller, required this.deviceId});

  final HomeController controller;
  final String deviceId;

  void _set(Map<String, dynamic> updates) => controller.setDevice(deviceId, updates);

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final d = controller.devices[deviceId];
        if (d == null) {
          // Removed while open.
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (context.mounted) Navigator.of(context).maybePop();
          });
          return const SizedBox.shrink();
        }
        final roomName = controller.rooms.where((r) => r.id == d.roomId).firstOrNull?.name ?? '';
        final accent = colorForDevice(d.type);
        return Dialog(
          backgroundColor: NestraColors.panel,
          insetPadding: const EdgeInsets.all(16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(24),
            side: const BorderSide(color: NestraColors.border),
          ),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(22),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      CircleAvatar(
                        radius: 20,
                        backgroundColor: accent.withValues(alpha: d.on ? 0.2 : 0.08),
                        child: Icon(iconFor(d), color: d.on ? accent : NestraColors.textMuted),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(d.name, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
                            Text(roomName, style: const TextStyle(fontSize: 12.5, color: NestraColors.textSecondary)),
                          ],
                        ),
                      ),
                      if (d.isPowered) Switch(value: d.on, onChanged: (on) => _set({'on': on})),
                      IconButton(
                        tooltip: 'Edit device',
                        color: NestraColors.textSecondary,
                        onPressed: () {
                          Navigator.pop(context);
                          showDeviceForm(context, controller, device: d);
                        },
                        icon: const Icon(Icons.edit_outlined, size: 20),
                      ),
                    ],
                  ),
                  if (d.type == 'ac') ..._aircond(d),
                  if (d.isPowered) ..._timers(context, d),
                  const SizedBox(height: 6),
                  Align(
                    alignment: Alignment.centerRight,
                    child: TextButton(onPressed: () => Navigator.pop(context), child: const Text('Done')),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  List<Widget> _aircond(Device d) => [
        const SizedBox(height: 22),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            _Round(icon: Icons.remove_rounded, onTap: () => _nudge(d, -0.5)),
            const SizedBox(width: 24),
            Column(
              children: [
                Text(
                  formatTemp(d.setpoint),
                  style: TextStyle(
                    fontSize: 44,
                    fontWeight: FontWeight.w300,
                    color: d.on ? NestraColors.textPrimary : NestraColors.textMuted,
                  ),
                ),
                const Text('Target temperature', style: TextStyle(fontSize: 12, color: NestraColors.textSecondary)),
              ],
            ),
            const SizedBox(width: 24),
            _Round(icon: Icons.add_rounded, onTap: () => _nudge(d, 0.5)),
          ],
        ),
        const SizedBox(height: 22),
        const _Heading('Mode'),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final (value, label, icon) in _modes)
              ChoiceChip(
                avatar: Icon(icon, size: 16),
                label: Text(label),
                selected: d.mode == value,
                showCheckmark: false,
                selectedColor: NestraColors.purple.withValues(alpha: 0.25),
                backgroundColor: NestraColors.card,
                side: BorderSide(color: d.mode == value ? NestraColors.purple : NestraColors.border),
                onSelected: (_) => _set({'mode': value, 'on': true}),
              ),
          ],
        ),
        const SizedBox(height: 18),
        const _Heading('Fan speed'),
        SegmentedButton<String>(
          showSelectedIcon: false,
          style: SegmentedButton.styleFrom(
            backgroundColor: NestraColors.card,
            selectedBackgroundColor: NestraColors.textPrimary,
            selectedForegroundColor: NestraColors.background,
            foregroundColor: NestraColors.textSecondary,
            side: const BorderSide(color: NestraColors.border),
          ),
          segments: [for (final (v, l) in _fanSpeeds) ButtonSegment(value: v, label: Text(l))],
          selected: {d.fanSpeed},
          onSelectionChanged: (s) => _set({'fan_speed': s.first, 'on': true}),
        ),
      ];

  void _nudge(Device d, double delta) =>
      _set({'on': true, 'setpoint': (d.setpoint + delta).clamp(16.0, 30.0)});

  List<Widget> _timers(BuildContext context, Device d) => [
        const SizedBox(height: 22),
        const _Heading('Timers'),
        if (d.timerOffAt != null)
          _ActiveTimer(
            icon: Icons.timer_off_outlined,
            text: 'Turns off at ${_clock(d.timerOffAt!)}',
            onCancel: () => _set({'timer_off_at': null}),
          ),
        if (d.timerOnAt != null)
          _ActiveTimer(
            icon: Icons.alarm_on_outlined,
            text: 'Turns on at ${_clock(d.timerOnAt!)}',
            onCancel: () => _set({'timer_on_at': null}),
          ),
        const SizedBox(height: 4),
        const Text('Turn off in', style: TextStyle(fontSize: 12, color: NestraColors.textMuted)),
        const SizedBox(height: 6),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final (minutes, label) in _offAfter)
              ActionChip(
                label: Text(label),
                backgroundColor: NestraColors.card,
                side: const BorderSide(color: NestraColors.border),
                onPressed: () => _set({'timer_off_in': minutes}),
              ),
          ],
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          style: OutlinedButton.styleFrom(
            foregroundColor: NestraColors.textPrimary,
            side: const BorderSide(color: NestraColors.border),
          ),
          onPressed: () async {
            final picked = await showTimePicker(
              context: context,
              initialTime: const TimeOfDay(hour: 7, minute: 0),
              helpText: 'Turn on at',
            );
            if (picked == null) return;
            final hh = picked.hour.toString().padLeft(2, '0');
            final mm = picked.minute.toString().padLeft(2, '0');
            _set({'timer_on_at_time': '$hh:$mm'});
          },
          icon: const Icon(Icons.alarm_add_outlined, size: 18),
          label: const Text('Turn on at a time…'),
        ),
        const SizedBox(height: 6),
        const Text(
          'Timers follow the simulated home clock.',
          style: TextStyle(fontSize: 11, color: NestraColors.textMuted),
        ),
      ];
}

class _Heading extends StatelessWidget {
  const _Heading(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(text, style: const TextStyle(fontSize: 13, color: NestraColors.textSecondary)),
      );
}

class _ActiveTimer extends StatelessWidget {
  const _ActiveTimer({required this.icon, required this.text, required this.onCancel});
  final IconData icon;
  final String text;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.fromLTRB(12, 4, 4, 4),
        decoration: BoxDecoration(
          color: NestraColors.purple.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: NestraColors.purple.withValues(alpha: 0.4)),
        ),
        child: Row(
          children: [
            Icon(icon, size: 18, color: NestraColors.purple),
            const SizedBox(width: 10),
            Expanded(child: Text(text)),
            IconButton(
              tooltip: 'Cancel timer',
              onPressed: onCancel,
              icon: const Icon(Icons.close_rounded, size: 18, color: NestraColors.textSecondary),
            ),
          ],
        ),
      );
}

class _Round extends StatelessWidget {
  const _Round({required this.icon, required this.onTap});
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Material(
        color: NestraColors.card,
        shape: const CircleBorder(side: BorderSide(color: NestraColors.border)),
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: onTap,
          child: Padding(padding: const EdgeInsets.all(12), child: Icon(icon)),
        ),
      );
}
