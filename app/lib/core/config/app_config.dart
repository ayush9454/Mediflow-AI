import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class AppConfig {
  const AppConfig({
    required this.apiBaseUrl,
    required this.enableRolePreview,
    this.firebaseApiKey = '',
  });

  factory AppConfig.fromEnvironment() {
    const configuredUrl = String.fromEnvironment('API_BASE_URL');
    const requestedPreview = bool.fromEnvironment(
      'ENABLE_ROLE_PREVIEW',
      defaultValue: true,
    );
    final url = configuredUrl.isEmpty ? null : Uri.tryParse(configuredUrl);
    if (configuredUrl.isNotEmpty &&
        (url == null ||
            !url.hasAuthority ||
            url.host.isEmpty ||
            (url.scheme != 'https' && !(kDebugMode && url.scheme == 'http')) ||
            url.userInfo.isNotEmpty ||
            url.hasQuery ||
            url.hasFragment ||
            (url.path.isNotEmpty && url.path != '/'))) {
      throw StateError(
        'API_BASE_URL must be an origin URL; HTTPS is required outside debug.',
      );
    }
    return AppConfig(
      apiBaseUrl: url,
      firebaseApiKey: const String.fromEnvironment('FIREBASE_API_KEY'),
      enableRolePreview: kDebugMode && requestedPreview,
    );
  }

  final Uri? apiBaseUrl;
  final String firebaseApiKey;
  final bool enableRolePreview;
}

final appConfigProvider = Provider<AppConfig>(
  (ref) => AppConfig.fromEnvironment(),
);
