import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mediflow_ai/core/config/app_config.dart';
import 'package:mediflow_ai/core/contracts/contracts.g.dart';
import 'package:mediflow_ai/features/auth/session.dart';

void main() {
  test(
    'email password sign-in sends Firebase ID token to trusted backend /me',
    () async {
      final paths = <String>[];
      final gateway = FirebaseSessionGateway(
        AppConfig(
          apiBaseUrl: Uri.parse('https://demo.example.test'),
          enableRolePreview: false,
          firebaseApiKey: 'public-api-key',
        ),
        MockClient((request) async {
          paths.add(request.url.path);
          if (request.url.host == 'identitytoolkit.googleapis.com') {
            expect(request.url.path, '/v1/accounts:signInWithPassword');
            expect(jsonDecode(request.body), {
              'email': 'doctor@example.test',
              'password': 'secret-password',
              'returnSecureToken': true,
            });
            return http.Response(
              jsonEncode({'idToken': 'signed-token', 'expiresIn': '3600'}),
              200,
            );
          }
          expect(request.url.path, '/api/v1/me');
          expect(request.headers['Authorization'], 'Bearer signed-token');
          return http.Response(
            jsonEncode({
              'schemaVersion': '1.0',
              'uid': 'doctor_a',
              'hospitalId': 'hospital_demo',
              'displayName': 'Synthetic Doctor',
              'role': 'doctor',
              'active': true,
            }),
            200,
          );
        }),
      );
      final controller = SessionController(gateway, SensitiveCache());
      addTearDown(controller.dispose);
      await controller.signIn(' doctor@example.test ', 'secret-password');
      expect(controller.state.account?.role, Role.doctor);
      expect(paths, ['/v1/accounts:signInWithPassword', '/api/v1/me']);
    },
  );
}
