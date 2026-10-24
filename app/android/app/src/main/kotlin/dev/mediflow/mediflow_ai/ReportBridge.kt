package dev.mediflow.mediflow_ai

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import android.provider.OpenableColumns
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodChannel
import java.io.ByteArrayOutputStream
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.Executors
import kotlin.math.min
import kotlin.math.sqrt

/** User-selected PDF bytes and small recovery metadata; no shared-storage permission. */
class ReportBridge(private val activity: Activity, messenger: BinaryMessenger) {
    private val channel = MethodChannel(messenger, "dev.mediflow/reports")
    private val preferences = activity.getSharedPreferences("report-recovery", Context.MODE_PRIVATE)
    private val work = Executors.newSingleThreadExecutor()
    private var picker: MethodChannel.Result? = null
    private var closed = false
    private val maxBytes = 10_000_000

    init {
        clearPdfFiles()
        channel.setMethodCallHandler { call, result ->
            try {
                val owner = call.argument<String>("owner")
                when (call.method) {
                    "pickPdf" -> {
                        if (picker != null) { result.error("busy", "Choose one PDF at a time.", null) }
                        else {
                            picker = result
                            activity.startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                                addCategory(Intent.CATEGORY_OPENABLE)
                                type = "application/pdf"
                                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                            }, 9109)
                        }
                    }
                    "loadRecovery" -> {
                        require(owner != null && owner.length <= 300)
                        if (preferences.getString("owner", null) != owner) {
                            check(preferences.edit().clear().commit())
                        }
                        result.success(preferences.getString("value", null))
                    }
                    "saveRecovery" -> {
                        val value = call.argument<String>("value")!!
                        require(owner != null && owner.length <= 300 && value.length <= 8192)
                        check(preferences.edit().putString("owner", owner).putString("value", value).commit())
                        result.success(null)
                    }
                    "clearRecovery" -> {
                        if (preferences.getString("owner", null) == owner) {
                            check(preferences.edit().clear().commit())
                        }
                        clearPdfFiles()
                        result.success(null)
                    }
                    "renderPdf" -> {
                        val bytes = call.argument<ByteArray>("bytes")!!
                        val page = call.argument<Int>("page")!!
                        require(bytes.size in 1..maxBytes && page in 0..9)
                        work.execute {
                            var file: File? = null
                            try {
                                file = File.createTempFile("mediflow-pdf-", ".pdf", activity.cacheDir)
                                file.writeBytes(bytes)
                                ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use { descriptor ->
                                    PdfRenderer(descriptor).use { renderer ->
                                        require(renderer.pageCount in 1..10 && page < renderer.pageCount)
                                        val pageCount = renderer.pageCount
                                        renderer.openPage(page).use { source ->
                                            val scale = min(2.0, sqrt(1_500_000.0 / (source.width.toDouble() * source.height)))
                                            val bitmap = Bitmap.createBitmap((source.width*scale).toInt().coerceAtLeast(1),
                                                (source.height*scale).toInt().coerceAtLeast(1), Bitmap.Config.ARGB_8888)
                                            try {
                                                bitmap.eraseColor(Color.WHITE)
                                                source.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                                                val output = ByteArrayOutputStream()
                                                bitmap.compress(Bitmap.CompressFormat.PNG, 100, output)
                                                val png = output.toByteArray()
                                                activity.runOnUiThread {
                                                    if (!closed) result.success(mapOf("png" to png, "pageCount" to pageCount))
                                                    png.fill(0)
                                                }
                                            } finally { bitmap.recycle() }
                                        }
                                    }
                                }
                            } catch (_: Exception) { activity.runOnUiThread { if (!closed) result.error("unreadable", "This PDF cannot be displayed.", null) } }
                            finally { bytes.fill(0); file?.delete() }
                        }
                    }
                    else -> result.notImplemented()
                }
            } catch (_: Exception) {
                if (call.method == "pickPdf") picker = null
                result.error("unavailable", "Document access is unavailable.", null)
            }
        }
    }

    fun activityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode != 9109) return
        val result = picker ?: return
        picker = null
        val uri = data?.data
        if (resultCode != Activity.RESULT_OK || uri == null) { result.success(null); return }
        work.execute {
            try {
                var name = "report.pdf"
                activity.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { cursor ->
                    if (cursor.moveToFirst()) {
                        name = cursor.getString(0)?.substringAfterLast('/')?.take(255) ?: name
                        if (!cursor.isNull(1)) require(cursor.getLong(1) in 1..maxBytes.toLong())
                    }
                }
                val output = ByteArrayOutputStream()
                activity.contentResolver.openInputStream(uri)!!.use { input ->
                    val buffer = ByteArray(65536)
                    while (true) {
                        val size = input.read(buffer)
                        if (size < 0) break
                        require(output.size() + size <= maxBytes)
                        output.write(buffer, 0, size)
                    }
                }
                val bytes = output.toByteArray()
                val hash = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
                activity.runOnUiThread {
                    if (!closed) result.success(mapOf("name" to name, "bytes" to bytes, "sha256" to hash))
                    bytes.fill(0)
                }
            } catch (_: Exception) { activity.runOnUiThread { if (!closed) result.error("invalid_pdf", "Choose a readable PDF up to 10 MB.", null) } }
        }
    }
    private fun clearPdfFiles() { activity.cacheDir.listFiles()?.filter { it.name.startsWith("mediflow-pdf-") }?.forEach { it.delete() } }
    fun close() { closed = true; picker = null; channel.setMethodCallHandler(null); work.shutdown() }
}
