package dev.automate.hub

import android.Manifest
import android.annotation.SuppressLint
import android.app.DownloadManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.text.InputType
import android.view.Menu
import android.view.MenuItem
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.preference.PreferenceManager
import java.io.File

/**
 * Minimal WebView wrapper around the bundled autoMate SPA.
 *
 * The SPA lives in app/src/main/assets/ (copied from automate/frontend/ at
 * build time). It loads via file:///android_asset/index.html, which means
 * the APK works offline. The JS inside the SPA reads `automate-hub-base`
 * from localStorage — that is where we put the user's hub URL after they
 * enter it on first launch, so XHR/WebSocket calls hit the user's laptop
 * (or relay) directly.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        webView = WebView(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.MATCH_PARENT
            )
        }
        setContentView(webView)

        with(webView.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            mediaPlaybackRequiresUserGesture = false
            allowFileAccess = true
            allowContentAccess = true
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            setSupportZoom(false)
            // v4.5.1: needed so target="_blank" fires onCreateWindow
            // instead of being silently dropped.
            javaScriptCanOpenWindowsAutomatically = true
            setSupportMultipleWindows(true)
        }
        webView.webChromeClient = object : WebChromeClient() {
            // v4.5.1: target="_blank" links route through onCreateWindow.
            // Without this, the link looks like a no-op to the user.
            override fun onCreateWindow(
                view: WebView, isDialog: Boolean, isUserGesture: Boolean,
                resultMsg: android.os.Message,
            ): Boolean {
                val href = view.hitTestResult.extra
                if (!href.isNullOrBlank()) {
                    try {
                        startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(href)))
                        return false
                    } catch (_: Throwable) {}
                }
                return false
            }

            // v4.5: forward MediaRecorder permission requests to Android.
            // The SPA's record button calls navigator.mediaDevices.getUserMedia
            // which routes through here when the page is loaded from
            // file:///android_asset.
            override fun onPermissionRequest(request: PermissionRequest) {
                runOnUiThread {
                    val wantsAudio = request.resources.any {
                        it == PermissionRequest.RESOURCE_AUDIO_CAPTURE
                    }
                    if (!wantsAudio) {
                        request.deny(); return@runOnUiThread
                    }
                    val granted = ContextCompat.checkSelfPermission(
                        this@MainActivity, Manifest.permission.RECORD_AUDIO
                    ) == PackageManager.PERMISSION_GRANTED
                    if (granted) {
                        request.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
                    } else {
                        pendingPermissionRequest = request
                        ActivityCompat.requestPermissions(
                            this@MainActivity,
                            arrayOf(Manifest.permission.RECORD_AUDIO),
                            REQ_RECORD_AUDIO,
                        )
                    }
                }
            }
        }

        // v4.4: when the SPA navigates to an .apk URL (the auto-update
        // path), download it and pop the system installer.
        webView.setDownloadListener { url, _, _, mimeType, _ ->
            if (url.endsWith(".apk", ignoreCase = true) ||
                mimeType == "application/vnd.android.package-archive") {
                downloadAndInstall(url)
            } else {
                // Fall back to opening the URL externally so we don't
                // accidentally swallow other downloads.
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
            }
        }

        loadShell()
    }

    // ---- v4.4: in-app APK update ----

    private var downloadId: Long = -1L

    private fun downloadAndInstall(url: String) {
        Toast.makeText(this, "Downloading update…", Toast.LENGTH_SHORT).show()
        val updatesDir = File(cacheDir, "updates").apply { mkdirs() }
        val target = File(updatesDir, "update-${System.currentTimeMillis()}.apk")
        val mgr = getSystemService(DOWNLOAD_SERVICE) as DownloadManager
        val request = DownloadManager.Request(Uri.parse(url))
            .setTitle("autoMate update")
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setDestinationUri(Uri.fromFile(target))
            .setMimeType("application/vnd.android.package-archive")
        downloadId = mgr.enqueue(request)
        registerReceiver(
            installOnComplete(target),
            IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE),
            Context.RECEIVER_EXPORTED,
        )
    }

    private fun installOnComplete(target: File) = object : BroadcastReceiver() {
        override fun onReceive(ctx: Context, intent: Intent) {
            val id = intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1L)
            if (id != downloadId) return
            try {
                ctx.unregisterReceiver(this)
            } catch (_: Throwable) {}
            launchInstaller(target)
        }
    }

    private fun launchInstaller(apk: File) {
        if (!apk.exists()) {
            Toast.makeText(this, "Download failed.", Toast.LENGTH_SHORT).show()
            return
        }
        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", apk)
        val install = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        try {
            startActivity(install)
        } catch (e: Throwable) {
            Toast.makeText(this, "Cannot launch installer: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    private fun loadShell() {
        // Just load the SPA. If there's a saved hub URL, inject it so the
        // SPA boots in connected mode. If there isn't, the SPA detects this
        // (via /api/health failing) and shows a yellow "Local mode" banner
        // with a hub-URL input — no forced prompt. Phone-only users with
        // notes + memory work fine without ever filling that in.
        val prefs = PreferenceManager.getDefaultSharedPreferences(this)
        val saved = prefs.getString(KEY_HUB, null)
        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView, url: String) {
                super.onPageFinished(view, url)
                if (!saved.isNullOrBlank()) injectHub(saved)
            }

            // v4.5.1: keep external links (Moonshot console, Anthropic
            // console, GitHub release pages, etc.) out of the WebView.
            // Default behaviour tried to load them in-place, which most
            // CSPs reject and ends with a blank or routed-back-home page —
            // the user reads it as "the button didn't work".
            override fun shouldOverrideUrlLoading(view: WebView, req: WebResourceRequest): Boolean {
                val target = req.url
                val scheme = target.scheme ?: return false
                if (scheme == "http" || scheme == "https" || scheme == "mailto" || scheme == "tel") {
                    val host = target.host ?: ""
                    // Stay in-WebView for the user's own hub URL.
                    if (!saved.isNullOrBlank() && saved.contains(host)) return false
                    try {
                        startActivity(Intent(Intent.ACTION_VIEW, target))
                        return true
                    } catch (_: Throwable) {
                        return false
                    }
                }
                return false
            }
        }
        webView.loadUrl("file:///android_asset/index.html")
    }

    private fun injectHub(url: String) {
        val safe = url.replace("'", "\\'").trimEnd('/')
        webView.evaluateJavascript(
            """
            try {
              localStorage.setItem('automate-hub-base', '$safe');
            } catch (e) {}
            """.trimIndent(),
            null
        )
    }

    private fun promptForHub() {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_TEXT_VARIATION_URI
            hint = "http://192.168.1.20:8765"
        }
        AlertDialog.Builder(this)
            .setTitle("Connect to your autoMate hub")
            .setMessage(
                "Enter the URL where automate is running on your laptop, " +
                "Docker host, or relay. (Same WiFi: use the laptop's LAN IP.)"
            )
            .setView(input)
            .setCancelable(false)
            .setPositiveButton("Connect") { _, _ ->
                val raw = input.text.toString().trim()
                if (raw.isEmpty()) {
                    promptForHub()
                    return@setPositiveButton
                }
                val url = if (raw.startsWith("http")) raw else "http://$raw"
                PreferenceManager.getDefaultSharedPreferences(this)
                    .edit().putString(KEY_HUB, url).apply()
                injectHub(url)
                webView.evaluateJavascript("location.reload();", null)
            }
            .show()
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.menu_main, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_change_hub -> { promptForHub(); true }
            R.id.action_reload -> { webView.reload(); true }
            else -> super.onOptionsItemSelected(item)
        }
    }

    @Deprecated("Deprecated in superclass")
    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }

    private var pendingPermissionRequest: PermissionRequest? = null

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQ_RECORD_AUDIO) {
            val req = pendingPermissionRequest ?: return
            pendingPermissionRequest = null
            val granted = grantResults.isNotEmpty() &&
                grantResults[0] == PackageManager.PERMISSION_GRANTED
            if (granted) {
                req.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
            } else {
                req.deny()
            }
        }
    }

    companion object {
        const val KEY_HUB = "hub_url"
        const val REQ_RECORD_AUDIO = 4501
    }
}
