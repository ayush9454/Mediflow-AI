import 'dart:convert';
import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mediflow_ai/core/contracts/contracts.g.dart';
import 'package:mediflow_ai/features/reports/evidence_screen.dart';
import 'package:mediflow_ai/features/reports/report_api.dart';
import 'package:mediflow_ai/features/reports/report_platform.dart';

import 'report_workflow_test.dart' show DeviceFiles;
import 'result_api_test.dart' show fixture, resultReport;

final doctor = Account.fromJson({
  'schemaVersion': '1.0',
  'uid': 'doctor_a',
  'hospitalId': 'hospital_1',
  'displayName': 'Synthetic Doctor',
  'role': 'doctor',
  'active': true,
});

class PageRenderer extends DeviceFiles {
  final pages = <int>[];
  @override
  Future<PdfPageImage> render(Uint8List source, int page) async {
    pages.add(page);
    return PdfPageImage(
      base64Decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=',
      ),
      2,
    );
  }
}

class UnreadableRenderer extends PageRenderer {
  @override
  Future<PdfPageImage> render(Uint8List source, int page) async =>
      throw const FormatException('unreadable');
}

Map<String, dynamic> draftPayload({int page = 2}) {
  final draft = fixture('analysis');
  draft['rows'][0]['evidence'][0]['page'] = page;
  draft['rows'][0]['unit'] = null;
  return {
    'schemaVersion': '1.0',
    'kind': 'draft',
    'draft': draft,
    'approved': null,
  };
}

http.Response jsonResponse(Object value) =>
    http.Response.bytes(utf8.encode(jsonEncode(value)), 200);

void main() {
  testWidgets(
    'source links show disabled state while authorization refresh is pending',
    (tester) async {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      final refresh = Completer<http.Response>();
      var metadataReads = 0;
      final metadata = {
        ...resultReport().toJson(),
        'assignedDoctorId': 'doctor_a',
      };
      final api = PatientReportApi(
        Uri.parse('https://example.invalid'),
        MockClient((request) async {
          if (request.url.path.endsWith('/result')) {
            return jsonResponse(draftPayload());
          }
          return ++metadataReads == 1 ? jsonResponse(metadata) : refresh.future;
        }),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: EvidenceResultScreen(
            account: doctor,
            reportId: 'report_1',
            api: api,
            platform: PageRenderer(),
            token: () => 'token',
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Open source page 2'));
      await tester.pump(const Duration(seconds: 16));
      expect(
        tester
            .widget<OutlinedButton>(
              find.byWidgetPredicate((widget) => widget is OutlinedButton),
            )
            .onPressed,
        isNull,
      );
      refresh.complete(jsonResponse(metadata));
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<OutlinedButton>(
              find.byWidgetPredicate((widget) => widget is OutlinedButton),
            )
            .onPressed,
        isNotNull,
      );
      await tester.pumpWidget(const SizedBox());
    },
  );
  testWidgets('an unreadable source page reports an explicit evidence issue', (
    tester,
  ) async {
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    final api = PatientReportApi(
      Uri.parse('https://example.invalid'),
      MockClient((request) async {
        if (request.url.path.endsWith('/document')) {
          return http.Response(
            '%PDF-synthetic',
            200,
            headers: {'content-type': 'application/pdf'},
          );
        }
        if (request.url.path.endsWith('/result')) {
          return jsonResponse(draftPayload());
        }
        return jsonResponse({
          ...resultReport().toJson(),
          'assignedDoctorId': 'doctor_a',
        });
      }),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: EvidenceResultScreen(
          account: doctor,
          reportId: 'report_1',
          api: api,
          platform: UnreadableRenderer(),
          token: () => 'token',
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Open source page 2'));
    await tester.tap(find.text('Open source page 2'));
    await tester.pumpAndSettle();
    expect(
      find.textContaining('Unreadable or invalid source page'),
      findsOneWidget,
    );
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
    'long quotations leave room for the source page on a narrow phone',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      final payload = draftPayload();
      payload['draft']['rows'][0]['evidence'][0]['quotation'] =
          'Synthetic quotation ' * 100;
      final api = PatientReportApi(
        Uri.parse('https://example.invalid'),
        MockClient((request) async {
          if (request.url.path.endsWith('/document')) {
            return http.Response(
              '%PDF-synthetic',
              200,
              headers: {'content-type': 'application/pdf'},
            );
          }
          if (request.url.path.endsWith('/result')) {
            return jsonResponse(payload);
          }
          return jsonResponse({
            ...resultReport().toJson(),
            'assignedDoctorId': 'doctor_a',
          });
        }),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: EvidenceResultScreen(
            account: doctor,
            reportId: 'report_1',
            api: api,
            platform: PageRenderer(),
            token: () => 'token',
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Open source page 2'));
      await tester.tap(find.text('Open source page 2'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('Page 2 of 2'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );
  testWidgets(
    'invalid and missing evidence are explicit and cannot open a PDF',
    (tester) async {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      final payload = draftPayload(page: 3);
      final missing = Map<String, dynamic>.from(
        payload['draft']['rows'][0] as Map,
      );
      missing.addAll({
        'rowId': 'missing',
        'analyte': 'Missing source marker',
        'evidence': [],
      });
      payload['draft']['rows'].add(missing);
      var documentRequests = 0;
      final api = PatientReportApi(
        Uri.parse('https://example.invalid'),
        MockClient((request) async {
          if (request.url.path.endsWith('/document')) documentRequests++;
          if (request.url.path.endsWith('/result')) {
            return jsonResponse(payload);
          }
          return jsonResponse({
            ...resultReport().toJson(),
            'assignedDoctorId': 'doctor_a',
          });
        }),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: EvidenceResultScreen(
            account: doctor,
            reportId: 'report_1',
            api: api,
            platform: PageRenderer(),
            token: () => 'token',
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.textContaining('Invalid evidence'), findsOneWidget);
      await tester.ensureVisible(find.textContaining('Missing evidence'));
      expect(find.textContaining('Missing evidence'), findsOneWidget);
      expect(find.textContaining('Open source page'), findsNothing);
      expect(documentRequests, 0);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'approved snapshot labels clinician corrections and unresolved reasons',
    (tester) async {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      final payload = fixture('approved-result');
      payload['approved']['provenance'] = fixture('analysis')['provenance'];
      payload['approved']['correctedRowIds'] = ['row_1'];
      payload['approved']['unresolvedAcknowledgements'] = [
        {'issueId': 'issue_1', 'reason': 'Printed unit is unclear'},
      ];
      payload['approved']['rows'][0]['issues'] = [
        {
          'issueId': 'issue_1',
          'field': 'unit',
          'code': 'unreadable',
          'severity': 'blocking',
          'message': 'Verify the source unit',
        },
      ];
      final patientAccount = Account.fromJson({
        ...doctor.toJson(),
        'role': 'patient',
        'uid': 'patient_a',
      });
      final api = PatientReportApi(
        Uri.parse('https://example.invalid'),
        MockClient((request) async {
          if (request.url.path.endsWith('/result')) {
            return jsonResponse(payload);
          }
          return jsonResponse({
            ...resultReport().toJson(),
            'latestAnalysisId': 'replacement',
            'reviewStatus': 'rejected',
          });
        }),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: EvidenceResultScreen(
            account: patientAccount,
            reportId: 'report_1',
            api: api,
            platform: PageRenderer(),
            token: () => 'token',
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Approved snapshot'), findsOneWidget);
      expect(
        find.text('Unresolved qualification: Printed unit is unclear'),
        findsOneWidget,
      );
      expect(find.text('AI candidate'), findsNothing);
      expect(
        find.text(
          'The replacement was not approved. This previously approved version remains available.',
        ),
        findsOneWidget,
      );
      await tester.ensureVisible(find.text('Clinician corrected · approved'));
      expect(find.text('Clinician corrected · approved'), findsOneWidget);
      expect(
        find.text('Unresolved · unit: Printed unit is unclear'),
        findsOneWidget,
      );
      await tester.scrollUntilVisible(
        find.text('Analysis provenance'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Analysis provenance'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Prompt:'), findsNothing);
      expect(find.textContaining('SHA-256:'), findsNothing);
      await tester.pumpWidget(const SizedBox());
    },
  );
  for (final expiry in [false, true]) {
    testWidgets(
      expiry
          ? 'retention expiry clears the visible result without another tap'
          : 'foreground authorization refresh clears a revoked result',
      (tester) async {
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.resumed,
        );
        var revoked = false;
        final api = PatientReportApi(
          Uri.parse('https://example.invalid'),
          MockClient((request) async {
            if (revoked) return http.Response('', 403);
            if (request.url.path.endsWith('/result')) {
              return jsonResponse(draftPayload());
            }
            return jsonResponse({
              ...resultReport().toJson(),
              'assignedDoctorId': 'doctor_a',
              if (expiry)
                'expiresAt': DateTime.now()
                    .add(const Duration(seconds: 5))
                    .toUtc()
                    .toIso8601String(),
            });
          }),
        );
        await tester.pumpWidget(
          MaterialApp(
            home: EvidenceResultScreen(
              account: doctor,
              reportId: 'report_1',
              api: api,
              platform: PageRenderer(),
              token: () => 'token',
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(find.text('AI candidate · not approved'), findsOneWidget);
        revoked = true;
        await tester.pump(Duration(seconds: expiry ? 6 : 16));
        await tester.pumpAndSettle();
        expect(find.text('AI candidate · not approved'), findsNothing);
        expect(
          find.textContaining(expiry ? 'expired' : 'cannot access'),
          findsOneWidget,
        );
        await tester.pumpWidget(const SizedBox());
      },
    );
  }
  testWidgets(
    'background clears results and rejects a late PDF; resume rechecks revoked access',
    (tester) async {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      final download = Completer<http.Response>();
      final renderer = PageRenderer();
      var revoked = false;
      final api = PatientReportApi(
        Uri.parse('https://example.invalid'),
        MockClient((request) async {
          if (revoked) return http.Response('', 403);
          if (request.url.path.endsWith('/document')) return download.future;
          if (request.url.path.endsWith('/result')) {
            return jsonResponse(draftPayload());
          }
          return jsonResponse({
            ...resultReport().toJson(),
            'assignedDoctorId': 'doctor_a',
          });
        }),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: EvidenceResultScreen(
            account: doctor,
            reportId: 'report_1',
            api: api,
            platform: renderer,
            token: () => 'token',
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Open source page 2'));
      await tester.tap(find.text('Open source page 2'));
      await tester.pump();
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pump();
      expect(find.textContaining('Synthetic Marker'), findsNothing);
      download.complete(
        http.Response(
          '%PDF-synthetic',
          200,
          headers: {'content-type': 'application/pdf'},
        ),
      );
      await tester.pumpAndSettle();
      expect(renderer.pages, isEmpty);
      revoked = true;
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(find.textContaining('cannot access this report'), findsOneWidget);
      expect(find.textContaining('Synthetic Marker'), findsNothing);
      await tester.pumpWidget(const SizedBox());
    },
  );
  testWidgets(
    'doctor sees printed candidate fields and opens the exact source page',
    (tester) async {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      final renderer = PageRenderer();
      var documentRequests = 0;
      final api = PatientReportApi(
        Uri.parse('https://example.invalid'),
        MockClient((request) async {
          if (request.url.path.endsWith('/document')) {
            documentRequests++;
            return http.Response(
              '%PDF-synthetic',
              200,
              headers: {'content-type': 'application/pdf'},
            );
          }
          if (request.url.path.endsWith('/result')) {
            return jsonResponse(draftPayload());
          }
          return jsonResponse({
            ...resultReport().toJson(),
            'assignedDoctorId': 'doctor_a',
          });
        }),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: EvidenceResultScreen(
            account: doctor,
            reportId: 'report_1',
            api: api,
            platform: renderer,
            token: () => 'token',
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('AI candidate · not approved'), findsOneWidget);
      expect(find.textContaining('<0.50'), findsWidgets);
      expect(find.text('Unit: Missing from extracted data'), findsOneWidget);
      await tester.ensureVisible(find.text('Open source page 2'));
      await tester.tap(find.text('Open source page 2'));
      await tester.pumpAndSettle();
      expect(renderer.pages, [1]);
      expect(documentRequests, 1);
      expect(find.text('Page 2 of 2'), findsOneWidget);
      expect(
        find.textContaining('Synthetic Marker <0.50 SYN-U'),
        findsOneWidget,
      );
      await tester.pumpWidget(const SizedBox());
    },
  );
}
