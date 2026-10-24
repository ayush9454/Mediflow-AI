import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_client.dart';
import '../../core/contracts/contracts.g.dart';
import 'laboratory_result_view.dart';
import 'report_api.dart';
import 'report_platform.dart';
import 'report_screen.dart' show approvedSnapshotNotice;

class EvidenceResultScreen extends StatefulWidget {
  const EvidenceResultScreen({
    required this.account,
    required this.reportId,
    required this.api,
    required this.platform,
    required this.token,
    this.onSessionEnded,
    super.key,
  });
  final Account account;
  final String reportId;
  final PatientReportApi api;
  final ReportPlatform platform;
  final String Function() token;
  final VoidCallback? onSessionEnded;
  @override
  State<EvidenceResultScreen> createState() => _EvidenceResultScreenState();
}

class _EvidenceResultScreenState extends State<EvidenceResultScreen>
    with WidgetsBindingObserver {
  ReportMetadata? report;
  ReportResult? result;
  Uint8List? png;
  EvidenceReference? selected;
  String? message, evidenceMessage;
  bool loading = false, rendering = false, approved = false;
  int page = 1, generation = 0;
  final tabs = ValueNotifier(0);
  Timer? retention, poll;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_load());
  }

  bool get _foreground =>
      WidgetsBinding.instance.lifecycleState == null ||
      WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed;

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_load());
    } else {
      setState(() {
        _clear();
        message = 'Return to the app to reload this result securely.';
      });
    }
  }

  void _clearPage() {
    if (png != null) {
      PaintingBinding.instance.imageCache.evict(MemoryImage(png!));
      png!.fillRange(0, png!.length, 0);
      png = null;
    }
  }

  void _clear() {
    retention?.cancel();
    poll?.cancel();
    poll = null;
    generation++;
    _clearPage();
    result = null;
    report = null;
    selected = null;
    evidenceMessage = null;
    loading = false;
    rendering = false;
  }

  Future<void> _load({bool keepCurrent = false}) async {
    if (!_foreground) return;
    if (keepCurrent && !TickerMode.of(context)) return;
    if (keepCurrent && loading) return;
    if (!keepCurrent) _clear();
    final current = generation;
    setState(() {
      loading = true;
      message = null;
    });
    try {
      final metadata = await widget.api.report(widget.token(), widget.reportId);
      if (!mounted || current != generation || !_foreground) return;
      if (metadata.reportId != widget.reportId ||
          metadata.hospitalId != widget.account.hospitalId ||
          !widget.account.active ||
          (widget.account.role == Role.patient
              ? metadata.patientId != widget.account.uid
              : widget.account.role != Role.doctor ||
                    metadata.assignedDoctorId != widget.account.uid)) {
        throw const ApiFailure(
          'This account cannot access this report.',
          code: ErrorCode.permissionDenied,
        );
      }
      if (metadata.expiresAt?.isAfter(DateTime.now()) == false) {
        throw const ApiFailure(
          'This report has expired.',
          code: ErrorCode.expired,
        );
      }
      final value = await widget.api.result(
        widget.token(),
        metadata,
        role: widget.account.role,
        approved: approved,
      );
      if (!mounted || current != generation) return;
      setState(() {
        if (report != null &&
            (report!.caseVersion != metadata.caseVersion ||
                report!.reviewVersion != metadata.reviewVersion ||
                report!.latestAnalysisId != metadata.latestAnalysisId ||
                report!.approvedAnalysisId != metadata.approvedAnalysisId)) {
          _clear();
        }
        report = metadata;
        result = value;
        loading = false;
      });
      retention?.cancel();
      if (metadata.expiresAt != null) {
        retention = Timer(metadata.expiresAt!.difference(DateTime.now()), () {
          if (mounted) {
            setState(() {
              _clear();
              message = 'This report has expired.';
            });
          }
        });
      }
      poll ??= Timer.periodic(
        const Duration(seconds: 15),
        (_) => unawaited(_load(keepCurrent: true)),
      );
    } on ApiFailure catch (error) {
      if (!mounted || current != generation) return;
      _handleFailure(error);
    } catch (_) {
      if (mounted && current == generation) {
        setState(() {
          _clear();
          message =
              'The result could not be read safely. Refresh to try again.';
        });
      }
    } finally {
      if (mounted && current == generation) setState(() => loading = false);
    }
  }

  void _handleFailure(ApiFailure error) {
    setState(() {
      _clear();
      message = error.message;
    });
    if (error.code == ErrorCode.unauthenticated) {
      widget.onSessionEnded?.call();
    }
  }

  Future<void> _open(EvidenceReference evidence) async {
    if (rendering || loading) return;
    selected = evidence;
    tabs.value = 1;
    await _render(evidence.page);
  }

  Future<void> _render(int next) async {
    if (rendering || report == null) return;
    final current = generation;
    _clearPage();
    setState(() {
      rendering = true;
      evidenceMessage = null;
    });
    Uint8List? bytes;
    try {
      bytes = await widget.api.original(widget.token(), widget.reportId);
      if (!mounted || current != generation) return;
      final image = await widget.platform.render(bytes, next - 1);
      if (!mounted || current != generation) {
        image.png.fillRange(0, image.png.length, 0);
        return;
      }
      if (next < 1 ||
          next > image.pageCount ||
          image.pageCount != report!.pageCount) {
        image.png.fillRange(0, image.png.length, 0);
        throw const FormatException('Page bounds mismatch');
      }
      setState(() {
        png = image.png;
        page = next;
      });
    } on ApiFailure catch (error) {
      if (!mounted || current != generation) return;
      _handleFailure(error);
    } catch (_) {
      if (mounted && current == generation) {
        setState(
          () => evidenceMessage =
              'Unreadable or invalid source page. The evidence could not be displayed.',
        );
      }
    } finally {
      bytes?.fillRange(0, bytes.length, 0);
      if (mounted && current == generation) setState(() => rendering = false);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _clear();
    tabs.dispose();
    widget.api.close();
    super.dispose();
  }

  Widget _evidence() => Column(
    children: [
      if (selected != null)
        ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: 160),
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: SelectableText(
              'Supporting quotation · page ${selected!.page}\n${selected!.quotation}',
            ),
          ),
        ),
      if (rendering) const LinearProgressIndicator(),
      if (evidenceMessage != null)
        Padding(
          padding: const EdgeInsets.all(16),
          child: Text(evidenceMessage!),
        ),
      if (png == null && !rendering && evidenceMessage == null)
        const Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'Choose a laboratory row’s source page to inspect its evidence.',
          ),
        ),
      if (png != null) ...[
        Expanded(
          child: InteractiveViewer(
            key: ValueKey('$generation-$page'),
            minScale: 1,
            maxScale: 5,
            child: Center(child: Image.memory(png!, gaplessPlayback: false)),
          ),
        ),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [
            IconButton(
              tooltip: 'Previous source page',
              onPressed: rendering || page <= 1
                  ? null
                  : () => _render(page - 1),
              icon: const Icon(Icons.chevron_left),
            ),
            Text('Page $page of ${report!.pageCount}'),
            IconButton(
              tooltip: 'Next source page',
              onPressed: rendering || page >= report!.pageCount!
                  ? null
                  : () => _render(page + 1),
              icon: const Icon(Icons.chevron_right),
            ),
          ],
        ),
      ],
    ],
  );

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(
        widget.account.role == Role.patient
            ? 'Approved laboratory result'
            : 'Laboratory evidence',
      ),
      actions: [
        if (widget.account.role == Role.doctor && report != null)
          TextButton(
            onPressed: loading || rendering
                ? null
                : () => context.push('/review/${widget.reportId}').then((_) {
                    if (mounted) unawaited(_load());
                  }),
            child: const Text('Review'),
          ),
        IconButton(
          tooltip: 'Refresh result',
          onPressed: loading ? null : _load,
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    body: SafeArea(
      child: Column(
        children: [
          if (widget.account.role == Role.doctor)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: SegmentedButton<bool>(
                segments: const [
                  ButtonSegment(value: false, label: Text('AI candidate')),
                  ButtonSegment(value: true, label: Text('Approved snapshot')),
                ],
                selected: {approved},
                onSelectionChanged: (values) {
                  approved = values.single;
                  unawaited(_load());
                },
              ),
            ),
          if (loading) const LinearProgressIndicator(),
          if (message != null)
            Padding(padding: const EdgeInsets.all(20), child: Text(message!)),
          if (result?.approved != null &&
              report != null &&
              approvedSnapshotNotice(report!) != null)
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(approvedSnapshotNotice(report!)!),
            ),
          if (result != null)
            Expanded(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final rows = LaboratoryResultView(
                    result: result!,
                    pageCount: report!.pageCount,
                    onOpenEvidence: loading || rendering ? null : _open,
                  );
                  if (constraints.maxWidth >= 840) {
                    return Row(
                      children: [
                        Expanded(child: rows),
                        const VerticalDivider(width: 1),
                        Expanded(child: _evidence()),
                      ],
                    );
                  }
                  return ValueListenableBuilder<int>(
                    valueListenable: tabs,
                    builder: (context, index, _) => Column(
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: TextButton(
                                onPressed: () => tabs.value = 0,
                                child: Text(
                                  index == 0 ? 'Results •' : 'Results',
                                ),
                              ),
                            ),
                            Expanded(
                              child: TextButton(
                                onPressed: () => tabs.value = 1,
                                child: Text(
                                  index == 1 ? 'Source PDF •' : 'Source PDF',
                                ),
                              ),
                            ),
                          ],
                        ),
                        Expanded(child: index == 0 ? rows : _evidence()),
                      ],
                    ),
                  );
                },
              ),
            ),
        ],
      ),
    ),
  );
}
