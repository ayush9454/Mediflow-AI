import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mediflow_ai/core/api/api_client.dart';

void main() {
  test(
    'liveness checks service identity without sending credentials',
    () async {
      final client = MockClient((request) async {
        expect(request.url.path, '/health/live');
        expect(request.headers.containsKey('Authorization'), isFalse);
        return http.Response(
          jsonEncode({
            'schemaVersion': '1.0',
            'status': 'ok',
            'service': 'mediflow-api',
            'syntheticDataOnly': true,
            'version': '0.1.0',
          }),
          200,
        );
      });
      addTearDown(client.close);
      final result = await ApiClient(
        baseUrl: Uri.parse('https://example.invalid'),
        client: client,
      ).liveness();
      expect(result.status, 'ok');
    },
  );

  test('a malformed response never becomes a successful connection', () async {
    final client = MockClient(
      (_) async => http.Response('PRIVATE RAW RESPONSE', 200),
    );
    addTearDown(client.close);
    await expectLater(
      ApiClient(
        baseUrl: Uri.parse('https://example.invalid'),
        client: client,
      ).liveness(),
      throwsA(
        isA<ApiFailure>().having(
          (e) => e.message,
          'safe message',
          isNot(contains('PRIVATE')),
        ),
      ),
    );
  });

  test('a different service cannot impersonate the backend', () async {
    final client = MockClient(
      (_) async => http.Response(
        jsonEncode({
          'schemaVersion': '1.0',
          'status': 'ok',
          'service': 'another-service',
          'syntheticDataOnly': true,
          'version': '0.1.0',
        }),
        200,
      ),
    );
    addTearDown(client.close);
    await expectLater(
      ApiClient(
        baseUrl: Uri.parse('https://example.invalid'),
        client: client,
      ).liveness(),
      throwsA(isA<ApiFailure>()),
    );
  });
}
