import 'package:flutter/material.dart';

import '../models.dart';
import '../state/home_controller.dart';
import '../theme.dart';

/// Add a new device (device == null) or edit/remove an existing one.
Future<void> showDeviceForm(
  BuildContext context,
  HomeController controller, {
  Device? device,
  String? roomId,
}) =>
    showDialog(
      context: context,
      builder: (_) => _DeviceForm(controller: controller, device: device, initialRoomId: roomId),
    );

/// Add a new room (room == null) or rename/remove an existing one.
Future<void> showRoomForm(BuildContext context, HomeController controller, {Room? room}) => showDialog(
      context: context,
      builder: (_) => _RoomForm(controller: controller, room: room),
    );

class _DeviceForm extends StatefulWidget {
  const _DeviceForm({required this.controller, this.device, this.initialRoomId});

  final HomeController controller;
  final Device? device;
  final String? initialRoomId;

  @override
  State<_DeviceForm> createState() => _DeviceFormState();
}

class _DeviceFormState extends State<_DeviceForm> {
  late final TextEditingController _name = TextEditingController(text: widget.device?.name ?? '');
  late String _type = widget.device?.type ?? 'light';
  late String _kind = widget.device?.kind ?? 'other';
  late String _roomId = widget.device?.roomId ??
      widget.initialRoomId ??
      (widget.controller.rooms.isEmpty ? '' : widget.controller.rooms.first.id);
  Catalog _catalog = Catalog.fallback;
  String? _error;
  bool _busy = false;

  bool get _editing => widget.device != null;

  @override
  void initState() {
    super.initState();
    widget.controller.catalog().then((c) {
      if (mounted) setState(() => _catalog = c);
    });
  }

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final name = _name.text.trim();
    if (name.isEmpty) {
      setState(() => _error = 'Give the device a name, e.g. "Kitchen Kettle".');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    final c = widget.controller;
    final String? error;
    if (_editing) {
      final d = widget.device!;
      error = await c.editDevice(d.id, {
        if (name != d.name) 'name': name,
        if (_roomId != d.roomId) 'room_id': _roomId,
        if (d.type == 'appliance' && _kind != d.kind) 'kind': _kind,
      });
    } else {
      error = await c.addDevice(
        type: _type,
        name: name,
        roomId: _roomId,
        kind: _type == 'appliance' ? _kind : null,
      );
    }
    if (!mounted) return;
    if (error == null) {
      Navigator.pop(context);
    } else {
      setState(() {
        _busy = false;
        _error = error;
      });
    }
  }

  Future<void> _remove() async {
    final d = widget.device!;
    final ok = await _confirm(
      context,
      title: 'Remove ${d.name}?',
      message: 'It will disappear from the dashboard and voice commands.',
      action: 'Remove',
    );
    if (!ok || !mounted) return;
    final error = await widget.controller.removeDevice(d.id);
    if (!mounted) return;
    if (error == null) {
      Navigator.pop(context);
    } else {
      setState(() => _error = error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final rooms = widget.controller.rooms;
    final kinds = _catalog.applianceKinds.any((k) => k.value == _kind)
        ? _catalog.applianceKinds
        : [..._catalog.applianceKinds, CatalogItem(_kind, _kind)];
    final type = _editing ? widget.device!.type : _type;

    return _FormDialog(
      title: _editing ? 'Edit device' : 'Add a device',
      error: _error,
      busy: _busy,
      onSave: _save,
      saveLabel: _editing ? 'Save' : 'Add device',
      onDelete: _editing ? _remove : null,
      children: [
        if (!_editing) ...[
          const _Label('Type'),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final t in _catalog.deviceTypes)
                ChoiceChip(
                  avatar: Icon(iconForDevice(t.value), size: 16, color: colorForDevice(t.value)),
                  label: Text(t.label),
                  selected: _type == t.value,
                  showCheckmark: false,
                  selectedColor: NestraColors.purple.withValues(alpha: 0.25),
                  backgroundColor: NestraColors.card,
                  side: BorderSide(color: _type == t.value ? NestraColors.purple : NestraColors.border),
                  onSelected: (_) => setState(() => _type = t.value),
                ),
            ],
          ),
          const SizedBox(height: 16),
        ],
        if (type == 'appliance') ...[
          const _Label('What is it?'),
          _Dropdown<String>(
            value: _kind,
            items: [
              for (final k in kinds)
                DropdownMenuItem(
                  value: k.value,
                  child: Row(
                    children: [
                      Icon(iconForAppliance(k.value), size: 18, color: NestraColors.textSecondary),
                      const SizedBox(width: 10),
                      Text(k.label),
                    ],
                  ),
                ),
            ],
            onChanged: (v) => setState(() => _kind = v ?? 'other'),
          ),
          const SizedBox(height: 16),
        ],
        const _Label('Name'),
        _TextInput(
          controller: _name,
          hint: type == 'appliance' ? 'e.g. Living Room TV' : 'e.g. Bedside Lamp',
          onSubmitted: _save,
        ),
        const SizedBox(height: 6),
        const Text(
          'This is the name you\'ll use in voice commands.',
          style: TextStyle(fontSize: 11.5, color: NestraColors.textMuted),
        ),
        const SizedBox(height: 16),
        const _Label('Room'),
        _Dropdown<String>(
          value: rooms.any((r) => r.id == _roomId) ? _roomId : null,
          items: [for (final r in rooms) DropdownMenuItem(value: r.id, child: Text(r.name))],
          onChanged: (v) => setState(() => _roomId = v ?? _roomId),
        ),
      ],
    );
  }
}

class _RoomForm extends StatefulWidget {
  const _RoomForm({required this.controller, this.room});

  final HomeController controller;
  final Room? room;

  @override
  State<_RoomForm> createState() => _RoomFormState();
}

class _RoomFormState extends State<_RoomForm> {
  late final TextEditingController _name = TextEditingController(text: widget.room?.name ?? '');
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final name = _name.text.trim();
    if (name.isEmpty) {
      setState(() => _error = 'Give the room a name.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    final room = widget.room;
    final error = room == null
        ? await widget.controller.addRoom(name)
        : name == room.name
            ? null
            : await widget.controller.renameRoom(room.id, name);
    if (!mounted) return;
    if (error == null) {
      Navigator.pop(context);
    } else {
      setState(() {
        _busy = false;
        _error = error;
      });
    }
  }

  Future<void> _remove() async {
    final room = widget.room!;
    final count = widget.controller.devicesIn(room.id).length;
    final ok = await _confirm(
      context,
      title: 'Remove ${room.name}?',
      message: count == 0
          ? 'The room is empty.'
          : 'Its $count device${count == 1 ? '' : 's'} will be removed too.',
      action: 'Remove room',
    );
    if (!ok || !mounted) return;
    final error = await widget.controller.removeRoom(room.id);
    if (!mounted) return;
    if (error == null) {
      Navigator.pop(context);
    } else {
      setState(() => _error = error);
    }
  }

  @override
  Widget build(BuildContext context) => _FormDialog(
        title: widget.room == null ? 'Add a room' : 'Edit room',
        error: _error,
        busy: _busy,
        onSave: _save,
        saveLabel: widget.room == null ? 'Add room' : 'Save',
        onDelete: widget.room == null ? null : _remove,
        children: [
          const _Label('Name'),
          _TextInput(controller: _name, hint: 'e.g. Study', onSubmitted: _save),
        ],
      );
}

// ---------------------------------------------------------------- pieces

Future<bool> _confirm(
  BuildContext context, {
  required String title,
  required String message,
  required String action,
}) async =>
    await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: NestraColors.cardRaised,
        title: Text(title),
        content: Text(message),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: NestraColors.red),
            onPressed: () => Navigator.pop(context, true),
            child: Text(action),
          ),
        ],
      ),
    ) ==
    true;

class _FormDialog extends StatelessWidget {
  const _FormDialog({
    required this.title,
    required this.children,
    required this.onSave,
    required this.saveLabel,
    required this.busy,
    this.error,
    this.onDelete,
  });

  final String title;
  final List<Widget> children;
  final VoidCallback onSave;
  final String saveLabel;
  final bool busy;
  final String? error;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) => Dialog(
        backgroundColor: NestraColors.panel,
        insetPadding: const EdgeInsets.all(16),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(24),
          side: const BorderSide(color: NestraColors.border),
        ),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(22),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
                const SizedBox(height: 18),
                ...children,
                if (error != null) ...[
                  const SizedBox(height: 14),
                  Text(error!, style: const TextStyle(color: NestraColors.red, fontSize: 12.5)),
                ],
                const SizedBox(height: 22),
                Row(
                  children: [
                    if (onDelete != null)
                      TextButton.icon(
                        onPressed: busy ? null : onDelete,
                        style: TextButton.styleFrom(foregroundColor: NestraColors.red),
                        icon: const Icon(Icons.delete_outline_rounded, size: 18),
                        label: const Text('Remove'),
                      ),
                    const Spacer(),
                    TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
                    const SizedBox(width: 8),
                    FilledButton(
                      onPressed: busy ? null : onSave,
                      child: busy
                          ? const SizedBox.square(dimension: 16, child: CircularProgressIndicator(strokeWidth: 2))
                          : Text(saveLabel),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      );
}

class _Label extends StatelessWidget {
  const _Label(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(text, style: const TextStyle(fontSize: 12.5, color: NestraColors.textSecondary)),
      );
}

InputDecoration _inputDecoration({String? hint}) => InputDecoration(
      hintText: hint,
      hintStyle: const TextStyle(color: NestraColors.textMuted),
      filled: true,
      fillColor: NestraColors.card,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: NestraColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: NestraColors.purple),
      ),
    );

class _TextInput extends StatelessWidget {
  const _TextInput({required this.controller, required this.hint, required this.onSubmitted});
  final TextEditingController controller;
  final String hint;
  final VoidCallback onSubmitted;

  @override
  Widget build(BuildContext context) => TextField(
        controller: controller,
        autofocus: true,
        maxLength: 40,
        textCapitalization: TextCapitalization.words,
        onSubmitted: (_) => onSubmitted(),
        decoration: _inputDecoration(hint: hint).copyWith(counterText: ''),
      );
}

class _Dropdown<T> extends StatelessWidget {
  const _Dropdown({required this.value, required this.items, required this.onChanged});
  final T? value;
  final List<DropdownMenuItem<T>> items;
  final ValueChanged<T?> onChanged;

  @override
  Widget build(BuildContext context) => DropdownButtonFormField<T>(
        initialValue: value,
        items: items,
        onChanged: onChanged,
        dropdownColor: NestraColors.cardRaised,
        borderRadius: BorderRadius.circular(12),
        decoration: _inputDecoration(),
      );
}
