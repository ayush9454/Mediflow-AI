// Socket-free check for restricted environments. Full widget tests still belong in CI.
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mediflow_ai/core/api/api_client.dart';
import 'package:mediflow_ai/core/contracts/contracts.g.dart';

Map<String, Object?> fixture(String name) =>
    (jsonDecode(File('../contracts/examples/$name.json').readAsStringSync())
            as Map)
        .cast<String, Object?>();

void check(bool condition, String message) {
  if (!condition) throw StateError(message);
}

Future<void> main() async {
  final account = Account.fromJson(fixture('account'));
  check(account.role == Role.patient, 'Account role contract mismatch');
  final report = ReportMetadata.fromJson(fixture('report'));
  check(
    report.processingStatus == ProcessingStatus.queued,
    'Processing status mismatch',
  );
  check(report.reviewStatus == ReviewStatus.notReady, 'Review status mismatch');
  final candidate = AnalysisCandidate.fromJson(fixture('analysis'));
  final row = candidate.rows.single;
  check(row.result == '<0.50', 'Printed inequality/precision changed');
  check(row.referenceRange == '0.00–1.00', 'Printed reference range changed');
  check(row.evidence.single.page == 1, 'Evidence page mismatch');
  final roundTrip = AnalysisCandidate.fromJson(candidate.toJson());
  check(
    roundTrip.createdAt == candidate.createdAt,
    'Timestamp round-trip mismatch',
  );
  final approved = ReportResult.fromJson(fixture('approved-result'));
  check(
    approved.kind == ResultKind.approved && approved.draft == null,
    'Draft leaked into approved result',
  );
  check(
    ReviewRequest.fromJson(fixture('review')).expectedAnalysisVersion == 1,
    'Review version missing',
  );
  var invalidRoleRejected = false;
  try {
    Role.fromJson('superuser');
  } on FormatException {
    invalidRoleRejected = true;
  }
  check(invalidRoleRejected, 'Unknown role was accepted');

  final client = MockClient((request) async {
    check(request.url.path == '/health/live', 'Unexpected endpoint');
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
  try {
    final health = await ApiClient(
      baseUrl: Uri.parse('https://example.invalid'),
      client: client,
    ).liveness();
    check(health.syntheticDataOnly, 'Synthetic-only service identity missing');
  } finally {
    client.close();
  }
  final badClient = MockClient(
    (_) async => http.Response('PRIVATE RESPONSE CONTENT', 200),
  );
  try {
    var failedSafely = false;
    try {
      await ApiClient(
        baseUrl: Uri.parse('https://example.invalid'),
        client: badClient,
      ).liveness();
    } on ApiFailure catch (error) {
      failedSafely = !error.message.contains('PRIVATE');
    }
    check(failedSafely, 'Malformed response was not rejected safely');
  } finally {
    badClient.close();
  }
  stdout.writeln(
    'Contract and API smoke checks passed (no local sockets required).',
  );
}
