import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_client.dart';
import '../../core/contracts/contracts.g.dart';
import '../reports/report_api.dart';

String operationKey() =>
    '${DateTime.now().microsecondsSinceEpoch}_${Random.secure().nextInt(1 << 32)}';

class DoctorReviewScreen extends StatefulWidget {
  const DoctorReviewScreen({
    required this.account,
    required this.reportId,
    required this.api,
    required this.token,
    this.onSessionEnded,
    super.key,
  });
  final Account account;
  final String reportId;
  final PatientReportApi api;
  final String Function() token;
  final VoidCallback? onSessionEnded;
  @override
  State<DoctorReviewScreen> createState() => _DoctorReviewScreenState();
}

class _DoctorReviewScreenState extends State<DoctorReviewScreen>
    with WidgetsBindingObserver {
  ReportMetadata? report;
  AnalysisCandidate? candidate;
  final history = <ReviewRecord>[];
  String? cursor, message;
  bool busy = false;
  int generation = 0;
  Timer? poll, retention;
  final editors = <String, _RowEditor>{};
  final unresolved = <String, TextEditingController>{};
  final comment = TextEditingController();
  Future<String> Function()? pending;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(load());
    poll = Timer.periodic(const Duration(seconds: 15), (_) => checkAccess());
  }

  bool get foreground =>
      mounted &&
      (WidgetsBinding.instance.lifecycleState == null ||
          WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed);

  void clear() {
    generation++;
    busy = false;
    retention?.cancel();
    report = null;
    candidate = null;
    history.clear();
    cursor = null;
    pending = null;
    for (final editor in editors.values) {
      editor.dispose();
    }
    editors.clear();
    for (final controller in unresolved.values) {
      controller.dispose();
    }
    unresolved.clear();
    comment.clear();
  }

  void failure(ApiFailure error) {
    if (!mounted) return;
    setState(() {
      if (error.code == ErrorCode.unauthenticated ||
          error.code == ErrorCode.permissionDenied ||
          error.code == ErrorCode.expired ||
          error.code == ErrorCode.conflict) {
        clear();
      }
      message = error.message;
    });
    if (error.code == ErrorCode.unauthenticated) widget.onSessionEnded?.call();
  }

  void validateMetadata(ReportMetadata value) {
    if (widget.account.role != Role.doctor ||
        !widget.account.active ||
        value.reportId != widget.reportId ||
        value.hospitalId != widget.account.hospitalId ||
        value.assignedDoctorId != widget.account.uid) {
      throw const ApiFailure(
        'This case is no longer assigned to this account.',
        code: ErrorCode.permissionDenied,
      );
    }
    if (value.expiresAt?.isAfter(DateTime.now()) == false) {
      throw const ApiFailure(
        'This report has expired.',
        code: ErrorCode.expired,
      );
    }
  }

  Future<void> checkAccess() async {
    if (!foreground || !TickerMode.of(context) || busy || report == null) {
      return;
    }
    final current = generation;
    try {
      final value = await widget.api.report(widget.token(), widget.reportId);
      if (!mounted || current != generation || !foreground) return;
      validateMetadata(value);
      if (value.caseVersion != report!.caseVersion ||
          value.reviewVersion != report!.reviewVersion ||
          value.latestAnalysisId != report!.latestAnalysisId ||
          value.processingStatus != report!.processingStatus) {
        throw const ApiFailure(
          'The case changed. Refresh before continuing.',
          code: ErrorCode.conflict,
        );
      }
    } on ApiFailure catch (error) {
      if (current == generation) failure(error);
    } catch (_) {
      if (current == generation) {
        failure(
          const ApiFailure(
            'Cannot verify this case. Refresh before continuing.',
            code: ErrorCode.conflict,
          ),
        );
      }
    }
  }

  Future<void> load({String? successMessage}) async {
    if (!foreground || busy) return;
    setState(() {
      clear();
      busy = true;
      message = successMessage;
    });
    final current = generation;
    try {
      final metadata = await widget.api.report(widget.token(), widget.reportId);
      validateMetadata(metadata);
      final records = await widget.api.reviews(widget.token(), widget.reportId);
      AnalysisCandidate? draft;
      if (metadata.latestAnalysisId != null &&
          metadata.processingStatus == ProcessingStatus.succeeded &&
          (metadata.reviewStatus == ReviewStatus.pending ||
              metadata.reviewStatus == ReviewStatus.underReview)) {
        draft = (await widget.api.result(
          widget.token(),
          metadata,
          role: Role.doctor,
        )).draft;
      }
      if (!mounted || current != generation || !foreground) return;
      setState(() {
        report = metadata;
        candidate = draft;
        history.addAll(records.items);
        cursor = records.nextCursor;
        for (final row in draft?.rows ?? <LaboratoryRow>[]) {
          editors[row.rowId] = _RowEditor(row);
        }
        for (final issue in [
          ...?draft?.issues,
          for (final row in draft?.rows ?? <LaboratoryRow>[]) ...row.issues,
        ]) {
          unresolved.putIfAbsent(issue.issueId, TextEditingController.new);
        }
      });
      if (metadata.expiresAt != null) {
        retention = Timer(
          metadata.expiresAt!.difference(DateTime.now()),
          () => failure(
            const ApiFailure(
              'This report has expired.',
              code: ErrorCode.expired,
            ),
          ),
        );
      }
    } on ApiFailure catch (error) {
      if (current == generation) failure(error);
    } catch (_) {
      if (current == generation) {
        failure(
          const ApiFailure(
            'The review could not be loaded safely. Refresh and retry.',
          ),
        );
      }
    } finally {
      if (mounted && current == generation) setState(() => busy = false);
    }
  }

  Future<void> submit(Future<String> Function() action) async {
    if (busy || !foreground) return;
    final current = generation;
    setState(() {
      busy = true;
      pending = action;
      message = null;
    });
    try {
      final text = await action();
      if (!mounted || current != generation || !foreground) return;
      pending = null;
      setState(() {
        clear();
        message = text;
      });
      await load(successMessage: text);
    } on ApiFailure catch (error) {
      if (current == generation) {
        if (!error.retryable) pending = null;
        failure(error);
      }
    } catch (_) {
      if (mounted && current == generation) {
        setState(
          () => message =
              'The response was interrupted. Retry the same operation to check its outcome.',
        );
      }
    } finally {
      if (mounted && current == generation) setState(() => busy = false);
    }
  }

  void begin() {
    final metadata = report!, draft = candidate!;
    final body = BeginReviewRequest(
      schemaVersion: '1.0',
      analysisId: draft.analysisId,
      expectedAnalysisVersion: draft.version,
      expectedCaseVersion: metadata.caseVersion,
      expectedReviewVersion: metadata.reviewVersion,
    );
    final key = operationKey();
    unawaited(
      submit(() async {
        await widget.api.beginReview(
          widget.token(),
          widget.reportId,
          body,
          key,
        );
        return 'Review started.';
      }),
    );
  }

  void decide(ReviewDecision decision) {
    try {
      final metadata = report!, draft = candidate!;
      if (decision == ReviewDecision.rejected && comment.text.trim().isEmpty) {
        setState(() => message = 'Enter a reason before rejecting.');
        return;
      }
      final corrections = decision == ReviewDecision.approved
          ? [
              for (final editor in editors.values)
                if (editor.changed) editor.correction(),
            ]
          : <RowCorrection>[];
      final acknowledgements = decision == ReviewDecision.approved
          ? [
              for (final item in unresolved.entries)
                if (item.value.text.trim().isNotEmpty)
                  UnresolvedAcknowledgement(
                    issueId: item.key,
                    reason: item.value.text.trim(),
                  ),
            ]
          : <UnresolvedAcknowledgement>[];
      final body = ReviewRequest(
        schemaVersion: '1.0',
        analysisId: draft.analysisId,
        expectedAnalysisVersion: draft.version,
        expectedCaseVersion: metadata.caseVersion,
        expectedReviewVersion: metadata.reviewVersion,
        decision: decision,
        corrections: corrections,
        unresolvedAcknowledgements: acknowledgements,
        comment: comment.text.trim().isEmpty ? null : comment.text.trim(),
      );
      final key = operationKey();
      unawaited(
        submit(() async {
          final record = await widget.api.review(
            widget.token(),
            widget.reportId,
            body,
            key,
          );
          return 'Decision recorded · ${record.request.decision.value} · review ${record.version} · ${record.reviewerId} · ${record.reviewedAt.toLocal()}';
        }),
      );
    } on FormatException catch (error) {
      setState(() => message = error.message);
    }
  }

  void reprocess() {
    if (comment.text.trim().isEmpty) {
      setState(() => message = 'Enter a reason for reprocessing.');
      return;
    }
    final metadata = report!,
        reason = comment.text.trim(),
        key = operationKey();
    unawaited(
      submit(() async {
        await widget.api.reprocess(widget.token(), metadata, reason, key);
        return 'Reprocessing requested. The previous approved snapshot stays visible until a replacement is approved.';
      }),
    );
  }

  Future<void> moreHistory() async {
    if (busy || cursor == null) return;
    final current = generation;
    setState(() => busy = true);
    try {
      final page = await widget.api.reviews(
        widget.token(),
        widget.reportId,
        cursor: cursor,
      );
      if (mounted && current == generation) {
        setState(() {
          history.addAll(page.items);
          cursor = page.nextCursor;
        });
      }
    } on ApiFailure catch (error) {
      if (current == generation) failure(error);
    } finally {
      if (mounted && current == generation) setState(() => busy = false);
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(load());
    } else {
      setState(() {
        clear();
        message = 'Return to reload this case securely.';
      });
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    poll?.cancel();
    clear();
    comment.dispose();
    widget.api.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final editable = !busy && pending == null;
    final draft = candidate;
    final canReview =
        report?.reviewStatus == ReviewStatus.underReview && draft != null;
    final qualified = unresolved.values.any(
      (item) => item.text.trim().isNotEmpty,
    );
    final corrected = editors.values.any((item) => item.changed);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Simulated doctor review'),
        actions: [
          IconButton(
            tooltip: 'Refresh review',
            onPressed: editable ? load : null,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Synthetic document review only. Compare every printed field with the original PDF.',
              ),
              if (busy) const LinearProgressIndicator(),
              if (message != null)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  child: Text(message!),
                ),
              if (pending != null && !busy)
                FilledButton(
                  onPressed: () => submit(pending!),
                  child: const Text('Retry same operation'),
                ),
              if (report != null) ...[
                Text(
                  'Review status: ${report!.reviewStatus.value.replaceAll('_', ' ')}',
                ),
                OutlinedButton(
                  onPressed: editable
                      ? () => context.push('/results/${widget.reportId}')
                      : null,
                  child: const Text('Open laboratory evidence'),
                ),
                if (draft != null) ...[
                  Text(
                    'Analysis ${draft.analysisId} · version ${draft.version}',
                  ),
                  if (report!.reviewStatus == ReviewStatus.pending)
                    FilledButton(
                      onPressed: editable ? begin : null,
                      child: const Text('Begin review'),
                    ),
                  if (canReview) ...[
                    for (final editor in editors.values)
                      editor.widget(editable, () => setState(() {})),
                    const SizedBox(height: 12),
                    const Text(
                      'Unresolved qualifications',
                      style: TextStyle(fontWeight: FontWeight.bold),
                    ),
                    const Text(
                      'Leave a reason only for issues you explicitly acknowledge as unresolved. Every blocking issue must be corrected or qualified.',
                    ),
                    for (final issue in [
                      ...draft.issues,
                      for (final row in draft.rows) ...row.issues,
                    ]) ...[
                      Text(
                        '${issue.severity.value} · ${issue.field}: ${issue.message}',
                      ),
                      TextField(
                        key: ValueKey('unresolved-${issue.issueId}'),
                        controller: unresolved[issue.issueId],
                        enabled: editable,
                        maxLength: 2000,
                        decoration: const InputDecoration(
                          labelText:
                              'Unresolved reason (optional if corrected)',
                        ),
                        onChanged: (_) => setState(() {}),
                      ),
                    ],
                  ],
                ],
                TextField(
                  controller: comment,
                  enabled: editable,
                  maxLength: 2000,
                  decoration: const InputDecoration(
                    labelText: 'Decision / reprocessing reason',
                  ),
                ),
                if (canReview) ...[
                  FilledButton(
                    onPressed: editable
                        ? () => decide(ReviewDecision.approved)
                        : null,
                    child: Text(
                      qualified
                          ? 'Approve with qualifications'
                          : corrected
                          ? 'Correct and approve'
                          : 'Approve',
                    ),
                  ),
                  OutlinedButton(
                    onPressed: editable
                        ? () => decide(ReviewDecision.rejected)
                        : null,
                    child: const Text('Reject analysis'),
                  ),
                ],
                if ({
                  ProcessingStatus.succeeded,
                  ProcessingStatus.failed,
                  ProcessingStatus.rejected,
                }.contains(report!.processingStatus))
                  OutlinedButton(
                    onPressed: editable ? reprocess : null,
                    child: const Text('Request reprocessing'),
                  ),
                const Divider(),
                const Text(
                  'Immutable review history',
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
                for (final record in history)
                  ExpansionTile(
                    title: Text(
                      '${record.request.decision.value}${record.request.corrections.isNotEmpty ? ' · corrected' : ''}${record.request.unresolvedAcknowledgements.isNotEmpty ? ' · qualified' : ''} · review ${record.version}',
                    ),
                    subtitle: Text(
                      '${record.reviewerId} · ${record.reviewedAt.toLocal()}',
                    ),
                    children: [
                      Text(
                        'Analysis ${record.request.analysisId} · version ${record.request.expectedAnalysisVersion}',
                      ),
                      if (record.request.comment != null)
                        Text(record.request.comment!),
                      for (final original in record.originalRows)
                        SelectableText(
                          'Original AI row ${original.rowId}: ${original.analyte} · ${original.result} · ${original.unit ?? 'No unit'} · ${original.referenceRange ?? 'No range'}\n${original.evidence.map((item) => 'Page ${item.page}: ${item.quotation}').join('\n')}',
                        ),
                      for (final change in record.request.corrections)
                        Text(
                          '${change.rowId}: ${change.reason}\nCorrected: ${change.correctedRow.analyte} · ${change.correctedRow.result} · ${change.correctedRow.unit ?? 'No unit'} · ${change.correctedRow.referenceRange ?? 'No range'}\n${change.correctedRow.evidence.map((item) => 'Page ${item.page}: ${item.quotation}').join('\n')}',
                        ),
                      for (final item
                          in record.request.unresolvedAcknowledgements)
                        Text('Unresolved · ${item.issueId}: ${item.reason}'),
                    ],
                  ),
                if (cursor != null)
                  TextButton(
                    onPressed: editable ? moreHistory : null,
                    child: const Text('Load more reviews'),
                  ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _RowEditor {
  _RowEditor(this.original) {
    final json = original.toJson();
    for (final field in fields) {
      values[field] = TextEditingController(text: json[field] as String? ?? '');
    }
    values['reason'] = TextEditingController();
    for (final item in original.evidence) {
      evidence.add(_EvidenceEditor(item));
    }
    if (evidence.isEmpty) evidence.add(_EvidenceEditor(null));
  }
  final LaboratoryRow original;
  static const fields = [
    'analyte',
    'result',
    'unit',
    'referenceRange',
    'abnormalityFlag',
    'collectionDate',
  ];
  final values = <String, TextEditingController>{};
  final evidence = <_EvidenceEditor>[];
  bool enabled = false;
  bool get changed => enabled;
  RowCorrection correction() {
    if (values['reason']!.text.trim().isEmpty ||
        values['analyte']!.text.trim().isEmpty ||
        values['result']!.text.trim().isEmpty) {
      throw const FormatException(
        'Each correction needs analyte, result, source quotation and a reason.',
      );
    }
    return RowCorrection(
      rowId: original.rowId,
      reason: values['reason']!.text.trim(),
      correctedRow: LaboratoryRow.fromJson({
        ...original.toJson(),
        for (final field in fields)
          field: values[field]!.text.trim().isEmpty
              ? null
              : values[field]!.text.trim(),
        'evidence': [for (final item in evidence) item.reference().toJson()],
      }),
    );
  }

  Widget widget(bool editable, VoidCallback changed) => ExpansionTile(
    maintainState: true,
    title: Text(original.analyte),
    subtitle: Text('Original AI result: ${original.result}'),
    children: [
      SwitchListTile(
        title: const Text('Correct this row'),
        value: enabled,
        onChanged: editable
            ? (value) {
                enabled = value;
                changed();
              }
            : null,
      ),
      if (enabled) ...[
        for (final field in fields)
          TextField(
            key: ValueKey('${original.rowId}-$field'),
            controller: values[field],
            enabled: editable,
            maxLength: 5000,
            decoration: InputDecoration(labelText: field),
          ),
        for (var index = 0; index < evidence.length; index++)
          evidence[index].widget(editable, changed, index),
        if (evidence.length < 10)
          TextButton(
            onPressed: editable
                ? () {
                    evidence.add(_EvidenceEditor(null));
                    changed();
                  }
                : null,
            child: const Text('Add source reference'),
          ),
        TextField(
          controller: values['reason'],
          enabled: editable,
          maxLength: 2000,
          decoration: const InputDecoration(labelText: 'Correction reason'),
        ),
      ],
    ],
  );
  void dispose() {
    for (final item in values.values) {
      item.dispose();
    }
    for (final item in evidence) {
      item.dispose();
    }
  }
}

class _EvidenceEditor {
  _EvidenceEditor(EvidenceReference? original)
    : page = TextEditingController(text: '${original?.page ?? 1}'),
      quotation = TextEditingController(text: original?.quotation ?? ''),
      origin = original?.extractionMethod ?? ExtractionMethod.native;
  final TextEditingController page, quotation;
  ExtractionMethod origin;
  EvidenceReference reference() {
    final number = int.tryParse(page.text);
    if (number == null ||
        number < 1 ||
        number > 10 ||
        quotation.text.trim().isEmpty) {
      throw const FormatException(
        'Each source reference needs a page between 1 and 10 and a quotation.',
      );
    }
    return EvidenceReference(
      page: number,
      quotation: quotation.text.trim(),
      extractionMethod: origin,
    );
  }

  Widget widget(bool editable, VoidCallback changed, int index) => Column(
    children: [
      TextField(
        controller: page,
        enabled: editable,
        keyboardType: TextInputType.number,
        decoration: InputDecoration(
          labelText: index == 0 ? 'Source page' : 'Source page ${index + 1}',
        ),
      ),
      TextField(
        controller: quotation,
        enabled: editable,
        maxLength: 5000,
        decoration: InputDecoration(
          labelText: index == 0
              ? 'Source quotation'
              : 'Source quotation ${index + 1}',
        ),
      ),
      DropdownButton<ExtractionMethod>(
        value: origin,
        items: [
          for (final item in ExtractionMethod.values)
            DropdownMenuItem(value: item, child: Text(item.value)),
        ],
        onChanged: editable
            ? (value) {
                if (value != null) origin = value;
                changed();
              }
            : null,
      ),
    ],
  );
  void dispose() {
    page.dispose();
    quotation.dispose();
  }
}
