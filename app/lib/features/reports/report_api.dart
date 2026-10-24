import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../../core/api/api_client.dart';
import '../../core/contracts/contracts.g.dart';

class _PdfRequest extends http.BaseRequest with http.Abortable {
  _PdfRequest(Uri url, this.bytes, this.progress, this.abortTrigger)
    : super('PUT', url);
  final Uint8List bytes;
  final void Function(double) progress;
  @override
  final Future<void>? abortTrigger;
  @override
  http.ByteStream finalize() {
    super.finalize();
    return http.ByteStream(_chunks());
  }

  Stream<List<int>> _chunks() async* {
    for (var offset = 0; offset < bytes.length; offset += 65536) {
      final end = (offset + 65536).clamp(0, bytes.length);
      yield Uint8List.sublistView(bytes, offset, end);
      progress(end / bytes.length);
    }
  }
}

class PatientReportApi {
  PatientReportApi(this.baseUrl, this.client);
  final Uri baseUrl;
  final http.Client client;
  final _inflight = <Completer<void>>{};
  bool _closed = false;

  Future<Uint8List> _send(
    String token,
    String method,
    String path, {
    Map<String, Object?>? body,
    String? key,
    Uint8List? pdf,
    void Function(double)? progress,
    int expected = 200,
    bool expectPdf = false,
    Duration timeout = const Duration(seconds: 45),
  }) async {
    if (_closed) throw const ApiFailure('This session has ended.');
    final maxBytes = expectPdf ? 10000000 : 1000000;
    final abort = Completer<void>();
    _inflight.add(abort);
    final uri = baseUrl.resolve(path);
    final http.BaseRequest request;
    if (pdf != null) {
      request = _PdfRequest(uri, pdf, progress ?? (_) {}, abort.future)
        ..contentLength = pdf.length;
    } else {
      request = http.AbortableRequest(method, uri, abortTrigger: abort.future);
      if (body != null) (request as http.Request).body = jsonEncode(body);
    }
    request.headers.addAll({
      'Authorization': 'Bearer $token',
      'Accept': expectPdf ? 'application/pdf' : 'application/json',
      if (body != null) 'Content-Type': 'application/json',
      if (pdf != null) 'Content-Type': 'application/pdf',
      if (key != null) 'Idempotency-Key': key,
    });
    try {
      return await (() async {
        final response = await client.send(request);
        if (response.contentLength != null &&
            response.contentLength! > maxBytes) {
          throw const ApiFailure('The response exceeds the permitted size.');
        }
        final bytes = BytesBuilder(copy: false);
        await for (final chunk in response.stream) {
          if (bytes.length + chunk.length > maxBytes) {
            throw const ApiFailure('The response exceeds the permitted size.');
          }
          bytes.add(chunk);
        }
        final payload = bytes.takeBytes();
        if (response.statusCode != expected) {
          throw _failure(response.statusCode);
        }
        if (expectPdf &&
            (response.headers['content-type']
                        ?.split(';')
                        .first
                        .trim()
                        .toLowerCase() !=
                    'application/pdf' ||
                payload.length < 5 ||
                ascii.decode(payload.sublist(0, 5), allowInvalid: true) !=
                    '%PDF-')) {
          payload.fillRange(0, payload.length, 0);
          throw const ApiFailure(
            'The original PDF could not be read safely. Refresh and try again.',
          );
        }
        return payload;
      })().timeout(timeout);
    } on ApiFailure {
      rethrow;
    } on TimeoutException {
      throw const ApiFailure(
        'The service is taking longer to respond. It may be starting. Retry shortly.',
        code: ErrorCode.temporarilyUnavailable,
        retryable: true,
      );
    } catch (_) {
      throw const ApiFailure(
        'Cannot reach the service. Check your connection and retry.',
        code: ErrorCode.temporarilyUnavailable,
        retryable: true,
      );
    } finally {
      if (!abort.isCompleted) abort.complete();
      _inflight.remove(abort);
    }
  }

  ApiFailure _failure(int status) => switch (status) {
    401 => const ApiFailure(
      'Your session ended. Sign in again.',
      code: ErrorCode.unauthenticated,
    ),
    403 => const ApiFailure(
      'This account cannot access this report.',
      code: ErrorCode.permissionDenied,
    ),
    410 => const ApiFailure(
      'This upload or report has expired.',
      code: ErrorCode.expired,
    ),
    413 => const ApiFailure(
      'Choose a PDF no larger than 10 MB (10,000,000 bytes).',
      code: ErrorCode.invalidUpload,
    ),
    422 => const ApiFailure(
      'The PDF was not accepted. Use a readable, unencrypted English laboratory PDF, up to 10 pages.',
      code: ErrorCode.invalidUpload,
    ),
    429 => const ApiFailure(
      'The upload limit has been reached. Try later; daily limits reset at midnight UTC.',
      code: ErrorCode.quotaExhausted,
    ),
    409 => const ApiFailure(
      'This upload is still being handled. Wait briefly and retry the same upload.',
      code: ErrorCode.conflict,
    ),
    500 || 502 || 503 || 504 => const ApiFailure(
      'The service is starting or temporarily unavailable. Retry shortly.',
      code: ErrorCode.temporarilyUnavailable,
      retryable: true,
    ),
    _ => const ApiFailure(
      'The request could not be completed. Refresh and retry.',
    ),
  };

  Map<String, dynamic> _json(Uint8List bytes) {
    try {
      return jsonDecode(utf8.decode(bytes)) as Map<String, dynamic>;
    } catch (_) {
      throw const ApiFailure('The service returned an unreadable response.');
    }
  }

  String _id(String value) {
    if (!RegExp(r'^[A-Za-z0-9_-]{1,128}$').hasMatch(value)) {
      throw const ApiFailure(
        'The service returned an invalid report reference.',
      );
    }
    return value;
  }

  Future<UploadSession> register(
    String token,
    String name,
    int count,
    String key,
  ) async {
    final result = UploadSession.fromJson(
      _json(
        await _send(
          token,
          'POST',
          '/api/v1/reports',
          body: {
            'fileName': name,
            'byteCount': count,
            'syntheticDataAcknowledged': true,
          },
          key: key,
          expected: 201,
        ),
      ),
    );
    if (result.uploadPath !=
        '/api/v1/reports/${_id(result.report.reportId)}/file') {
      throw const ApiFailure(
        'The service returned an invalid upload reference.',
      );
    }
    return result;
  }

  Future<void> upload(
    String token,
    String reportId,
    Uint8List bytes,
    void Function(double) progress,
  ) async {
    await _send(
      token,
      'PUT',
      '/api/v1/reports/${_id(reportId)}/file',
      pdf: bytes,
      progress: progress,
      expected: 204,
      timeout: const Duration(seconds: 90),
    );
  }

  Future<ProcessingJob> complete(String token, String id, String key) async =>
      ProcessingJob.fromJson(
        _json(
          await _send(
            token,
            'POST',
            '/api/v1/reports/${_id(id)}/complete-upload',
            body: {},
            key: key,
            expected: 202,
            timeout: const Duration(seconds: 270),
          ),
        ),
      );
  Future<ReportMetadata> report(String token, String id) async =>
      ReportMetadata.fromJson(
        _json(await _send(token, 'GET', '/api/v1/reports/${_id(id)}')),
      );
  Future<CasePage> cases(String token, {String? cursor}) async {
    final path = Uri(
      path: '/api/v1/cases',
      queryParameters: {'limit': '20', if (cursor != null) 'cursor': cursor},
    );
    return CasePage.fromJson(_json(await _send(token, 'GET', path.toString())));
  }

  Future<Uint8List> original(String token, String id) => _send(
    token,
    'GET',
    '/api/v1/reports/${_id(id)}/document',
    expectPdf: true,
    timeout: const Duration(seconds: 90),
  );

  Future<ReportResult> result(
    String token,
    ReportMetadata report, {
    required Role role,
    bool approved = false,
  }) async {
    if (role == Role.administrator) {
      throw const ApiFailure('This account cannot access laboratory results.');
    }
    final kind = role == Role.patient || approved
        ? ResultKind.approved
        : ResultKind.draft;
    try {
      final value = ReportResult.fromJson(
        _json(
          await _send(
            token,
            'GET',
            '/api/v1/reports/${_id(report.reportId)}/result?kind=${kind.value}',
          ),
        ),
      );
      if (value.schemaVersion != '1.0' ||
          value.kind != kind ||
          (kind == ResultKind.approved
              ? value.draft != null ||
                    value.approved == null ||
                    value.approved!.reportId != report.reportId ||
                    value.approved!.analysisId != report.approvedAnalysisId
              : value.approved != null ||
                    value.draft == null ||
                    value.draft!.reportId != report.reportId ||
                    value.draft!.analysisId != report.latestAnalysisId)) {
        throw const FormatException('Unexpected result identity');
      }
      return value;
    } on ApiFailure catch (error) {
      if (error.code == ErrorCode.conflict) {
        throw const ApiFailure(
          'This result is not available yet. Refresh to check again.',
          code: ErrorCode.conflict,
        );
      }
      rethrow;
    } catch (_) {
      throw const ApiFailure(
        'The result could not be read safely. Refresh and try again.',
      );
    }
  }

  Future<Map<String, dynamic>> workflowRequest(
    String token,
    String method,
    String path, {
    Map<String, Object?>? body,
    String? key,
    int expected = 200,
  }) async {
    try {
      return _json(
        await _send(
          token,
          method,
          path,
          body: body,
          key: key,
          expected: expected,
        ),
      );
    } on ApiFailure catch (error) {
      if (error.code == ErrorCode.conflict) {
        throw const ApiFailure(
          'The case changed. Refresh before continuing.',
          code: ErrorCode.conflict,
        );
      }
      if (error.code == ErrorCode.invalidUpload) {
        throw const ApiFailure(
          'Check the fields, source evidence and unresolved reasons. Every blocking issue needs a correction or an explicit unresolved reason.',
          code: ErrorCode.invalidRequest,
        );
      }
      if (error.code == ErrorCode.quotaExhausted) {
        throw const ApiFailure(
          'Reprocessing is limited to two requests per report per UTC day, at least one minute apart.',
          code: ErrorCode.quotaExhausted,
        );
      }
      rethrow;
    }
  }

  Future<DoctorPage> doctors(String token, {String? cursor}) async =>
      DoctorPage.fromJson(
        await workflowRequest(
          token,
          'GET',
          Uri(
            path: '/api/v1/doctors',
            queryParameters: {
              'limit': '20',
              if (cursor != null) 'cursor': cursor,
            },
          ).toString(),
        ),
      );

  Future<CaseSummary> assign(
    String token,
    CaseSummary item,
    String doctorId,
    String key,
  ) async => CaseSummary.fromJson(
    await workflowRequest(
      token,
      'POST',
      '/api/v1/cases/${_id(item.caseId)}/assignment',
      body: {'doctorId': _id(doctorId), 'expectedCaseVersion': item.version},
      key: key,
    ),
  );

  Future<CaseSummary> beginReview(
    String token,
    String id,
    BeginReviewRequest body,
    String key,
  ) async => CaseSummary.fromJson(
    await workflowRequest(
      token,
      'POST',
      '/api/v1/reports/${_id(id)}/begin-review',
      body: body.toJson(),
      key: key,
    ),
  );

  Future<ReviewRecord> review(
    String token,
    String id,
    ReviewRequest body,
    String key,
  ) async => ReviewRecord.fromJson(
    await workflowRequest(
      token,
      'POST',
      '/api/v1/reports/${_id(id)}/review',
      body: body.toJson(),
      key: key,
      expected: 201,
    ),
  );

  Future<ReviewPage> reviews(String token, String id, {String? cursor}) async =>
      ReviewPage.fromJson(
        await workflowRequest(
          token,
          'GET',
          Uri(
            path: '/api/v1/reports/${_id(id)}/reviews',
            queryParameters: {
              'limit': '20',
              if (cursor != null) 'cursor': cursor,
            },
          ).toString(),
        ),
      );

  Future<ProcessingJob> reprocess(
    String token,
    ReportMetadata report,
    String reason,
    String key,
  ) async => ProcessingJob.fromJson(
    await workflowRequest(
      token,
      'POST',
      '/api/v1/reports/${_id(report.reportId)}/reprocess',
      body: {
        'expectedLatestAnalysisId': report.latestAnalysisId,
        'reason': reason,
      },
      key: key,
      expected: 202,
    ),
  );

  void close() {
    _closed = true;
    for (final abort in _inflight) {
      if (!abort.isCompleted) abort.complete();
    }
    _inflight.clear();
    client.close();
  }
}
