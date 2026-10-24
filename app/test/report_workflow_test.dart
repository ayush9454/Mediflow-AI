import 'dart:convert';
import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mediflow_ai/features/reports/report_api.dart';
import 'package:mediflow_ai/features/reports/report_platform.dart';
import 'package:mediflow_ai/features/reports/report_controller.dart';
import 'package:mediflow_ai/core/contracts/contracts.g.dart';

Map<String, Object?> metadata({
  String id = 'report_1',
  String status = 'queued',
}) => {
  'schemaVersion': '1.0',
  'reportId': id,
  'caseId': 'case_1',
  'caseVersion': 1,
  'reviewVersion': 0,
  'patientId': 'patient_a',
  'hospitalId': 'hospital_1',
  'fileName': 'synthetic.pdf',
  'processingStatus': status,
  'reviewStatus': 'not_ready',
  'assignedDoctorId': null,
  'latestAnalysisId': null,
  'approvedAnalysisId': null,
  'pageCount': null,
  'createdAt': '2026-10-24T10:00:00Z',
  'expiresAt': null,
};

final patient = Account.fromJson({
  'schemaVersion': '1.0',
  'uid': 'patient_a',
  'hospitalId': 'hospital_1',
  'displayName': 'Synthetic Patient',
  'role': 'patient',
  'active': true,
});

class DeviceFiles implements ReportPlatform {
  String? journal;
  String? owner;
  @override
  Future<PickedPdf?> pickPdf() async => PickedPdf(
    'synthetic.pdf',
    Uint8List.fromList(utf8.encode('%PDF-synthetic')).asUnmodifiableView(),
    'a' * 64,
  );
  @override
  Future<String?> load(String scope) async => owner == scope ? journal : null;
  @override
  Future<void> save(String scope, String value) async {
    owner = scope;
    journal = value;
  }

  @override
  Future<void> clear(String scope) async {
    if (owner == scope) journal = null;
  }

  @override
  Future<PdfPageImage> render(Uint8List source, int page) async =>
      throw UnimplementedError();
}

class DeferredPicker extends DeviceFiles {
  final selection = Completer<PickedPdf?>();
  @override
  Future<PickedPdf?> pickPdf() => selection.future;
}

void main() {
  test(
    'restart resolves a retired duplicate report through its original completion key',
    () async {
      final device = DeviceFiles();
      await device.save(
        'hospital_1/patient_a',
        const PendingUpload(
          name: 'synthetic.pdf',
          byteCount: 14,
          sha256: 'digest',
          registrationKey: 'registration',
          completionKey: 'completion',
          reportId: 'provisional',
          verifying: true,
        ).encode(),
      );
      var completions = 0;
      final controller = PatientReportsController(
        account: patient,
        token: () => 'token',
        platform: device,
        api: PatientReportApi(
          Uri.parse('https://example.invalid'),
          MockClient((request) async {
            if (request.url.path == '/api/v1/reports/provisional') {
              return http.Response('', 403);
            }
            if (request.url.path.endsWith('complete-upload')) {
              completions++;
              expect(request.headers['Idempotency-Key'], 'completion');
              return http.Response(
                jsonEncode({
                  'schemaVersion': '1.0',
                  'jobId': 'job_1',
                  'reportId': 'canonical',
                  'status': 'queued',
                  'attemptCount': 0,
                  'maximumAttempts': 3,
                  'failureCode': null,
                  'createdAt': '2026-10-24T10:00:00Z',
                  'updatedAt': '2026-10-24T10:00:00Z',
                }),
                202,
              );
            }
            if (request.url.path == '/api/v1/cases') {
              return http.Response('{"items":[],"nextCursor":null}', 200);
            }
            return http.Response(jsonEncode(metadata(id: 'canonical')), 200);
          }),
        ),
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      expect(controller.state.selected?.reportId, 'canonical');
      expect(controller.state.pending, isNull);
      expect(completions, 1);
    },
  );

  test(
    'server session expiry clears the open report and asks for sign-in',
    () async {
      var expired = false, ended = 0;
      final controller = PatientReportsController(
        account: patient,
        token: () => 'token',
        platform: DeviceFiles(),
        onSessionEnded: () => ended++,
        api: PatientReportApi(
          Uri.parse('https://example.invalid'),
          MockClient((request) async {
            if (expired) return http.Response('PRIVATE TOKEN ERROR', 401);
            return http.Response(
              jsonEncode(metadata(status: 'succeeded')),
              200,
            );
          }),
        ),
      );
      addTearDown(controller.dispose);
      await controller.select('report_1');
      expect(controller.state.selected, isNotNull);
      expired = true;
      await controller.refresh();
      expect(controller.state.selected, isNull);
      expect(ended, 1);
      expect(controller.state.message, contains('Sign in again'));
    },
  );
  test(
    'a late file-picker response after account closure is wiped and never uploaded',
    () async {
      final device = DeferredPicker();
      var requests = 0;
      final controller = PatientReportsController(
        account: patient,
        token: () => 'token',
        platform: device,
        api: PatientReportApi(
          Uri.parse('https://example.invalid'),
          MockClient((request) async {
            requests++;
            return http.Response('', 500);
          }),
        ),
      );
      controller.acknowledge(true);
      final operation = controller.pickAndUpload();
      controller.dispose();
      final picked = PickedPdf(
        'synthetic.pdf',
        Uint8List.fromList(
          utf8.encode('%PDF-private-selected-data'),
        ).asUnmodifiableView(),
        'a' * 64,
      );
      final bytes = picked.bytes;
      device.selection.complete(picked);
      await operation;
      expect(requests, 0);
      expect(bytes, everyElement(0));
    },
  );
  test(
    'original PDF access rejects JSON or oversized responses without exposing bytes',
    () async {
      final api = PatientReportApi(
        Uri.parse('https://example.invalid'),
        MockClient(
          (request) async => http.Response(
            'PRIVATE-DRAFT',
            200,
            headers: {'content-type': 'application/json'},
          ),
        ),
      );
      addTearDown(api.close);
      await expectLater(
        api.original('token', 'report_1'),
        throwsA(isA<Exception>()),
      );
    },
  );
  test('pagination survives local acknowledgement changes', () async {
    final cursors = <String?>[];
    final controller = PatientReportsController(
      account: patient,
      token: () => 'token',
      platform: DeviceFiles(),
      api: PatientReportApi(
        Uri.parse('https://example.invalid'),
        MockClient((request) async {
          cursors.add(request.url.queryParameters['cursor']);
          return http.Response(
            jsonEncode({
              'schemaVersion': '1.0',
              'items': [],
              'nextCursor': cursors.length == 1 ? 'next_page' : null,
            }),
            200,
          );
        }),
      ),
    );
    addTearDown(controller.dispose);
    await controller.initialize();
    controller.acknowledge(true);
    expect(controller.state.nextCursor, 'next_page');
    await controller.refresh(more: true);
    expect(cursors, [null, 'next_page']);
    expect(controller.state.nextCursor, isNull);
  });
  test(
    'a lost registration response retries with the already persisted key',
    () async {
      final device = DeviceFiles();
      final keys = <String>[];
      final api = PatientReportApi(
        Uri.parse('https://example.invalid'),
        MockClient((request) async {
          if (request.url.path == '/api/v1/reports') {
            keys.add(request.headers['Idempotency-Key']!);
            if (keys.length == 1) {
              throw http.ClientException('lost registration');
            }
            return http.Response(
              jsonEncode({
                'schemaVersion': '1.0',
                'report': metadata(status: 'upload_pending'),
                'uploadPath': '/api/v1/reports/report_1/file',
                'expiresAt': '2027-01-01T10:00:00Z',
              }),
              201,
            );
          }
          if (request.method == 'PUT') return http.Response('', 204);
          if (request.url.path.endsWith('complete-upload')) {
            return http.Response(
              jsonEncode({
                'schemaVersion': '1.0',
                'jobId': 'job_1',
                'reportId': 'report_1',
                'status': 'queued',
                'attemptCount': 0,
                'maximumAttempts': 3,
                'failureCode': null,
                'createdAt': '2026-10-24T10:00:00Z',
                'updatedAt': '2026-10-24T10:00:00Z',
              }),
              202,
            );
          }
          if (request.url.path == '/api/v1/cases') {
            return http.Response(
              '{"schemaVersion":"1.0","items":[],"nextCursor":null}',
              200,
            );
          }
          return http.Response(jsonEncode(metadata()), 200);
        }),
      );
      final controller = PatientReportsController(
        account: patient,
        token: () => 'token',
        platform: device,
        api: api,
      );
      addTearDown(controller.dispose);
      controller.acknowledge(true);
      await controller.pickAndUpload();
      expect(keys.length, 2);
      expect(keys[0], keys[1]);
      expect(controller.state.selected?.reportId, 'report_1');
      expect(controller.state.pending, isNull);
    },
  );
  test(
    'quota errors stop automatic retries and never reveal a raw server payload',
    () async {
      var requests = 0;
      final controller = PatientReportsController(
        account: patient,
        token: () => 'token',
        platform: DeviceFiles(),
        api: PatientReportApi(
          Uri.parse('https://example.invalid'),
          MockClient((request) async {
            requests++;
            return http.Response('PRIVATE-RAW-KEY-AND-DRAFT', 429);
          }),
        ),
      );
      addTearDown(controller.dispose);
      controller.acknowledge(true);
      await controller.pickAndUpload();
      expect(requests, 1);
      expect(controller.state.message, contains('limit'));
      expect(controller.state.message, isNot(contains('PRIVATE')));
    },
  );
  test(
    'restart after lost completion restores the same server case without another upload',
    () async {
      final device = DeviceFiles();
      var registrations = 0, uploads = 0, completions = 0;
      var accepted = false;
      Future<http.Response> respond(http.Request request) async {
        if (request.url.path == '/api/v1/reports' && request.method == 'POST') {
          registrations++;
          expect(device.journal, isNotNull);
          return http.Response(
            jsonEncode({
              'schemaVersion': '1.0',
              'report': metadata(status: 'upload_pending'),
              'uploadPath': '/api/v1/reports/report_1/file',
              'expiresAt': '2027-01-01T10:00:00Z',
            }),
            201,
          );
        }
        if (request.method == 'PUT') {
          uploads++;
          return http.Response('', 204);
        }
        if (request.url.path.endsWith('complete-upload')) {
          completions++;
          accepted = true;
          throw http.ClientException('connection lost after commit');
        }
        if (request.url.path == '/api/v1/cases') {
          return http.Response(
            '{"schemaVersion":"1.0","items":[],"nextCursor":null}',
            200,
          );
        }
        return http.Response(
          jsonEncode(metadata(status: accepted ? 'queued' : 'upload_pending')),
          200,
        );
      }

      PatientReportsController create() => PatientReportsController(
        account: patient,
        token: () => 'identity-token',
        platform: device,
        api: PatientReportApi(
          Uri.parse('https://example.invalid'),
          MockClient(respond),
        ),
      );
      final first = create();
      await first.initialize();
      first.acknowledge(true);
      await first.pickAndUpload();
      expect(first.state.pending?.reportId, 'report_1');
      expect(completions, 2);
      expect(device.journal, isNot(contains('identity-token')));
      expect(device.journal, isNot(contains('%PDF')));
      first.dispose();
      final reopened = create();
      addTearDown(reopened.dispose);
      await reopened.initialize();
      expect(reopened.state.selected?.reportId, 'report_1');
      expect(reopened.state.pending, isNull);
      expect(registrations, 1);
      expect(uploads, 1);
      expect(completions, 2);
    },
  );
  test(
    'upload uses server IDs, protected relative paths and stable operation keys',
    () async {
      final requests = <http.Request>[];
      final api = PatientReportApi(
        Uri.parse('https://example.invalid'),
        MockClient((request) async {
          requests.add(request);
          expect(request.headers['Authorization'], 'Bearer identity-token');
          if (request.url.path == '/api/v1/reports') {
            return http.Response(
              jsonEncode({
                'schemaVersion': '1.0',
                'report': metadata(status: 'upload_pending'),
                'uploadPath': '/api/v1/reports/report_1/file',
                'expiresAt': '2026-10-24T11:00:00Z',
              }),
              201,
            );
          }
          return http.Response('', 204);
        }),
      );
      addTearDown(api.close);
      final session = await api.register(
        'identity-token',
        'synthetic.pdf',
        5,
        'operation_1',
      );
      final progress = <double>[];
      await api.upload(
        'identity-token',
        session.report.reportId,
        Uint8List.fromList([37, 80, 68, 70, 45]),
        progress.add,
      );
      expect(requests[0].headers['Idempotency-Key'], 'operation_1');
      expect(requests[1].url.path, '/api/v1/reports/report_1/file');
      expect(requests[1].headers['Content-Type'], 'application/pdf');
      expect(progress.last, 1);
    },
  );
}
