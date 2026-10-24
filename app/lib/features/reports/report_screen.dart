import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import '../../core/api/api_client.dart';
import '../../core/config/app_config.dart';
import '../../core/contracts/contracts.g.dart';
import '../auth/session.dart';
import 'report_api.dart';
import 'report_controller.dart';
import 'report_platform.dart';

final reportHttpClientFactoryProvider = Provider<http.Client Function()>(
  (ref) => http.Client.new,
);
final reportPlatformProvider = Provider<ReportPlatform>(
  (ref) => AndroidReportPlatform(),
);

String workflowLabel(
  ProcessingStatus processing,
  ReviewStatus review,
  String? assigned,
  DateTime? expires,
) {
  if (expires != null && !expires.isAfter(DateTime.now())) return 'Expired';
  if (processing == ProcessingStatus.rejected) return 'PDF not accepted';
  if (processing == ProcessingStatus.failed) {
    return 'Processing could not finish';
  }
  if (processing == ProcessingStatus.uploadPending) return 'Upload incomplete';
  if (processing == ProcessingStatus.validating) return 'Checking PDF';
  if (processing == ProcessingStatus.queued) return 'Waiting to process';
  if (processing == ProcessingStatus.processing) return 'Processing PDF';
  if (review == ReviewStatus.rejected) return 'Doctor did not approve';
  if (review == ReviewStatus.approved) return 'Approved by doctor';
  if (review == ReviewStatus.underReview) return 'Doctor review in progress';
  return assigned == null
      ? 'Awaiting doctor assignment'
      : 'Awaiting doctor review';
}

class PatientReportsHost extends ConsumerStatefulWidget {
  const PatientReportsHost({
    required this.account,
    this.history = false,
    super.key,
  });
  final Account account;
  final bool history;
  @override
  ConsumerState<PatientReportsHost> createState() => _PatientReportsHostState();
}

class _PatientReportsHostState extends ConsumerState<PatientReportsHost> {
  late final PatientReportsController controller;
  @override
  void initState() {
    super.initState();
    controller = PatientReportsController(
      account: widget.account,
      onSessionEnded: () => ref.read(sessionProvider.notifier).expire(),
      platform: ref.read(reportPlatformProvider),
      api: PatientReportApi(
        ref.read(appConfigProvider).apiBaseUrl ??
            Uri.parse('https://unconfigured.invalid'),
        ref.read(reportHttpClientFactoryProvider)(),
      ),
      token: () {
        final session = ref.read(sessionProvider);
        if (session.account?.uid != widget.account.uid ||
            session.account?.hospitalId != widget.account.hospitalId ||
            session.token == null ||
            !session.token!.expiresAt.isAfter(DateTime.now())) {
          throw const ApiFailure(
            'Your session ended. Sign in again.',
            code: ErrorCode.unauthenticated,
          );
        }
        return session.token!.value;
      },
    );
  }

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) =>
      PatientReportsPanel(controller: controller, history: widget.history);
}

class PatientReportsPanel extends StatefulWidget {
  const PatientReportsPanel({
    required this.controller,
    this.history = false,
    super.key,
  });
  final PatientReportsController controller;
  final bool history;
  @override
  State<PatientReportsPanel> createState() => _PatientReportsPanelState();
}

class _PatientReportsPanelState extends State<PatientReportsPanel>
    with WidgetsBindingObserver {
  late final void Function() unsubscribe;
  Timer? poll;
  Uint8List? source, png;
  int page = 0, pageCount = 0;
  bool rendering = false;
  String? shownReport;
  PatientReportsController get controller => widget.controller;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unsubscribe = controller.addListener((state) {
      if (shownReport != state.selected?.reportId) {
        _clearPdf();
        shownReport = state.selected?.reportId;
      }
      if (mounted) setState(() {});
    }, fireImmediately: false);
    unawaited(controller.initialize());
    _startPolling();
  }

  void _startPolling() {
    poll?.cancel();
    final lifecycle = WidgetsBinding.instance.lifecycleState;
    if (lifecycle != null && lifecycle != AppLifecycleState.resumed) return;
    poll = Timer.periodic(const Duration(seconds: 15), (_) {
      if (source != null &&
          controller.snapshot.selected?.expiresAt?.isAfter(DateTime.now()) ==
              false) {
        _clearPdf();
      }
      unawaited(controller.refresh());
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState value) {
    poll?.cancel();
    if (value == AppLifecycleState.resumed) {
      _startPolling();
      unawaited(controller.refresh());
    } else {
      _clearPdf();
      if (mounted) setState(() {});
    }
  }

  void _clearPdf() {
    if (png != null) {
      PaintingBinding.instance.imageCache.clear();
      PaintingBinding.instance.imageCache.clearLiveImages();
    }
    png?.fillRange(0, png!.length, 0);
    source?.fillRange(0, source!.length, 0);
    png = null;
    source = null;
    page = 0;
    pageCount = 0;
  }

  @override
  void dispose() {
    poll?.cancel();
    unsubscribe();
    WidgetsBinding.instance.removeObserver(this);
    _clearPdf();
    super.dispose();
  }

  Future<void> _openPdf() async {
    final bytes = await controller.loadOriginal();
    if (!mounted) {
      bytes?.fillRange(0, bytes.length, 0);
      return;
    }
    if (bytes != null) {
      source = bytes;
      await _render(0);
    }
  }

  Future<void> _render(int next) async {
    if (source == null || rendering) return;
    setState(() => rendering = true);
    final document = source;
    try {
      final result = await controller.platform.render(document!, next);
      if (!mounted || source != document) {
        result.png.fillRange(0, result.png.length, 0);
        return;
      }
      png?.fillRange(0, png!.length, 0);
      setState(() {
        png = result.png;
        page = next;
        pageCount = result.pageCount;
      });
    } catch (_) {
      if (mounted) {
        _clearPdf();
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'This PDF cannot be displayed. Try opening it again.',
            ),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => rendering = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = controller.snapshot, report = controller.snapshot.selected;
    return RefreshIndicator(
      onRefresh: () => controller.refresh(),
      child: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text(
            widget.history ? 'Report history' : 'Your laboratory reports',
            style: Theme.of(context).textTheme.headlineMedium,
          ),
          const SizedBox(height: 8),
          const Text(
            'Synthetic demonstration · Track processing and doctor review.',
          ),
          if (state.busy) ...[
            const SizedBox(height: 16),
            LinearProgressIndicator(
              value: state.phase == ReportPhase.uploading
                  ? state.progress
                  : null,
            ),
            const SizedBox(height: 8),
            Text(switch (state.phase) {
              ReportPhase.selecting => 'Reading your selected PDF…',
              ReportPhase.registering => 'Starting a secure upload…',
              ReportPhase.uploading =>
                'Sending PDF · ${(state.progress * 100).round()}%',
              ReportPhase.verifying =>
                'Checking the PDF and starting processing…',
              ReportPhase.opening => 'Opening your original PDF securely…',
              _ => 'Connecting… The hosted service may be waking up.',
            }),
          ],
          if (state.message != null) ...[
            const SizedBox(height: 16),
            Semantics(liveRegion: true, child: Text(state.message!)),
            const SizedBox(height: 8),
            TextButton(
              onPressed: state.busy ? null : () => controller.refresh(),
              child: const Text('Refresh status'),
            ),
          ],
          const SizedBox(height: 20),
          if (report != null) ...[
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: state.busy ? null : controller.back,
                icon: const Icon(Icons.arrow_back),
                label: const Text('All reports'),
              ),
            ),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      report.fileName,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 12),
                    Text(
                      workflowLabel(
                        report.processingStatus,
                        report.reviewStatus,
                        report.assignedDoctorId,
                        report.expiresAt,
                      ),
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      'Processing continues on the server after this app is closed. A doctor must approve the result before it is shared.',
                    ),
                    if (report.processingStatus == ProcessingStatus.rejected)
                      const Padding(
                        padding: EdgeInsets.only(top: 12),
                        child: Text(
                          'The document could not be accepted. Check its format, readability and page count.',
                        ),
                      ),
                    if (report.reviewStatus == ReviewStatus.rejected)
                      const Padding(
                        padding: EdgeInsets.only(top: 12),
                        child: Text(
                          'The doctor did not approve this analysis. Contact your hospital for the next step.',
                        ),
                      ),
                    if (report.approvedAnalysisId != null &&
                        (report.processingStatus ==
                                ProcessingStatus.processing ||
                            report.processingStatus == ProcessingStatus.queued))
                      const Text(
                        'A new version is processing. Your previous approval remains recorded.',
                      ),
                    const SizedBox(height: 16),
                    FilledButton.tonalIcon(
                      onPressed:
                          state.busy ||
                              report.expiresAt?.isAfter(DateTime.now()) ==
                                  false ||
                              {
                                ProcessingStatus.uploadPending,
                                ProcessingStatus.validating,
                                ProcessingStatus.rejected,
                              }.contains(report.processingStatus)
                          ? null
                          : _openPdf,
                      icon: const Icon(Icons.description_outlined),
                      label: const Text('Open original PDF'),
                    ),
                  ],
                ),
              ),
            ),
            if (source != null) ...[
              const SizedBox(height: 12),
              TextButton(
                onPressed: () {
                  setState(_clearPdf);
                },
                child: const Text('Close original PDF'),
              ),
              if (rendering) const Center(child: CircularProgressIndicator()),
              if (png != null)
                InteractiveViewer(
                  minScale: 1,
                  maxScale: 4,
                  child: Image.memory(png!, gaplessPlayback: false),
                ),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  IconButton(
                    onPressed: rendering || page <= 0
                        ? null
                        : () => _render(page - 1),
                    icon: const Icon(Icons.chevron_left),
                    tooltip: 'Previous page',
                  ),
                  Text('Page ${page + 1} of $pageCount'),
                  IconButton(
                    onPressed: rendering || page + 1 >= pageCount
                        ? null
                        : () => _render(page + 1),
                    icon: const Icon(Icons.chevron_right),
                    tooltip: 'Next page',
                  ),
                ],
              ),
            ],
          ] else ...[
            if (!widget.history)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Text(
                        'English laboratory PDFs · up to 10 pages and 10 MB (10,000,000 bytes). Password-protected, corrupt or unsupported documents are not accepted.',
                      ),
                      CheckboxListTile(
                        contentPadding: EdgeInsets.zero,
                        value: state.acknowledged,
                        onChanged: state.busy
                            ? null
                            : (value) => controller.acknowledge(value ?? false),
                        title: const Text(
                          'This PDF contains only invented patient data.',
                        ),
                      ),
                      FilledButton.icon(
                        onPressed: state.busy
                            ? null
                            : state.pending == null
                            ? controller.pickAndUpload
                            : controller.retryUpload,
                        icon: const Icon(Icons.upload_file),
                        label: Text(
                          state.pending == null
                              ? 'Select and upload PDF'
                              : 'Continue interrupted upload',
                        ),
                      ),
                      if (state.pending != null)
                        TextButton(
                          onPressed: state.busy ? null : controller.discard,
                          child: const Text('Start a different upload'),
                        ),
                    ],
                  ),
                ),
              ),
            const SizedBox(height: 16),
            if (state.cases.isEmpty && !state.busy)
              const Text(
                'No reports yet. Your saved reports will appear here after upload.',
              ),
            for (final item in state.cases.where(
              (item) =>
                  !widget.history ||
                  {
                    ProcessingStatus.succeeded,
                    ProcessingStatus.rejected,
                    ProcessingStatus.failed,
                  }.contains(item.processingStatus),
            ))
              Card(
                child: ListTile(
                  leading: const Icon(Icons.description_outlined),
                  title: Text(
                    workflowLabel(
                      item.processingStatus,
                      item.reviewStatus,
                      item.assignedDoctorId,
                      item.expiresAt,
                    ),
                  ),
                  subtitle: Text(
                    'Submitted ${item.createdAt.toLocal().toString().substring(0, 16)}',
                  ),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: state.busy
                      ? null
                      : () => controller.select(item.reportId),
                ),
              ),
            if (state.nextCursor != null)
              TextButton(
                onPressed: state.busy
                    ? null
                    : () => controller.refresh(more: true),
                child: const Text('Load more reports'),
              ),
          ],
          const SizedBox(height: 30),
        ],
      ),
    );
  }
}
