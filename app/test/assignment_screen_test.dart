import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mediflow_ai/core/contracts/contracts.g.dart';
import 'package:mediflow_ai/features/reports/report_api.dart';
import 'package:mediflow_ai/features/workspace/workflow_screen.dart';

import 'evidence_screen_test.dart' show doctor;

void main() {
  for (final reviewed in [false, true]) {
    testWidgets(
      'doctor requests the ${reviewed ? 'reviewed' : 'pending'} workspace',
      (tester) async {
        String? view;
        final api = PatientReportApi(
          Uri.parse('https://example.invalid'),
          MockClient((request) async {
            view = request.url.queryParameters['view'];
            return http.Response(
              '{"schemaVersion":"1.0","items":[],"nextCursor":"next_page"}',
              200,
            );
          }),
        );
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: WorkflowPanel(
                account: doctor,
                api: api,
                token: () => 'token',
                reviews: reviewed,
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(view, reviewed ? 'reviewed' : 'pending');
        expect(
          find.text('No matching cases on this page. Load more to continue.'),
          findsOneWidget,
        );
        expect(find.text('Load more cases'), findsOneWidget);
        await tester.pumpWidget(const SizedBox());
      },
    );
  }
  testWidgets(
    'administrator chooses an eligible doctor and submits the displayed case version',
    (tester) async {
      Map<String, dynamic>? submission;
      var assigned = false;
      final item = {
        'schemaVersion': '1.0',
        'caseId': 'case_1',
        'reportId': 'report_1',
        'patientId': 'patient_a',
        'assignedDoctorId': null,
        'processingStatus': 'succeeded',
        'reviewStatus': 'pending',
        'version': 1,
        'reviewVersion': 0,
        'createdAt': '2026-10-25T10:00:00Z',
        'expiresAt': null,
        'failureCode': null,
      };
      final api = PatientReportApi(
        Uri.parse('https://example.invalid'),
        MockClient((request) async {
          Object payload;
          if (request.method == 'POST') {
            submission = jsonDecode(request.body);
            expect(request.headers['Idempotency-Key'], isNotEmpty);
            assigned = true;
            payload = {...item, 'assignedDoctorId': 'doctor_a', 'version': 2};
          } else if (request.url.path.endsWith('/doctors')) {
            payload = {
              'schemaVersion': '1.0',
              'items': [
                {
                  'doctorId': 'doctor_a',
                  'displayName': 'Synthetic Doctor',
                  'department': 'Laboratory',
                  'active': true,
                },
              ],
              'nextCursor': null,
            };
          } else {
            payload = {
              'schemaVersion': '1.0',
              'items': [
                {...item, if (assigned) 'assignedDoctorId': 'doctor_a'},
              ],
              'nextCursor': null,
            };
          }
          return http.Response.bytes(utf8.encode(jsonEncode(payload)), 200);
        }),
      );
      final admin = Account.fromJson({
        ...doctor.toJson(),
        'uid': 'admin',
        'role': 'administrator',
      });
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: WorkflowPanel(account: admin, api: api, token: () => 'token'),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Assign doctor'));
      await tester.pumpAndSettle();
      await tester.pump(const Duration(seconds: 16));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Synthetic Doctor · Laboratory'));
      await tester.pumpAndSettle();
      expect(submission, {'doctorId': 'doctor_a', 'expectedCaseVersion': 1});
      expect(find.textContaining('doctor_a'), findsWidgets);
      await tester.pumpWidget(const SizedBox());
    },
  );
}
