import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
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
    try {
      tzdata.initializeTimeZones();
      tz.setLocalLocation(tz.UTC);
      const android = AndroidInitializationSettings('@mipmap/ic_launcher');
      // iOS swallows the system dialog if we ask during splash /
      // didFinishLaunching. Request later from Python after the first frame.
      const darwin = DarwinInitializationSettings(
        requestAlertPermission: false,
        requestBadgePermission: false,
        requestSoundPermission: false,
        defaultPresentAlert: true,
        defaultPresentSound: true,
        defaultPresentBadge: true,
        defaultPresentBanner: true,
        defaultPresentList: true,
      );
      await _plugin.initialize(
        const InitializationSettings(
          android: android,
          iOS: darwin,
          macOS: darwin,
        ),
      );
      final androidPlugin = _plugin.resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin>();
      if (androidPlugin != null) {
        await androidPlugin.createNotificationChannel(
          const AndroidNotificationChannel(
            'finwise_reminders',
            'FinWise reminders',
            description: 'Debt, subscription, and goal alerts',
            importance: Importance.high,
            playSound: true,
            enableVibration: true,
          ),
        );
      }
      _ready = true;
    } catch (err, stack) {
      debugPrint("FinanseLocalNotifications init failed: $err\n$stack");
      rethrow;
    }
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    debugPrint("FinanseLocalNotifications.$name($args)");
    if (name == "haptic") {
      return _haptic(args);
    }
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
        await _plugin.cancel((_asMap(args)["id"] as num?)?.toInt() ?? 0);
        return true;
      case "cancel_all":
        await _plugin.cancelAll();
        return true;
      default:
        throw Exception("Unknown FinanseLocalNotifications method: $name");
    }
  }

  Future<bool> _haptic(dynamic args) async {
    final kind = (args is Map ? args["kind"] as String? : null) ?? "light";
    switch (kind) {
      case "medium":
        await HapticFeedback.mediumImpact();
        break;
      case "heavy":
        await HapticFeedback.heavyImpact();
        break;
      case "selection":
        await HapticFeedback.selectionClick();
        break;
      case "success":
        await HapticFeedback.mediumImpact();
        break;
      default:
        await HapticFeedback.lightImpact();
    }
    return true;
  }

  Future<bool> _requestPermissions() async {
    var granted = true;
    var asked = false;
    final android = _plugin.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    if (android != null) {
      asked = true;
      final ok = await android.requestNotificationsPermission();
      if (ok == false) {
        granted = false;
      }
      try {
        await android.requestExactAlarmsPermission();
      } catch (_) {}
    }
    final ios = _plugin.resolvePlatformSpecificImplementation<
        IOSFlutterLocalNotificationsPlugin>();
    if (ios != null) {
      asked = true;
      final ok = await ios.requestPermissions(
        alert: true,
        badge: true,
        sound: true,
      );
      if (ok == false) {
        granted = false;
      }
    }
    final macos = _plugin.resolvePlatformSpecificImplementation<
        MacOSFlutterLocalNotificationsPlugin>();
    if (macos != null) {
      asked = true;
      final ok = await macos.requestPermissions(
        alert: true,
        badge: true,
        sound: true,
      );
      if (ok == false) {
        granted = false;
      }
    }
    if (!asked) {
      debugPrint(
        "FinanseLocalNotifications: no native plugin "
        "(IPA/APK missing flutter_local_notifications?)",
      );
      return false;
    }
    return granted;
  }

  Future<bool> _areEnabled() async {
    final android = _plugin.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    if (android != null) {
      return await android.areNotificationsEnabled() ?? true;
    }
    final ios = _plugin.resolvePlatformSpecificImplementation<
        IOSFlutterLocalNotificationsPlugin>();
    if (ios != null) {
      final ok = await ios.requestPermissions(
        alert: true,
        badge: true,
        sound: true,
      );
      return ok ?? false;
    }
    return true;
  }

  NotificationDetails _details(dynamic args, {bool androidIcon = true}) {
    final map = _asMap(args);
    final channelId = (map["channel_id"] as String?) ?? "finwise_reminders";
    final channelName =
        (map["channel_name"] as String?) ?? "FinWise reminders";
    const darwin = DarwinNotificationDetails(
      presentAlert: true,
      presentBadge: true,
      presentSound: true,
      presentBanner: true,
      presentList: true,
      interruptionLevel: InterruptionLevel.active,
    );
    return NotificationDetails(
      android: AndroidNotificationDetails(
        channelId,
        channelName,
        channelDescription: "Debt, subscription, and goal alerts",
        importance: Importance.max,
        priority: Priority.max,
        playSound: true,
        enableVibration: true,
        icon: androidIcon ? "@drawable/ic_stat_finwise" : null,
        ticker: "FinWise",
        category: AndroidNotificationCategory.reminder,
        visibility: NotificationVisibility.public,
      ),
      iOS: darwin,
      macOS: darwin,
    );
  }

  Map<String, dynamic> _asMap(dynamic args) {
    if (args is Map) {
      return args.map((key, value) => MapEntry(key.toString(), value));
    }
    return {};
  }

  Future<bool> _show(dynamic args) async {
    final map = _asMap(args);
    final id = (map["id"] as num?)?.toInt() ?? 1;
    final title = (map["title"] as String?) ?? "FinWise";
    final body = (map["body"] as String?) ?? "";
    try {
      await _plugin.show(id, title, body, _details(map));
      return true;
    } catch (err) {
      debugPrint("show with notification icon failed: $err");
    }
    try {
      await _plugin.show(id, title, body, _details(map, androidIcon: false));
      return true;
    } catch (err) {
      debugPrint("show fallback failed: $err");
      return false;
    }
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
    final map = _asMap(args);
    final whenIso = map["when_iso"] as String?;
    if (whenIso == null || whenIso.isEmpty) {
      return _show(map);
    }
    DateTime when;
    try {
      when = DateTime.parse(whenIso);
    } catch (_) {
      return _show(map);
    }
    if (when.isBefore(DateTime.now().toUtc().subtract(const Duration(seconds: 5)))) {
      return _show(map);
    }
    final id = (map["id"] as num?)?.toInt() ?? 1;
    final title = (map["title"] as String?) ?? "FinWise";
    final body = (map["body"] as String?) ?? "";
    final details = _details(map);
    final at = _toTz(when);
    try {
      await _plugin.zonedSchedule(
        id,
        title,
        body,
        at,
        details,
        androidScheduleMode: AndroidScheduleMode.exactAllowWhileIdle,
        uiLocalNotificationDateInterpretation:
            UILocalNotificationDateInterpretation.absoluteTime,
      );
      return true;
    } catch (err) {
      debugPrint("exact schedule failed: $err");
    }
    try {
      await _plugin.zonedSchedule(
        id,
        title,
        body,
        at,
        details,
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
        uiLocalNotificationDateInterpretation:
            UILocalNotificationDateInterpretation.absoluteTime,
      );
      return true;
    } catch (err) {
      debugPrint("inexact schedule failed: $err");
      return _show(args);
    }
  }

  @override
  void dispose() {
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
