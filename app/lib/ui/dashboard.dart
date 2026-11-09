import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import '../config.dart';
import '../state/hands_free.dart';
import '../state/home_controller.dart';
import '../theme.dart';
import 'activity_panel.dart';
import 'command_dialog.dart';
import 'conversation_bar.dart';
import 'device_tile.dart';
import 'manage_dialogs.dart';
import 'room_card.dart';

class Dashboard extends StatefulWidget {
  const Dashboard({super.key, required this.controller, this.user});

  final HomeController controller;
  final User? user;

  @override
  State<Dashboard> createState() => _DashboardState();
}

class _DashboardState extends State<Dashboard> {
  HomeController get c => widget.controller;
  late final HandsFree handsFree = HandsFree(c)..addListener(_showHandsFreeError);

  @override
  void initState() {
    super.initState();
    c.addListener(_showErrors);
  }

  @override
  void dispose() {
    c.removeListener(_showErrors);
    handsFree.dispose();
    super.dispose();
  }

  void _showHandsFreeError() {
    final message = handsFree.error;
    if (message != null && mounted) {
      handsFree.error = null;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
    }
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
        child: Stack(
          children: [
            Positioned.fill(child: _content()),
            Positioned(
              left: 16,
              right: 16,
              bottom: 20,
              child: Center(child: ConversationBar(handsFree: handsFree, controller: c)),
            ),
          ],
        ),
      ),
    );
  }

  Widget _content() {
    return ListenableBuilder(
          listenable: c,
          builder: (context, _) {
            if (!c.loaded) return _Connecting(online: c.online, user: widget.user);
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
        );
  }

  Widget _main(BuildContext context) {
    final room = c.selectedRoom!;
    final roomDevices = c.devicesIn(room.id);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _Header(controller: c, handsFree: handsFree, user: widget.user),
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
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Expanded(child: _SectionTitle('Rooms')),
            _AllRoomsSwitch(controller: c),
          ],
        ),
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
  const _Header({required this.controller, required this.handsFree, this.user});

  final HomeController controller;
  final HandsFree handsFree;
  final User? user;

  String get _firstName {
    final display = user?.displayName?.trim() ?? '';
    if (display.isNotEmpty) return display.split(' ').first;
    return residentName;
  }

  String _greeting() {
    final hour = (controller.now ?? DateTime.now()).hour;
    final part = hour < 5
        ? 'Good night'
        : hour < 12
            ? 'Good morning'
            : hour < 18
                ? 'Good afternoon'
                : 'Good evening';
    final name = _firstName;
    return name.isEmpty ? '$part.' : '$part, $name.';
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
              if (narrow) ...[
                const SizedBox(height: 10),
                HomeClock(controller: controller, compact: true),
              ],
            ],
          ),
        ),
        if (!narrow) ...[
          HomeClock(controller: controller),
          const SizedBox(width: 22),
        ],
        _HandsFreeButton(handsFree: handsFree),
        const SizedBox(width: 10),
        Tooltip(
          message: 'Give a command',
          child: Material(
            color: NestraColors.purple,
            shape: const CircleBorder(),
            child: InkWell(
              customBorder: const CircleBorder(),
              onTap: () => handsFree.pauseWhile(() => showCommandDialog(context, controller)),
              child: const Padding(
                padding: EdgeInsets.all(14),
                child: Icon(Icons.mic_rounded, color: Colors.white),
              ),
            ),
          ),
        ),
        if (user != null) ...[
          const SizedBox(width: 10),
          _AccountButton(user: user!),
        ],
      ],
    );
  }
}

/// Avatar with the signed-in account and a sign-out option.
class _AccountButton extends StatelessWidget {
  const _AccountButton({required this.user});
  final User user;

  @override
  Widget build(BuildContext context) {
    final label = (user.displayName?.trim().isNotEmpty ?? false) ? user.displayName! : (user.email ?? 'Account');
    return PopupMenuButton<String>(
      tooltip: 'Account',
      color: NestraColors.cardRaised,
      position: PopupMenuPosition.under,
      onSelected: (value) {
        if (value == 'sign_out') FirebaseAuth.instance.signOut();
      },
      itemBuilder: (_) => [
        PopupMenuItem<String>(
          enabled: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: const TextStyle(color: NestraColors.textPrimary, fontWeight: FontWeight.w600)),
              if (user.email != null && user.email != label)
                Text(user.email!, style: const TextStyle(color: NestraColors.textSecondary, fontSize: 12)),
            ],
          ),
        ),
        const PopupMenuDivider(),
        const PopupMenuItem<String>(
          value: 'sign_out',
          child: Row(
            children: [
              Icon(Icons.logout_rounded, size: 18),
              SizedBox(width: 10),
              Text('Sign out'),
            ],
          ),
        ),
      ],
      child: CircleAvatar(
        radius: 24,
        backgroundColor: NestraColors.cardRaised,
        foregroundImage: user.photoURL == null ? null : NetworkImage(user.photoURL!),
        child: Text(
          label.characters.first.toUpperCase(),
          style: const TextStyle(fontWeight: FontWeight.w700, color: NestraColors.textPrimary),
        ),
      ),
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
  const _Connecting({required this.online, this.user});
  final bool online;
  final User? user;

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
            if (user != null) ...[
              const SizedBox(height: 16),
              TextButton(onPressed: () => FirebaseAuth.instance.signOut(), child: const Text('Sign out')),
            ],
          ],
        ),
      );
}


/// Date and time on the home's clock, ticking every second.
class HomeClock extends StatefulWidget {
  const HomeClock({super.key, required this.controller, this.compact = false});

  final HomeController controller;
  final bool compact;

  @override
  State<HomeClock> createState() => _HomeClockState();
}

class _HomeClockState extends State<HomeClock> {
  late final Timer _timer;

  static const _days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  static const _months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ];

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => setState(() {}));
  }

  @override
  void dispose() {
    _timer.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final now = widget.controller.now ?? DateTime.now();
    final time = '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}';
    final date = '${_days[now.weekday - 1]}, ${now.day} ${_months[now.month - 1]} ${now.year}';
    final scale = widget.controller.timeScale;
    final speed = scale == 1
        ? null
        : Tooltip(
            message: 'The simulated home runs ${_scaleText(scale)} faster than real time '
                '(NESTRA_TIME_SCALE). Timers and history use this clock.',
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
              decoration: BoxDecoration(
                color: NestraColors.purple.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                '${_scaleText(scale)} speed',
                style: const TextStyle(fontSize: 10.5, color: NestraColors.purple, fontWeight: FontWeight.w600),
              ),
            ),
          );
    if (widget.compact) {
      return Row(
        children: [
          Text(time, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              '${_days[now.weekday - 1].substring(0, 3)}, ${now.day} ${_months[now.month - 1].substring(0, 3)}',
              style: const TextStyle(fontSize: 13, color: NestraColors.textSecondary),
            ),
          ),
          if (speed != null) ...[const SizedBox(width: 8), speed],
        ],
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Text(
          time,
          style: const TextStyle(fontSize: 34, fontWeight: FontWeight.w300, height: 1.15, letterSpacing: 1),
        ),
        const SizedBox(height: 6),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (speed != null) ...[speed, const SizedBox(width: 8)],
            Text(date, style: const TextStyle(fontSize: 13, color: NestraColors.textSecondary)),
          ],
        ),
      ],
    );
  }

  static String _scaleText(double s) => s == s.roundToDouble() ? '${s.round()}×' : '${s.toStringAsFixed(1)}×';
}

/// Whole-home power: on if anything is on; switching it off turns off every
/// light, fan, aircond and appliance in every room.
class _AllRoomsSwitch extends StatelessWidget {
  const _AllRoomsSwitch({required this.controller});
  final HomeController controller;

  @override
  Widget build(BuildContext context) {
    final devices = controller.poweredDevices;
    if (devices.isEmpty) return const SizedBox.shrink();
    final onCount = devices.where((d) => d.on).length;
    final anyOn = onCount > 0;
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            anyOn ? 'All rooms · $onCount on' : 'All rooms · off',
            style: const TextStyle(fontSize: 13, color: NestraColors.textSecondary),
          ),
          const SizedBox(width: 8),
          Tooltip(
            message: anyOn ? 'Turn off everything in every room' : 'Turn on everything in every room',
            child: Switch(
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              value: anyOn,
              onChanged: controller.setAllPower,
            ),
          ),
        ],
      ),
    );
  }
}


/// Turns "Hi Nestra" hands-free listening on and off. Glows with your voice while listening.
class _HandsFreeButton extends StatelessWidget {
  const _HandsFreeButton({required this.handsFree});
  final HandsFree handsFree;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: handsFree,
        builder: (context, _) {
          final status = handsFree.status;
          final on = handsFree.enabled;
          final tooltip = switch (status) {
            HandsFreeStatus.off => 'Hands-free: say “Hi Nestra”',
            HandsFreeStatus.starting => 'Starting the microphone…',
            HandsFreeStatus.listening => 'Listening for “Hi Nestra”. Tap to stop',
            HandsFreeStatus.conversing => 'In a conversation. Tap to turn hands-free off',
            HandsFreeStatus.thinking => 'Working on it…',
          };
          return Tooltip(
            message: tooltip,
            child: ValueListenableBuilder<double>(
              valueListenable: handsFree.level,
              builder: (context, level, child) => AnimatedContainer(
                duration: const Duration(milliseconds: 120),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  boxShadow: [
                    if (on)
                      BoxShadow(
                        color: NestraColors.green.withValues(alpha: 0.35),
                        blurRadius: 6 + 18 * level,
                        spreadRadius: 4 * level,
                      ),
                  ],
                ),
                child: child,
              ),
              child: Material(
                color: on ? NestraColors.green.withValues(alpha: 0.18) : NestraColors.cardRaised,
                shape: CircleBorder(side: BorderSide(color: on ? NestraColors.green : NestraColors.border)),
                child: InkWell(
                  customBorder: const CircleBorder(),
                  onTap: status == HandsFreeStatus.starting ? null : handsFree.toggle,
                  child: Padding(
                    padding: const EdgeInsets.all(13),
                    child: status == HandsFreeStatus.thinking || status == HandsFreeStatus.starting
                        ? const SizedBox.square(
                            dimension: 22,
                            child: CircularProgressIndicator(strokeWidth: 2, color: NestraColors.green),
                          )
                        : Icon(
                            on ? Icons.hearing_rounded : Icons.hearing_disabled_rounded,
                            color: on ? NestraColors.green : NestraColors.textSecondary,
                          ),
                  ),
                ),
              ),
            ),
          );
        },
      );
}
