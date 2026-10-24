import 'dart:convert';
import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mediflow_ai/features/reports/report_api.dart';
import 'package:mediflow_ai/features/reports/report_controller.dart';
import 'package:mediflow_ai/features/reports/report_screen.dart';

import 'report_workflow_test.dart' show DeviceFiles, patient, metadata;
import 'package:mediflow_ai/features/reports/report_platform.dart';

class RenderingFiles extends DeviceFiles {
  int renders = 0;
  @override
  Future<PdfPageImage> render(Uint8List source, int page) async {
    renders++;
    throw UnimplementedError();
  }
}

void main() {
  testWidgets(
    'a document download completing after background never opens or renders',
    (tester) async {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      final response = Completer<http.Response>();
      final files = RenderingFiles();
      final controller = PatientReportsController(
        account: patient,
        token: () => 'token',
        platform: files,
        api: PatientReportApi(
          Uri.parse('https://example.invalid'),
          MockClient((request) async {
            if (request.url.path.endsWith('/document')) return response.future;
            if (request.url.path == '/api/v1/cases') {
              return http.Response('{"items":[],"nextCursor":null}', 200);
            }
            return http.Response(
              jsonEncode(metadata(status: 'succeeded')),
              200,
            );
          }),
        ),
      );
      addTearDown(controller.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: PatientReportsPanel(controller: controller)),
        ),
      );
      await tester.pumpAndSettle();
      await controller.select('report_1');
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Open original PDF'));
      await tester.tap(find.text('Open original PDF'));
      await tester.pump();
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      response.complete(
        http.Response(
          '%PDF-synthetic',
          200,
          headers: {'content-type': 'application/pdf'},
        ),
      );
      await tester.pumpAndSettle();
      expect(files.renders, 0);
      expect(find.text('Close original PDF'), findsNothing);
      await tester.pumpWidget(const SizedBox());
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    },
  );

  testWidgets(
    'polling waits for a foreground screen and refreshes immediately on resume',
    (tester) async {
      var reads = 0;
      final controller = PatientReportsController(
        account: patient,
        token: () => 'token',
        platform: DeviceFiles(),
        api: PatientReportApi(
          Uri.parse('https://example.invalid'),
          MockClient((request) async {
            reads++;
            return http.Response(
              '{"schemaVersion":"1.0","items":[],"nextCursor":null}',
              200,
            );
          }),
        ),
      );
      addTearDown(controller.dispose);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: PatientReportsPanel(controller: controller)),
        ),
      );
      await tester.pumpAndSettle();
      final initial = reads;
      await tester.pump(const Duration(seconds: 31));
      expect(reads, initial);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(reads, initial + 1);
      await tester.pump(const Duration(seconds: 16));
      await tester.pumpAndSettle();
      expect(reads, initial + 2);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pump(const Duration(seconds: 31));
      expect(reads, initial + 2);
      await tester.pumpWidget(const SizedBox());
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    },
  );
  testWidgets(
    'patient screen distinguishes document rejection, doctor rejection and expiry',
    (tester) async {
      final rows = [
        {
          'id': 'document',
          'processing': 'rejected',
          'review': 'not_ready',
          'expiry': null,
        },
        {
          'id': 'review',
          'processing': 'succeeded',
          'review': 'rejected',
          'expiry': null,
        },
        {
          'id': 'expired',
          'processing': 'succeeded',
          'review': 'approved',
          'expiry': '2020-01-01T00:00:00Z',
        },
      ];
      final controller = PatientReportsController(
        account: patient,
        token: () => 'token',
        platform: DeviceFiles(),
        api: PatientReportApi(
          Uri.parse('https://example.invalid'),
          MockClient(
            (request) async => http.Response(
              jsonEncode({
                'schemaVersion': '1.0',
                'items': rows
                    .map(
                      (row) => {
                        'schemaVersion': '1.0',
                        'caseId': row['id'],
                        'reportId': row['id'],
                        'patientId': 'patient_a',
                        'assignedDoctorId': null,
                        'processingStatus': row['processing'],
                        'reviewStatus': row['review'],
                        'version': 1,
                        'reviewVersion': 0,
                        'createdAt': '2026-10-24T10:00:00Z',
                        'expiresAt': row['expiry'],
                      },
                    )
                    .toList(),
                'nextCursor': null,
              }),
              200,
            ),
          ),
        ),
      );
      addTearDown(controller.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: PatientReportsPanel(controller: controller)),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('PDF not accepted'), findsOneWidget);
      expect(find.text('Doctor did not approve'), findsOneWidget);
      expect(find.text('Expired'), findsOneWidget);
      expect(find.textContaining('draft'), findsNothing);
      await tester.pumpWidget(const SizedBox());
    },
  );
}
