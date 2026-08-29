import 'dart:async';

import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:speech_to_text/speech_to_text.dart';

class FinanseSpeechService extends FletService with WidgetsBindingObserver {
  FinanseSpeechService({required super.control});

  final SpeechToText _speech = SpeechToText();
  bool _pendingVoice = false;
  Timer? _holdTimer;
  bool _holdFired = false;

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invokeMethod);
    WidgetsBinding.instance.addObserver(this);
    HardwareKeyboard.instance.addHandler(_onKey);
    _armFromRoute(WidgetsBinding.instance.platformDispatcher.defaultRouteName);
  }

  bool _isVoiceRoute(String route) {
    final text = route.toLowerCase();
    return text.contains("voice") || text.contains("finwise://voice");
  }

  void _armFromRoute(String route) {
    if (_isVoiceRoute(route)) {
      _emitVoiceRequest();
    }
  }

  void _emitVoiceRequest() {
    _pendingVoice = true;
    try {
      control.triggerEvent("voice_request", {});
    } catch (error) {
      debugPrint("FinanseSpeech triggerEvent failed: $error");
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _armFromRoute(WidgetsBinding.instance.platformDispatcher.defaultRouteName);
    }
  }

  bool _onKey(KeyEvent event) {
    // The lock/power button belongs to the OS. Volume-down long-press while
    // FinWise is open starts capture; phone Settings bind finwise://voice
    // to a hardware key (side key, Back Tap, Action Button).
    if (event.logicalKey != LogicalKeyboardKey.audioVolumeDown) {
      return false;
    }
    if (event is KeyDownEvent) {
      _holdFired = false;
      _holdTimer?.cancel();
      _holdTimer = Timer(const Duration(milliseconds: 700), () {
        _holdFired = true;
        _emitVoiceRequest();
      });
    } else if (event is KeyUpEvent) {
      _holdTimer?.cancel();
      _holdTimer = null;
    }
    return false;
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    debugPrint("FinanseSpeech.$name($args)");
    switch (name) {
      case "is_available":
        return await _speech.initialize();
      case "listen":
        return _listen(args);
      case "take_pending_voice":
        final pending = _pendingVoice;
        _pendingVoice = false;
        return pending;
      default:
        throw Exception("Unknown FinanseSpeech method: $name");
    }
  }

  String _lastWords() {
    try {
      return _speech.lastRecognizedWords.trim();
    } catch (_) {
      return "";
    }
  }

  Future<Map<String, dynamic>> _listen(dynamic args) async {
    final locale = (args?["locale"] as String?) ?? "ru_RU";
    final seconds = (args?["seconds"] as num?)?.toInt() ?? 8;
    try {
      final ready = await _speech.initialize();
      if (!ready) {
        return {"ok": false, "text": "", "error": "unavailable"};
      }
      final completer = Completer<String>();
      await _speech.listen(
        onResult: (result) {
          final text = result.recognizedWords.trim();
          if (result.finalResult && text.isNotEmpty && !completer.isCompleted) {
            completer.complete(text);
          }
        },
        listenFor: Duration(seconds: seconds),
        pauseFor: const Duration(seconds: 3),
        localeId: locale,
        partialResults: true,
        cancelOnError: true,
        listenMode: ListenMode.confirmation,
      );
      final text = await completer.future.timeout(
        Duration(seconds: seconds + 4),
        onTimeout: () => _lastWords(),
      );
      try {
        await _speech.stop();
      } catch (_) {}
      final spoken = text.trim().isNotEmpty ? text.trim() : _lastWords();
      return {
        "ok": spoken.isNotEmpty,
        "text": spoken,
        "error": spoken.isEmpty ? "empty" : null,
      };
    } catch (error) {
      try {
        await _speech.stop();
      } catch (_) {}
      return {"ok": false, "text": "", "error": error.toString()};
    }
  }

  @override
  void dispose() {
    _holdTimer?.cancel();
    HardwareKeyboard.instance.removeHandler(_onKey);
    WidgetsBinding.instance.removeObserver(this);
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
