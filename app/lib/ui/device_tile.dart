import 'package:flutter/material.dart';

import '../models.dart';
import '../state/home_controller.dart';
import '../theme.dart';

/// One device card in the selected room's grid. The control at the bottom
/// depends on the device type.
class DeviceTile extends StatelessWidget {
  const DeviceTile({super.key, required this.device, required this.controller});

  final Device device;
  final HomeController controller;

  @override
  Widget build(BuildContext context) {
    final accent = colorForDevice(device.type);
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: NestraColors.card,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: NestraColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _IconBubble(
                icon: iconForDevice(device.type),
                color: accent,
                active: device.isActive,
                tooltip: device.isPowered ? (device.on ? 'Turn off' : 'Turn on') : null,
                onTap: device.isPowered
                    ? () => controller.setDevice(device.id, {'on': !device.on})
                    : null,
              ),
              const Spacer(),
              _statusLabel(),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            device.name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
          ),
          const Spacer(),
          _control(context),
        ],
      ),
    );
  }

  Widget _statusLabel() {
    final text = switch (device.type) {
      'blinds' => device.position <= 0 ? 'Closed' : '${device.position.round()}% open',
      'lock' => device.locked ? 'Locked' : 'Unlocked',
      'ac' => device.on ? formatTemp(device.setpoint) : 'Off',
      'fan' => device.on ? '${device.speed.round()}%' : 'Off',
      _ => null,
    };
    if (text == null) return _Dot(active: device.isActive);
    return Text(text, style: const TextStyle(fontSize: 11, color: NestraColors.textSecondary));
  }

  Widget _control(BuildContext context) => switch (device.type) {
        'light' => _LevelBar(
            value: device.on ? device.brightness : 0,
            color: NestraColors.peach,
            onChanged: (v) => controller.setDevice(device.id, {'brightness': v, 'on': v > 0}),
          ),
        'fan' => _FanSpeed(device: device, controller: controller),
        'ac' => _Setpoint(device: device, controller: controller),
        'blinds' => Align(
            alignment: Alignment.centerRight,
            child: _PillButton(
              label: device.position > 0 ? 'Close' : 'Open',
              icon: device.position > 0 ? Icons.south_rounded : Icons.north_rounded,
              onTap: () => controller.setDevice(device.id, {'position': device.position > 0 ? 0 : 100}),
            ),
          ),
        'lock' => Align(
            alignment: Alignment.centerRight,
            child: _PillButton(
              label: device.locked ? 'Unlock' : 'Lock',
              icon: device.locked ? Icons.lock_open_rounded : Icons.lock_rounded,
              onTap: () => toggleLock(context, controller, device),
            ),
          ),
        _ => const SizedBox.shrink(),
      };
}

/// Unlocking asks first; locking doesn't.
Future<void> toggleLock(BuildContext context, HomeController controller, Device device) async {
  if (!device.locked) {
    await controller.setDevice(device.id, {'locked': true});
    return;
  }
  final ok = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      backgroundColor: NestraColors.cardRaised,
      title: Text('Unlock ${device.name}?'),
      content: const Text('Anyone at the door will be able to open it.'),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Unlock')),
      ],
    ),
  );
  if (ok == true) await controller.setDevice(device.id, {'locked': false});
}

class _IconBubble extends StatelessWidget {
  const _IconBubble({
    required this.icon,
    required this.color,
    required this.active,
    this.onTap,
    this.tooltip,
  });

  final IconData icon;
  final Color color;
  final bool active;
  final VoidCallback? onTap;
  final String? tooltip;

  @override
  Widget build(BuildContext context) {
    final bubble = Material(
      color: active ? color.withValues(alpha: 0.18) : NestraColors.cardRaised,
      shape: const CircleBorder(),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: Icon(icon, size: 18, color: active ? color : NestraColors.textMuted),
        ),
      ),
    );
    return tooltip == null ? bubble : Tooltip(message: tooltip!, child: bubble);
  }
}

class _Dot extends StatelessWidget {
  const _Dot({required this.active});
  final bool active;

  @override
  Widget build(BuildContext context) => Container(
        width: 7,
        height: 7,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: active ? NestraColors.orange : NestraColors.textMuted,
        ),
      );
}

/// Draggable horizontal level bar (brightness). Sends the value when the drag ends.
class _LevelBar extends StatefulWidget {
  const _LevelBar({required this.value, required this.color, required this.onChanged});

  final double value;
  final Color color;
  final ValueChanged<double> onChanged;

  @override
  State<_LevelBar> createState() => _LevelBarState();
}

class _LevelBarState extends State<_LevelBar> {
  double? _dragging;

  double _valueAt(double dx, double width) => (dx / width * 100).clamp(0, 100).roundToDouble();

  @override
  Widget build(BuildContext context) {
    final value = _dragging ?? widget.value;
    return LayoutBuilder(
      builder: (context, box) {
        final width = box.maxWidth;
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapUp: (d) => widget.onChanged(_valueAt(d.localPosition.dx, width)),
          onHorizontalDragStart: (d) => setState(() => _dragging = _valueAt(d.localPosition.dx, width)),
          onHorizontalDragUpdate: (d) => setState(() => _dragging = _valueAt(d.localPosition.dx, width)),
          onHorizontalDragEnd: (_) {
            final v = _dragging;
            setState(() => _dragging = null);
            if (v != null) widget.onChanged(v);
          },
          child: Container(
            height: 32,
            decoration: BoxDecoration(
              color: NestraColors.track,
              borderRadius: BorderRadius.circular(10),
            ),
            clipBehavior: Clip.antiAlias,
            child: Stack(
              children: [
                AnimatedContainer(
                  duration: Duration(milliseconds: _dragging == null ? 250 : 0),
                  width: width * value / 100,
                  color: widget.color,
                ),
                Positioned.fill(
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Padding(
                      padding: const EdgeInsets.only(left: 10),
                      child: Text(
                        '${value.round()}%',
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: value > 18 ? const Color(0xFF3B2414) : NestraColors.textSecondary,
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

/// Low / Med / High segmented control. Values match the backend's fuzzy term centres.
class _FanSpeed extends StatelessWidget {
  const _FanSpeed({required this.device, required this.controller});

  final Device device;
  final HomeController controller;

  static const _levels = [('Low', 25.0), ('Med', 55.0), ('High', 80.0)];

  @override
  Widget build(BuildContext context) {
    int? selected;
    if (device.on) {
      var best = double.infinity;
      for (var i = 0; i < _levels.length; i++) {
        final d = (_levels[i].$2 - device.speed).abs();
        if (d < best) {
          best = d;
          selected = i;
        }
      }
    }
    return Container(
      height: 32,
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: NestraColors.track, borderRadius: BorderRadius.circular(10)),
      child: Row(
        children: [
          for (var i = 0; i < _levels.length; i++)
            Expanded(
              child: GestureDetector(
                onTap: () => controller.setDevice(device.id, {'on': true, 'speed': _levels[i].$2}),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: selected == i ? NestraColors.textPrimary : Colors.transparent,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    _levels[i].$1,
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      color: selected == i ? NestraColors.background : NestraColors.textSecondary,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _Setpoint extends StatelessWidget {
  const _Setpoint({required this.device, required this.controller});

  final Device device;
  final HomeController controller;

  void _nudge(double delta) {
    final next = (device.setpoint + delta).clamp(16.0, 30.0);
    controller.setDevice(device.id, {'on': true, 'setpoint': next});
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        _RoundButton(icon: Icons.remove_rounded, onTap: () => _nudge(-0.5)),
        Expanded(
          child: Text(
            device.on ? '${device.mode[0].toUpperCase()}${device.mode.substring(1)}' : 'Off',
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 12, color: NestraColors.textSecondary),
          ),
        ),
        _RoundButton(icon: Icons.add_rounded, onTap: () => _nudge(0.5)),
      ],
    );
  }
}

class _RoundButton extends StatelessWidget {
  const _RoundButton({required this.icon, required this.onTap});
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Material(
        color: NestraColors.track,
        shape: const CircleBorder(),
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: onTap,
          child: Padding(padding: const EdgeInsets.all(6), child: Icon(icon, size: 18)),
        ),
      );
}

class _PillButton extends StatelessWidget {
  const _PillButton({required this.label, required this.icon, required this.onTap});
  final String label;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Material(
        color: NestraColors.purple,
        borderRadius: BorderRadius.circular(20),
        child: InkWell(
          borderRadius: BorderRadius.circular(20),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, size: 14, color: Colors.white),
                const SizedBox(width: 4),
                Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Colors.white)),
              ],
            ),
          ),
        ),
      );
}
