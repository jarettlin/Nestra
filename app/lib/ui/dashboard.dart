import 'package:flutter/material.dart';

import '../config.dart';
import '../state/home_controller.dart';
import '../theme.dart';
import 'activity_panel.dart';
import 'command_dialog.dart';
import 'device_tile.dart';
import 'manage_dialogs.dart';
import 'room_card.dart';

class Dashboard extends StatefulWidget {
  const Dashboard({super.key, required this.controller});

  final HomeController controller;

  @override
  State<Dashboard> createState() => _DashboardState();
}

class _DashboardState extends State<Dashboard> {
  HomeController get c => widget.controller;

  @override
  void initState() {
    super.initState();
    c.addListener(_showErrors);
  }

  @override
  void dispose() {
    c.removeListener(_showErrors);
    super.dispose();
  }

  void _showErrors() {
    final message = c.error == null ? null : c.takeError();
    if (message != null && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: ListenableBuilder(
          listenable: c,
          builder: (context, _) {
            if (!c.loaded) return _Connecting(online: c.online);
            return LayoutBuilder(
              builder: (context, box) {
                final wide = box.maxWidth >= 1000;
                final padding = box.maxWidth < 600 ? 16.0 : 28.0;
                if (wide) {
                  return Padding(
                    padding: EdgeInsets.all(padding),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Expanded(child: SingleChildScrollView(child: _main(context))),
                        const SizedBox(width: 24),
                        SizedBox(
                          width: 300,
                          child: ActivityPanel(entries: c.activity, online: c.online),
                        ),
                      ],
                    ),
                  );
                }
                return SingleChildScrollView(
                  padding: EdgeInsets.all(padding),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _main(context),
                      const SizedBox(height: 24),
                      ActivityPanel(entries: c.activity, online: c.online, scrollable: false),
                    ],
                  ),
                );
              },
            );
          },
        ),
      ),
    );
  }

  Widget _main(BuildContext context) {
    final room = c.selectedRoom!;
    final roomDevices = c.devicesIn(room.id);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _Header(controller: c),
        const SizedBox(height: 28),
        _SectionTitle(room.name),
        GridView(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
            maxCrossAxisExtent: 210,
            mainAxisExtent: 142,
            crossAxisSpacing: 14,
            mainAxisSpacing: 14,
          ),
          children: [
            for (final d in roomDevices) DeviceTile(device: d, controller: c),
            AddTile(label: 'Add device', onTap: () => showDeviceForm(context, c, roomId: room.id)),
          ],
        ),
        const SizedBox(height: 28),
        const _SectionTitle('Rooms'),
        GridView(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
            maxCrossAxisExtent: 300,
            mainAxisExtent: 158,
            crossAxisSpacing: 14,
            mainAxisSpacing: 14,
          ),
          children: [
            for (final r in c.rooms)
              RoomCard(room: r, devices: c.devicesIn(r.id), selected: r.id == room.id, controller: c),
            AddTile(label: 'Add room', onTap: () => showRoomForm(context, c)),
          ],
        ),
      ],
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.controller});

  final HomeController controller;

  String _greeting() {
    final hour = (controller.time ?? DateTime.now()).hour;
    final part = hour < 5
        ? 'Good night'
        : hour < 12
            ? 'Good morning'
            : hour < 18
                ? 'Good afternoon'
                : 'Good evening';
    return residentName.isEmpty ? '$part.' : '$part, $residentName.';
  }

  @override
  Widget build(BuildContext context) {
    final inside = controller.selectedRoom!.environment.temperature;
    final narrow = MediaQuery.sizeOf(context).width < 600;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                _greeting(),
                style: TextStyle(fontSize: narrow ? 26 : 34, fontWeight: FontWeight.w500, height: 1.15),
              ),
              const SizedBox(height: 6),
              Text.rich(
                TextSpan(
                  style: const TextStyle(fontSize: 13, color: NestraColors.textSecondary),
                  children: [
                    const TextSpan(text: 'Outside '),
                    TextSpan(
                      text: formatTemp(controller.outsideTemperature),
                      style: const TextStyle(color: NestraColors.peach, fontWeight: FontWeight.w600),
                    ),
                    const TextSpan(text: '    Inside '),
                    TextSpan(
                      text: formatTemp(inside),
                      style: const TextStyle(color: NestraColors.blue, fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        Tooltip(
          message: 'Give a command',
          child: Material(
            color: NestraColors.purple,
            shape: const CircleBorder(),
            child: InkWell(
              customBorder: const CircleBorder(),
              onTap: () => showCommandDialog(context, controller),
              child: const Padding(
                padding: EdgeInsets.all(14),
                child: Icon(Icons.mic_rounded, color: Colors.white),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Text(
          text,
          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: NestraColors.textSecondary),
        ),
      );
}

class _Connecting extends StatelessWidget {
  const _Connecting({required this.online});
  final bool online;

  @override
  Widget build(BuildContext context) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(color: NestraColors.purple),
            const SizedBox(height: 20),
            const Text('Connecting to Nestra…', style: TextStyle(fontSize: 16)),
            const SizedBox(height: 6),
            Text(
              'Make sure the backend is running at $apiBase',
              style: const TextStyle(color: NestraColors.textSecondary, fontSize: 13),
            ),
          ],
        ),
      );
}
