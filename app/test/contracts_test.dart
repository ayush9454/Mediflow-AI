import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mediflow_ai/core/contracts/contracts.g.dart';

Map<String, Object?> fixture(String name) =>
    (jsonDecode(File('../contracts/examples/$name.json').readAsStringSync())
            as Map)
        .cast<String, Object?>();

void main() {
  test(
    'backend account and report fixtures preserve identity and independent statuses',
    () {
      final account = Account.fromJson(fixture('account'));
      final report = ReportMetadata.fromJson(fixture('report'));
      expect(account.role, Role.patient);
      expect(report.processingStatus, ProcessingStatus.queued);
      expect(report.reviewStatus, ReviewStatus.notReady);
      expect(report.assignedDoctorId, isNull);
      expect(report.caseVersion, 1);
      expect(report.reviewVersion, 0);
      expect(report.expiresAt!.isUtc, isTrue);
      expect(account.toJson(), fixture('account'));
    },
  );

  test('printed strings and evidence survive the Python to Dart boundary', () {
    final analysis = AnalysisCandidate.fromJson(fixture('analysis'));
    final row = analysis.rows.single;
    expect(row.result, '<0.50');
    expect(row.unit, 'SYN-U');
    expect(row.referenceRange, '0.00–1.00');
    expect(row.evidence.single.page, 1);
    expect(row.evidence.single.extractionMethod, ExtractionMethod.native);
    expect(analysis.createdAt.isUtc, isTrue);
    final roundTrip = AnalysisCandidate.fromJson(analysis.toJson());
    expect(roundTrip.rows.single.result, row.result);
    expect(roundTrip.createdAt, analysis.createdAt);
  });

  test('approved result payload is separate from the AI draft', () {
    final result = ReportResult.fromJson(fixture('approved-result'));
    expect(result.kind, ResultKind.approved);
    expect(result.draft, isNull);
    expect(result.approved!.reviewerId, 'doctor_1');
    expect(result.approved!.analysisVersion, 1);
  });

  test('review uses explicit optimistic concurrency version', () {
    final review = ReviewRequest.fromJson(fixture('review'));
    expect(review.expectedAnalysisVersion, 1);
    expect(review.expectedCaseVersion, 1);
    expect(review.expectedReviewVersion, 0);
    expect(review.decision, ReviewDecision.approved);
    expect(review.toJson(), fixture('review'));
  });

  test(
    'unknown role or wrong printed-value type fails rather than being guessed',
    () {
      expect(() => Role.fromJson('superuser'), throwsFormatException);
      final payload = fixture('analysis');
      final rows = payload['rows'] as List;
      final row = rows.first as Map;
      row['result'] = 0.5;
      expect(
        () => AnalysisCandidate.fromJson(payload),
        throwsA(isA<TypeError>()),
      );
    },
  );
}
