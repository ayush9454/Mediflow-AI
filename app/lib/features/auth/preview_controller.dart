import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/config/app_config.dart';
import '../../core/contracts/contracts.g.dart';

/// Debug UI selection only. This never represents an authenticated account.
class PreviewRoleController extends Notifier<Role?> {
  @override
  Role? build() => null;

  void open(Role role) {
    if (!ref.read(appConfigProvider).enableRolePreview) {
      throw StateError('Interface previews are disabled.');
    }
    state = role;
  }

  void close() => state = null;
}

final previewRoleProvider = NotifierProvider<PreviewRoleController, Role?>(
  PreviewRoleController.new,
);

extension RolePresentation on Role {
  String get label => switch (this) {
    Role.patient => 'Patient',
    Role.doctor => 'Doctor',
    Role.administrator => 'Administrator',
  };
}
