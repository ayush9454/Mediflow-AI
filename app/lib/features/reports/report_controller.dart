import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'dart:typed_data';

import '../../core/api/api_client.dart';
import '../../core/contracts/contracts.g.dart';
import 'report_api.dart';
import 'report_platform.dart';

class PendingUpload {
  const PendingUpload({
    required this.name,
    required this.byteCount,
    required this.sha256,
    required this.registrationKey,
    required this.completionKey,
    this.reportId,
    this.verifying = false,
  });
  final String name, sha256, registrationKey, completionKey;
  final int byteCount;
  final String? reportId;
  final bool verifying;
  PendingUpload registered(String id, {bool? verifying}) => PendingUpload(
    name: name,
    byteCount: byteCount,
    sha256: sha256,
    registrationKey: registrationKey,
    completionKey: completionKey,
    reportId: id,
    verifying: verifying ?? this.verifying,
  );
  String encode() => jsonEncode({
    'name': name,
    'byteCount': byteCount,
    'sha256': sha256,
    'registrationKey': registrationKey,
    'completionKey': completionKey,
    'reportId': reportId,
    'verifying': verifying,
  });
  factory PendingUpload.decode(String value) {
    final j = jsonDecode(value) as Map<String, dynamic>;
    return PendingUpload(
      name: j['name'] as String,
      byteCount: j['byteCount'] as int,
      sha256: j['sha256'] as String,
      registrationKey: j['registrationKey'] as String,
      completionKey: j['completionKey'] as String,
      reportId: j['reportId'] as String?,
      verifying: j['verifying'] as bool,
    );
  }
}

enum ReportPhase {
  idle,
  selecting,
  registering,
  uploading,
  verifying,
  refreshing,
  opening,
}

class PatientReportState {
  const PatientReportState({
    this.cases = const [],
    this.nextCursor,
    this.selected,
    this.pending,
    this.phase = ReportPhase.idle,
    this.progress = 0,
    this.message,
    this.acknowledged = false,
  });
  final List<CaseSummary> cases;
  final String? nextCursor;
  final ReportMetadata? selected;
  final PendingUpload? pending;
  final ReportPhase phase;
  final double progress;
  final String? message;
  final bool acknowledged;
  bool get busy => phase != ReportPhase.idle;
  PatientReportState copy({
    List<CaseSummary>? cases,
    String? nextCursor,
    ReportMetadata? selected,
    PendingUpload? pending,
    ReportPhase? phase,
    double? progress,
    String? message,
    bool? acknowledged,
    bool clearSelected = false,
    bool clearPending = false,
    bool clearMessage = false,
    bool clearCursor = false,
  }) => PatientReportState(
    cases: cases ?? this.cases,
    nextCursor: clearCursor ? null : nextCursor ?? this.nextCursor,
    selected: clearSelected ? null : selected ?? this.selected,
    pending: clearPending ? null : pending ?? this.pending,
    phase: phase ?? this.phase,
    progress: progress ?? this.progress,
    message: clearMessage ? null : message ?? this.message,
    acknowledged: acknowledged ?? this.acknowledged,
  );
}

class PatientReportsController extends StateNotifier<PatientReportState> {
  PatientReportsController({
    required this.account,
    required this.token,
    required this.platform,
    required this.api,
    this.view = CaseView.all,
    this.onSessionEnded,
  }) : super(const PatientReportState());
  final Account account;
  final String Function() token;
  final ReportPlatform platform;
  final PatientReportApi api;
  final CaseView view;
  final void Function()? onSessionEnded;
  PatientReportState get snapshot => state;
  PickedPdf? _file;
  String get owner => '${account.hospitalId}/${account.uid}';
  void _active() {
    if (!mounted) throw const ApiFailure('This session ended.');
  }

  String get _token {
    _active();
    return token();
  }

  void acknowledge(bool value) {
    if (!state.busy) state = state.copy(acknowledged: value);
  }

  bool _accepted(ReportMetadata value) =>
      value.processingStatus != ProcessingStatus.uploadPending &&
      value.processingStatus != ProcessingStatus.validating;
  ReportMetadata _owned(ReportMetadata value) {
    if (value.patientId != account.uid ||
        value.hospitalId != account.hospitalId) {
      throw const ApiFailure('The report does not belong to this account.');
    }
    return value;
  }

  Future<void> initialize() async {
    state = state.copy(phase: ReportPhase.refreshing);
    try {
      final stored = await platform.load(owner);
      _active();
      if (stored != null) {
        final pending = PendingUpload.decode(stored);
        state = state.copy(
          pending: pending,
          message: 'An upload was interrupted. Continue it using the same PDF.',
        );
        if (pending.reportId != null) {
          ReportMetadata report;
          try {
            report = _owned(await api.report(_token, pending.reportId!));
          } on ApiFailure catch (error) {
            if (error.code != ErrorCode.permissionDenied ||
                !pending.verifying) {
              rethrow;
            }
            // Duplicate completion can retire a provisional report. Replay the
            // persisted completion key to recover its canonical server ID.
            final job = await _retry(
              () => api.complete(
                _token,
                pending.reportId!,
                pending.completionKey,
              ),
            );
            await _save(pending.registered(job.reportId, verifying: true));
            report = _owned(await api.report(_token, job.reportId));
          }
          _active();
          if (_accepted(report)) await _finish(report);
        }
      }
    } catch (error) {
      _failed(error);
    }
    if (mounted) {
      state = state.copy(phase: ReportPhase.idle);
      await refresh();
    }
  }

  String _message(Object error) => error is ApiFailure
      ? error.message
      : 'The operation could not finish. Refresh or retry.';

  void _failed(Object error) {
    if (!mounted) return;
    final denied =
        error is ApiFailure &&
        (error.code == ErrorCode.unauthenticated ||
            error.code == ErrorCode.permissionDenied);
    if (denied) _wipeFile();
    state = state.copy(
      phase: ReportPhase.idle,
      message: _message(error),
      clearSelected: denied,
      cases: denied ? const [] : null,
      clearCursor: denied,
    );
    if (error is ApiFailure && error.code == ErrorCode.unauthenticated) {
      onSessionEnded?.call();
    }
  }

  Future<T> _retry<T>(Future<T> Function() operation) async {
    for (var attempt = 0; ; attempt++) {
      _active();
      try {
        return await operation();
      } on ApiFailure catch (error) {
        if (!error.retryable || attempt >= 1) rethrow;
        await Future<void>.delayed(const Duration(milliseconds: 300));
      }
    }
  }

  Future<void> _save(PendingUpload pending) async {
    _active();
    await platform.save(owner, pending.encode());
    _active();
    state = state.copy(pending: pending);
  }

  Future<void> _finish(ReportMetadata report) async {
    _active();
    await platform.clear(owner);
    _active();
    _wipeFile();
    state = state.copy(
      selected: report,
      clearPending: true,
      acknowledged: false,
      phase: ReportPhase.idle,
      message:
          'Your report is saved. Processing continues when this app is closed.',
    );
  }

  Future<void> pickAndUpload() async {
    if (state.busy) return;
    if (!state.acknowledged) {
      state = state.copy(
        message: 'Confirm that this PDF contains only invented patient data.',
      );
      return;
    }
    state = state.copy(phase: ReportPhase.selecting, clearMessage: true);
    try {
      final file = await platform.pickPdf();
      if (!mounted) {
        file?.bytes.fillRange(0, file.bytes.length, 0);
        return;
      }
      if (file == null) {
        state = state.copy(phase: ReportPhase.idle);
        return;
      }
      if (file.bytes.isEmpty ||
          file.bytes.length > 10000000 ||
          !file.name.toLowerCase().endsWith('.pdf') ||
          file.bytes.length < 5 ||
          ascii.decode(file.bytes.sublist(0, 5), allowInvalid: true) !=
              '%PDF-') {
        file.bytes.fillRange(0, file.bytes.length, 0);
        throw const ApiFailure(
          'Choose an English laboratory PDF up to 10 MB and 10 pages.',
        );
      }
      final prior = state.pending;
      if (prior != null &&
          (prior.sha256 != file.sha256 ||
              prior.byteCount != file.bytes.length)) {
        file.bytes.fillRange(0, file.bytes.length, 0);
        throw const ApiFailure(
          'Choose the same PDF to continue this upload, or discard the interrupted upload.',
        );
      }
      _wipeFile();
      _file = file;
      final random = Random.secure();
      String key() => List.generate(
        16,
        (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
      ).join();
      final pending =
          prior ??
          PendingUpload(
            name: file.name,
            byteCount: file.bytes.length,
            sha256: file.sha256,
            registrationKey: key(),
            completionKey: key(),
          );
      await _save(pending);
      await _upload();
    } catch (error) {
      _failed(error);
    }
  }

  Future<void> retryUpload() async {
    if (state.busy || state.pending == null) return;
    if (_file == null && !state.pending!.verifying) {
      await pickAndUpload();
      return;
    }
    try {
      await _upload();
    } catch (error) {
      _failed(error);
    }
  }

  Future<void> _upload() async {
    var pending = state.pending!;
    if (pending.reportId == null) {
      state = state.copy(phase: ReportPhase.registering, clearMessage: true);
      final session = await _retry(
        () => api.register(
          _token,
          pending.name,
          pending.byteCount,
          pending.registrationKey,
        ),
      );
      _active();
      _owned(session.report);
      pending = pending.registered(session.report.reportId);
      await _save(pending);
      if (_accepted(session.report)) {
        await _finish(session.report);
        return;
      }
    }
    if (!pending.verifying) {
      if (_file == null) {
        throw const ApiFailure('Select the same PDF to continue.');
      }
      state = state.copy(
        phase: ReportPhase.uploading,
        progress: 0,
        clearMessage: true,
      );
      await _retry(
        () => api.upload(_token, pending.reportId!, _file!.bytes, (progress) {
          if (mounted) state = state.copy(progress: progress);
        }),
      );
      _active();
      pending = pending.registered(pending.reportId!, verifying: true);
      await _save(pending);
    }
    state = state.copy(phase: ReportPhase.verifying);
    final job = await _retry(
      () => api.complete(_token, pending.reportId!, pending.completionKey),
    );
    _active();
    await _save(pending.registered(job.reportId, verifying: true));
    final report = _owned(await api.report(_token, job.reportId));
    _active();
    await _finish(report);
    await refresh();
  }

  Future<void> refresh({bool more = false}) async {
    if (state.busy) return;
    state = state.copy(phase: ReportPhase.refreshing, clearMessage: true);
    try {
      final page = await api.cases(
        _token,
        cursor: more ? state.nextCursor : null,
        view: view,
      );
      _active();
      if (page.items.any((item) => item.patientId != account.uid)) {
        throw const ApiFailure('Refresh the case list.');
      }
      final selected = state.selected;
      final detail = selected == null
          ? null
          : _owned(await api.report(_token, selected.reportId));
      _active();
      state = state.copy(
        cases: List.unmodifiable(
          more ? [...state.cases, ...page.items] : page.items,
        ),
        nextCursor: page.nextCursor,
        clearCursor: page.nextCursor == null,
        selected: detail,
        phase: ReportPhase.idle,
      );
    } catch (error) {
      _failed(error);
    }
  }

  Future<void> select(String id) async {
    if (state.busy) return;
    state = state.copy(
      phase: ReportPhase.refreshing,
      clearSelected: true,
      clearMessage: true,
    );
    try {
      final report = _owned(await api.report(_token, id));
      _active();
      state = state.copy(selected: report, phase: ReportPhase.idle);
    } catch (error) {
      _failed(error);
    }
  }

  void back() {
    if (!state.busy) {
      state = state.copy(clearSelected: true, clearMessage: true);
    }
  }

  Future<void> discard() async {
    if (state.busy) return;
    try {
      await platform.clear(owner);
      _active();
      _wipeFile();
      state = state.copy(
        clearPending: true,
        clearMessage: true,
        acknowledged: false,
      );
    } catch (error) {
      _failed(error);
    }
  }

  Future<Uint8List?> loadOriginal() async {
    final report = state.selected;
    if (report == null || state.busy) return null;
    state = state.copy(phase: ReportPhase.opening, clearMessage: true);
    try {
      final bytes = await api.original(_token, report.reportId);
      if (!mounted) {
        bytes.fillRange(0, bytes.length, 0);
        return null;
      }
      state = state.copy(phase: ReportPhase.idle);
      return bytes;
    } catch (error) {
      _failed(error);
      return null;
    }
  }

  void _wipeFile() {
    _file?.bytes.fillRange(0, _file!.bytes.length, 0);
    _file = null;
  }

  @override
  void dispose() {
    _wipeFile();
    api.close();
    super.dispose();
  }
}
