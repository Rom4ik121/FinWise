import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

class FinanseLocalNotificationsService extends FletService {
  FinanseLocalNotificationsService({required super.control});

  final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
  bool _ready = false;

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invokeMethod);
    _ensureInit();
  }

  Future<void> _ensureInit() async {
    if (_ready) {
      return;
    }
    tzdata.initializeTimeZones();
    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    const darwin = DarwinInitializationSettings(
      requestAlertPermission: true,
      requestBadgePermission: true,
      requestSoundPermission: true,
    );
    await _plugin.initialize(
      const InitializationSettings(
        android: android,
        iOS: darwin,
        macOS: darwin,
      ),
    );
    _ready = true;
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    debugPrint("FinanseLocalNotifications.$name($args)");
    await _ensureInit();
    switch (name) {
      case "request_permissions":
        return _requestPermissions();
      case "are_notifications_enabled":
        return _areEnabled();
      case "show_notification":
        return _show(args);
      case "schedule_notification":
        return _schedule(args);
      case "cancel_notification":
        await _plugin.cancel((args?["id"] as num?)?.toInt() ?? 0);
        return true;
      default:
        throw Exception("Unknown FinanseLocalNotifications method: $name");
    }
  }

  Future<bool> _requestPermissions() async {
    final android = _plugin.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    if (android != null) {
      await android.requestNotificationsPermission();
      try {
        await android.requestExactAlarmsPermission();
      } catch (_) {}
    }
    final ios = _plugin.resolvePlatformSpecificImplementation<
        IOSFlutterLocalNotificationsPlugin>();
    if (ios != null) {
      await ios.requestPermissions(alert: true, badge: true, sound: true);
    }
    final macos = _plugin.resolvePlatformSpecificImplementation<
        MacOSFlutterLocalNotificationsPlugin>();
    if (macos != null) {
      await macos.requestPermissions(alert: true, badge: true, sound: true);
    }
    return true;
  }

  Future<bool> _areEnabled() async {
    final android = _plugin.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    if (android != null) {
      return await android.areNotificationsEnabled() ?? true;
    }
    return true;
  }

  NotificationDetails _details(dynamic args) {
    final channelId = (args?["channel_id"] as String?) ?? "finwise_reminders";
    final channelName =
        (args?["channel_name"] as String?) ?? "FinWise reminders";
    return NotificationDetails(
      android: AndroidNotificationDetails(
        channelId,
        channelName,
        channelDescription: "Debt, subscription, and goal alerts",
        importance: Importance.high,
        priority: Priority.high,
        playSound: true,
        enableVibration: true,
      ),
      iOS: const DarwinNotificationDetails(
        presentAlert: true,
        presentBadge: true,
        presentSound: true,
      ),
    );
  }

  Future<bool> _show(dynamic args) async {
    final id = (args?["id"] as num?)?.toInt() ?? 1;
    await _plugin.show(
      id,
      (args?["title"] as String?) ?? "FinWise",
      (args?["body"] as String?) ?? "",
      _details(args),
    );
    return true;
  }

  tz.TZDateTime _toTz(DateTime when) {
    final utc = when.toUtc();
    return tz.TZDateTime.utc(
      utc.year,
      utc.month,
      utc.day,
      utc.hour,
      utc.minute,
      utc.second,
    );
  }

  Future<bool> _schedule(dynamic args) async {
    final whenIso = args?["when_iso"] as String?;
    if (whenIso == null || whenIso.isEmpty) {
      return _show(args);
    }
    DateTime when;
    try {
      when = DateTime.parse(whenIso);
    } catch (_) {
      return _show(args);
    }
    if (when.isBefore(DateTime.now().toUtc().subtract(const Duration(seconds: 5)))) {
      return _show(args);
    }
    final id = (args?["id"] as num?)?.toInt() ?? 1;
    await _plugin.zonedSchedule(
      id,
      (args?["title"] as String?) ?? "FinWise",
      (args?["body"] as String?) ?? "",
      _toTz(when),
      _details(args),
      androidScheduleMode: AndroidScheduleMode.exactAllowWhileIdle,
      uiLocalNotificationDateInterpretation:
          UILocalNotificationDateInterpretation.absoluteTime,
    );
    return true;
  }

  @override
  void dispose() {
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
