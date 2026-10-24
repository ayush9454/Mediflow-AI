import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';

class PickedPdf {
  PickedPdf(this.name, Uint8List source, this.sha256)
    : bytes = Uint8List.fromList(source);
  final String name;
  final Uint8List bytes;
  final String sha256;
}

class PdfPageImage {
  PdfPageImage(Uint8List source, this.pageCount)
    : png = Uint8List.fromList(source);
  final Uint8List png;
  final int pageCount;
}

abstract interface class ReportPlatform {
  Future<PickedPdf?> pickPdf();
  Future<String?> load(String owner);
  Future<void> save(String owner, String value);
  Future<void> clear(String owner);
  Future<PdfPageImage> render(Uint8List source, int page);
}

class AndroidReportPlatform implements ReportPlatform {
  static const channel = MethodChannel('dev.mediflow/reports');
  @override
  Future<PickedPdf?> pickPdf() async {
    try {
      final value = await channel.invokeMapMethod<String, dynamic>('pickPdf');
      if (value == null) return null;
      return PickedPdf(
        value['name'] as String,
        value['bytes'] as Uint8List,
        value['sha256'] as String,
      );
    } catch (_) {
      throw const ApiFailure(
        'The PDF could not be read. Choose a readable PDF up to 10 MB.',
      );
    }
  }

  @override
  Future<String?> load(String owner) =>
      channel.invokeMethod<String>('loadRecovery', {'owner': owner});
  @override
  Future<void> save(String owner, String value) async {
    await channel.invokeMethod<void>('saveRecovery', {
      'owner': owner,
      'value': value,
    });
  }

  @override
  Future<void> clear(String owner) =>
      channel.invokeMethod<void>('clearRecovery', {'owner': owner});
  @override
  Future<PdfPageImage> render(Uint8List source, int page) async {
    final value = await channel.invokeMapMethod<String, dynamic>('renderPdf', {
      'bytes': source,
      'page': page,
    });
    return PdfPageImage(value!['png'] as Uint8List, value['pageCount'] as int);
  }
}
