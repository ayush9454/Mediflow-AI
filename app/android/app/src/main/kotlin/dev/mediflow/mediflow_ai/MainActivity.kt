package dev.mediflow.mediflow_ai

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import android.content.Intent

class MainActivity : FlutterActivity() {
    private var reports: ReportBridge? = null
    override fun configureFlutterEngine(engine: FlutterEngine) {
        super.configureFlutterEngine(engine)
        reports = ReportBridge(this, engine.dartExecutor.binaryMessenger)
    }
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        reports?.activityResult(requestCode, resultCode, data)
    }
    override fun onDestroy() { reports?.close(); super.onDestroy() }
}
