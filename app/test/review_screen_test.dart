import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mediflow_ai/features/reports/report_api.dart';
import 'package:mediflow_ai/features/reviews/review_screen.dart';

import 'evidence_screen_test.dart' show doctor;
import 'result_api_test.dart' show fixture, resultReport;

PatientReportApi reviewApi(
  Future<http.Response> Function(http.Request) write, {
  bool Function()? revoked,
}) => PatientReportApi(
  Uri.parse('https://example.invalid'),
  MockClient((request) async {
    if (revoked?.call() == true) return http.Response('', 403);
    if (request.method == 'POST') return write(request);
    final Object payload = request.url.path.endsWith('/reviews')
        ? {'schemaVersion': '1.0', 'items': [], 'nextCursor': null}
        : request.url.path.endsWith('/result')
        ? {
            'schemaVersion': '1.0',
            'kind': 'draft',
            'draft': fixture('analysis'),
            'approved': null,
          }
        : {
            ...resultReport().toJson(),
            'assignedDoctorId': 'doctor_a',
            'caseVersion': 2,
            'reviewVersion': 0,
            'processingStatus': 'succeeded',
            'reviewStatus': 'under_review',
          };
    return http.Response.bytes(utf8.encode(jsonEncode(payload)), 200);
  }),
);

http.Response recorded(http.Request request) => http.Response.bytes(
  utf8.encode(
    jsonEncode({
      'schemaVersion': '1.0',
      'reviewId': 'review_1',
      'version': 1,
      'reportId': 'report_1',
      'reviewerId': 'doctor_a',
      'reviewedAt': '2026-10-25T10:00:00Z',
      'request': jsonDecode(request.body),
      'originalRows': [],
    }),
  ),
  201,
);

Future<void> showReview(WidgetTester tester, PatientReportApi api) async {
  tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
  await tester.pumpWidget(
    MaterialApp(
      home: DoctorReviewScreen(
        account: doctor,
        reportId: 'report_1',
        api: api,
        token: () => 'token',
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets(
    'doctor begins a version-pinned review and approves with an explicit qualification',
    (tester) async {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      var version = 2;
      String status = 'pending';
      Map<String, dynamic>? submitted;
      final draft = fixture('analysis');
      draft['issues'] = [
        {
          'issueId': 'quality',
          'field': 'document',
          'code': 'quality',
          'severity': 'blocking',
          'message': 'Scan is unclear',
        },
      ];
      final api = PatientReportApi(
        Uri.parse('https://example.invalid'),
        MockClient((request) async {
          Object value;
          var code = 200;
          if (request.url.path.endsWith('/begin-review')) {
            final body = jsonDecode(request.body);
            expect(body['expectedCaseVersion'], 2);
            expect(request.headers['Idempotency-Key'], isNotEmpty);
            version = 3;
            status = 'under_review';
            value = {
              'schemaVersion': '1.0',
              'caseId': 'case_1',
              'reportId': 'report_1',
              'patientId': 'patient_a',
              'assignedDoctorId': 'doctor_a',
              'processingStatus': 'succeeded',
              'reviewStatus': status,
              'version': version,
              'reviewVersion': 0,
              'createdAt': '2026-10-20T10:00:00Z',
              'expiresAt': null,
              'failureCode': null,
            };
          } else if (request.url.path.endsWith('/review')) {
            submitted = jsonDecode(request.body);
            code = 201;
            value = {
              'schemaVersion': '1.0',
              'reviewId': 'review_1',
              'version': 1,
              'reportId': 'report_1',
              'reviewerId': 'doctor_a',
              'reviewedAt': '2026-10-25T10:00:00Z',
              'request': submitted,
            };
          } else if (request.url.path.endsWith('/reviews')) {
            value = {'schemaVersion': '1.0', 'items': [], 'nextCursor': null};
          } else if (request.url.path.endsWith('/result')) {
            value = {
              'schemaVersion': '1.0',
              'kind': 'draft',
              'draft': draft,
              'approved': null,
            };
          } else {
            value = {
              ...resultReport().toJson(),
              'assignedDoctorId': 'doctor_a',
              'caseVersion': version,
              'reviewVersion': 0,
              'processingStatus': 'succeeded',
              'reviewStatus': status,
            };
          }
          return http.Response.bytes(utf8.encode(jsonEncode(value)), code);
        }),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: DoctorReviewScreen(
            account: doctor,
            reportId: 'report_1',
            api: api,
            token: () => 'token',
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Begin review'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const ValueKey('unresolved-quality')),
        'Printed scan remains unclear',
      );
      await tester.scrollUntilVisible(
        find.text('Approve with qualifications'),
        250,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Approve with qualifications'));
      await tester.pumpAndSettle();
      expect(submitted?['expectedCaseVersion'], 3);
      expect(submitted?['analysisId'], 'analysis_1');
      expect(submitted?['unresolvedAcknowledgements'], [
        {'issueId': 'quality', 'reason': 'Printed scan remains unclear'},
      ]);
      expect(find.textContaining('Decision recorded'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );
  testWidgets('rejection requires a reason and sends no approval changes', (
    tester,
  ) async {
    Map<String, dynamic>? submitted;
    await showReview(
      tester,
      reviewApi((request) async {
        submitted = jsonDecode(request.body);
        return recorded(request);
      }),
    );
    await tester.scrollUntilVisible(
      find.text('Reject analysis'),
      250,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Reject analysis'));
    await tester.pumpAndSettle();
    expect(submitted, isNull);
    expect(find.text('Enter a reason before rejecting.'), findsOneWidget);
    await tester.enterText(
      find.widgetWithText(TextField, 'Decision / reprocessing reason'),
      'Row is unsupported',
    );
    await tester.tap(find.text('Reject analysis'));
    await tester.pumpAndSettle();
    expect(submitted?['decision'], 'rejected');
    expect(submitted?['comment'], 'Row is unsupported');
    expect(submitted?['corrections'], isEmpty);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
    'correction preserves the original row reference and requires evidence and a reason',
    (tester) async {
      Map<String, dynamic>? submitted;
      await showReview(
        tester,
        reviewApi((request) async {
          submitted = jsonDecode(request.body);
          return recorded(request);
        }),
      );
      await tester.tap(find.text('Synthetic Marker'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Correct this row'));
      await tester.pumpAndSettle();
      final result = find.byKey(const ValueKey('row_1-result'));
      await tester.ensureVisible(result);
      await tester.enterText(result, '<0.60');
      await tester.scrollUntilVisible(
        find.widgetWithText(TextField, 'Source quotation'),
        250,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Source quotation'),
        'Synthetic Marker <0.60 SYN-U 0.00–1.00',
      );
      await tester.scrollUntilVisible(
        find.widgetWithText(TextField, 'Correction reason'),
        250,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Correction reason'),
        'Compared with the source',
      );
      await tester.scrollUntilVisible(
        find.text('Correct and approve'),
        250,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Correct and approve'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Correct and approve'));
      await tester.pumpAndSettle();
      final correction = (submitted?['corrections'] as List).single;
      expect(correction['rowId'], 'row_1');
      expect(correction['correctedRow']['result'], '<0.60');
      expect(correction['correctedRow']['evidence'][0]['page'], 1);
      expect(correction['reason'], 'Compared with the source');
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'uncertain review retry retains the exact payload and idempotency key',
    (tester) async {
      final requests = <http.Request>[];
      await showReview(
        tester,
        reviewApi((request) async {
          requests.add(request);
          return requests.length == 1
              ? http.Response('', 503)
              : recorded(request);
        }),
      );
      await tester.scrollUntilVisible(
        find.text('Approve'),
        250,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Approve'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('Retry same operation'),
        -250,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Retry same operation'));
      await tester.pumpAndSettle();
      expect(requests.length, 2);
      expect(requests[0].body, requests[1].body);
      expect(
        requests[0].headers['Idempotency-Key'],
        requests[1].headers['Idempotency-Key'],
      );
      expect(find.textContaining('Decision recorded'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets('revoked assignment clears the review form and candidate', (
    tester,
  ) async {
    var revoked = false;
    await showReview(
      tester,
      reviewApi((request) async => recorded(request), revoked: () => revoked),
    );
    expect(find.text('Synthetic Marker'), findsOneWidget);
    revoked = true;
    await tester.pump(const Duration(seconds: 16));
    await tester.pumpAndSettle();
    expect(find.text('Synthetic Marker'), findsNothing);
    expect(find.textContaining('cannot access'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });
}
