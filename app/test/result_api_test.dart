import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mediflow_ai/core/api/api_client.dart';
import 'package:mediflow_ai/core/contracts/contracts.g.dart';
import 'package:mediflow_ai/features/reports/report_api.dart';

import 'report_workflow_test.dart' show metadata;

Map<String, dynamic> fixture(String name) =>
    jsonDecode(File('../contracts/examples/$name.json').readAsStringSync())
        as Map<String, dynamic>;

ReportMetadata resultReport() => ReportMetadata.fromJson({
  ...metadata(status: 'succeeded'),
  'latestAnalysisId': 'analysis_1',
  'approvedAnalysisId': 'analysis_1',
  'pageCount': 2,
});

void main() {
  test(
    'result identity and version pointers are checked, and expiry stays actionable',
    () async {
      var status = 200;
      final payload = fixture('approved-result');
      final api = PatientReportApi(
        Uri.parse('https://example.invalid'),
        MockClient(
          (_) async => status == 200
              ? http.Response.bytes(utf8.encode(jsonEncode(payload)), 200)
              : http.Response('PRIVATE DETAILS', status),
        ),
      );
      addTearDown(api.close);
      payload['approved']['reportId'] = 'someone_else';
      await expectLater(
        api.result('token', resultReport(), role: Role.patient),
        throwsA(isA<ApiFailure>()),
      );
      payload['approved']['reportId'] = 'report_1';
      payload['approved']['analysisId'] = 'other_version';
      await expectLater(
        api.result('token', resultReport(), role: Role.patient),
        throwsA(isA<ApiFailure>()),
      );
      status = 401;
      await expectLater(
        api.result('token', resultReport(), role: Role.patient),
        throwsA(
          isA<ApiFailure>().having(
            (e) => e.code,
            'code',
            ErrorCode.unauthenticated,
          ),
        ),
      );
      status = 410;
      await expectLater(
        api.result('token', resultReport(), role: Role.patient),
        throwsA(
          isA<ApiFailure>().having((e) => e.code, 'code', ErrorCode.expired),
        ),
      );
    },
  );
  test(
    'patient result requests approval and rejects draft or mixed payloads',
    () async {
      var payload = fixture('approved-result');
      final api = PatientReportApi(
        Uri.parse('https://example.invalid'),
        MockClient((request) async {
          expect(request.headers['Authorization'], 'Bearer session');
          expect(request.url.queryParameters['kind'], 'approved');
          return http.Response.bytes(utf8.encode(jsonEncode(payload)), 200);
        }),
      );
      addTearDown(api.close);
      expect(
        (await api.result(
          'session',
          resultReport(),
          role: Role.patient,
        )).approved!.analysisVersion,
        1,
      );
      payload = {
        'kind': 'draft',
        'draft': fixture('analysis'),
        'approved': null,
        'schemaVersion': '1.0',
      };
      await expectLater(
        api.result('session', resultReport(), role: Role.patient),
        throwsA(isA<ApiFailure>()),
      );
      payload = {...fixture('approved-result'), 'draft': fixture('analysis')};
      await expectLater(
        api.result('session', resultReport(), role: Role.patient),
        throwsA(isA<ApiFailure>()),
      );
    },
  );
}
