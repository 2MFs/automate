package dev.automate.hub

import android.annotation.SuppressLint
import android.os.Bundle
import android.text.InputType
import android.view.Menu
import android.view.MenuItem
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.LinearLayout
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.preference.PreferenceManager

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
        }
        webView.webViewClient = WebViewClient()
        webView.webChromeClient = WebChromeClient()

        loadShell()
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

    companion object {
        const val KEY_HUB = "hub_url"
    }
}
