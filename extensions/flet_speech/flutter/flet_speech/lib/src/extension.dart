import 'package:flet/flet.dart';
import 'package:flutter/widgets.dart';

import 'speech_service.dart';

class Extension extends FletExtension {
  @override
  void ensureInitialized() {}

  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "FinanseSpeech":
        return FinanseSpeechService(control: control);
      default:
        return null;
    }
  }

  @override
  Widget? createWidget(Key? key, Control control) {
    return null;
  }
}
