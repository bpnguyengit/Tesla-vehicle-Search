package com.teslasearch.vehicle

import android.app.Activity
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject
import java.util.UUID
import kotlinx.coroutines.CancellableContinuation
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Loads the public inventory page once in the system WebView, then performs
 * inventory GETs with fetch() so TLS, cookies, and headers come from Chromium.
 * WebView methods run on the main thread; the network read itself does not.
 */
class TeslaWebFetcher(private val activity: Activity) {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val gate = Mutex()
    private val bridgeLock = Any()
    private val transfers = HashMap<String, Transfer>()
    private val bridge = Bridge()

    private var webView: WebView? = null
    private var pageState = PageState.IDLE
    private var pageDeferred: CompletableDeferred<Unit>? = null

    @Volatile
    private var destroyed = false

    suspend fun fetch(url: String): Pair<Int, String> {
        if (destroyed || activity.isDestroyed) {
            throw InventoryException("Inventory browser is closed.")
        }
        return gate.withLock {
            ensurePage()
            doFetch(url)
        }
    }

    fun destroy() {
        val task = Runnable { destroyOnMain() }
        if (Looper.myLooper() == Looper.getMainLooper()) task.run() else mainHandler.post(task)
    }

    private fun destroyOnMain() {
        if (destroyed) return
        destroyed = true
        val pending = synchronized(bridgeLock) {
            val copy = transfers.values.toList()
            transfers.clear()
            copy
        }
        for (transfer in pending) {
            if (transfer.continuation.isActive) transfer.continuation.cancel()
        }
        val view = webView ?: return
        webView = null
        view.stopLoading()
        view.removeJavascriptInterface(BRIDGE_NAME)
        (view.parent as? ViewGroup)?.removeView(view)
        view.destroy()
    }

    private suspend fun ensurePage() {
        val waitFor = withContext(Dispatchers.Main) {
            if (destroyed || activity.isDestroyed) {
                throw InventoryException("Inventory browser is closed.")
            }
            ensureWebView()
            synchronized(bridgeLock) {
                when (pageState) {
                    PageState.READY -> null
                    PageState.LOADING -> pageDeferred
                    PageState.IDLE -> {
                        val created = CompletableDeferred<Unit>()
                        pageDeferred = created
                        pageState = PageState.LOADING
                        webView?.loadUrl(INVENTORY_PAGE)
                        created
                    }
                }
            }
        }
        if (waitFor == null) return
        withTimeoutOrNull(PAGE_LOAD_TIMEOUT_MS) { waitFor.await() }
        synchronized(bridgeLock) {
            pageState = PageState.READY
        }
    }

    private fun ensureWebView() {
        check(Looper.myLooper() == Looper.getMainLooper())
        if (webView != null) return
        val cookies = CookieManager.getInstance()
        cookies.setAcceptCookie(true)
        val view = WebView(activity)
        cookies.setAcceptThirdPartyCookies(view, true)
        view.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            userAgentString = ANDROID_CHROME_UA
            mediaPlaybackRequiresUserGesture = true
            setSupportMultipleWindows(false)
        }
        view.addJavascriptInterface(bridge, BRIDGE_NAME)
        view.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                if (url == null || !url.startsWith("https://www.tesla.com/")) return
                markPageReady()
            }
        }
        view.isFocusable = false
        view.isFocusableInTouchMode = false
        view.isClickable = false
        view.alpha = 0f
        view.setBackgroundColor(0)
        view.importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        val content = activity.findViewById<ViewGroup>(android.R.id.content)
            ?: activity.window.decorView as ViewGroup
        content.addView(view, ViewGroup.LayoutParams(0, 0))
        webView = view
    }

    private fun markPageReady() {
        synchronized(bridgeLock) {
            pageState = PageState.READY
            pageDeferred?.complete(Unit)
        }
    }

    private suspend fun doFetch(url: String): Pair<Int, String> {
        if (destroyed) throw InventoryException("Inventory browser is closed.")
        try {
            return withTimeout(FETCH_TIMEOUT_MS) {
                suspendCancellableCoroutine { cont ->
                    val id = UUID.randomUUID().toString()
                    synchronized(bridgeLock) {
                        transfers[id] = Transfer(cont)
                    }
                    cont.invokeOnCancellation {
                        synchronized(bridgeLock) { transfers.remove(id) }
                    }
                    val script = fetchScript(id, url)
                    mainHandler.post {
                        val view = webView
                        if (!cont.isActive || view == null || destroyed) return@post
                        view.evaluateJavascript(script, null)
                    }
                }
            }
        } catch (exc: TimeoutCancellationException) {
            throw InventoryException("Timed out waiting for Tesla inventory.")
        }
    }

    private class Transfer(
        val continuation: CancellableContinuation<Pair<Int, String>>,
        var status: Int = -1,
        val body: StringBuilder = StringBuilder(),
    )

    inner class Bridge {
        @JavascriptInterface
        fun begin(id: String, status: Int) {
            synchronized(bridgeLock) {
                val transfer = transfers[id] ?: return
                transfer.status = status
                transfer.body.setLength(0)
            }
        }

        @JavascriptInterface
        fun chunk(id: String, text: String?) {
            synchronized(bridgeLock) {
                val transfer = transfers[id] ?: return
                if (!text.isNullOrEmpty()) transfer.body.append(text)
            }
        }

        @JavascriptInterface
        fun finish(id: String) {
            val transfer = synchronized(bridgeLock) { transfers.remove(id) } ?: return
            val cont = transfer.continuation
            if (cont.isActive) cont.resume(transfer.status to transfer.body.toString())
        }

        @JavascriptInterface
        fun onError(id: String, message: String?) {
            val transfer = synchronized(bridgeLock) { transfers.remove(id) } ?: return
            val cont = transfer.continuation
            if (cont.isActive) {
                cont.resumeWithException(
                    InventoryException(
                        "Network error contacting Tesla inventory: ${message ?: "fetch failed"}"
                    )
                )
            }
        }
    }

    private enum class PageState { IDLE, LOADING, READY }

    companion object {
        private const val BRIDGE_NAME = "TeslaBridge"
        private const val INVENTORY_PAGE = "https://www.tesla.com/inventory/new/my"
        private const val PAGE_LOAD_TIMEOUT_MS = 20_000L
        private const val FETCH_TIMEOUT_MS = 30_000L

        // Reduced UA that current Chrome on Android actually sends (Chrome 154, Oct 2026).
        private const val ANDROID_CHROME_UA =
            "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) " +
                "Chrome/154.0.0.0 Mobile Safari/537.36"

        private fun fetchScript(id: String, url: String): String {
            val qid = JSONObject.quote(id)
            val qurl = JSONObject.quote(url)
            return """
                (function() {
                  var id = $qid;
                  fetch($qurl, {
                    method: 'GET',
                    credentials: 'include',
                    headers: { 'Accept': 'application/json' }
                  }).then(function(resp) {
                    return resp.text().then(function(text) {
                      var body = (text == null) ? '' : String(text);
                      TeslaBridge.begin(id, resp.status | 0);
                      var size = 120000;
                      var i = 0;
                      while (i < body.length) {
                        var end = Math.min(body.length, i + size);
                        if (end < body.length) {
                          var cu = body.charCodeAt(end - 1);
                          if (cu >= 0xD800 && cu <= 0xDBFF) end = end - 1;
                        }
                        if (end <= i) end = Math.min(body.length, i + 1);
                        TeslaBridge.chunk(id, body.substring(i, end));
                        i = end;
                      }
                      if (body.length === 0) TeslaBridge.chunk(id, '');
                      TeslaBridge.finish(id);
                    }, function() {
                      TeslaBridge.begin(id, resp.status | 0);
                      TeslaBridge.finish(id);
                    });
                  }).catch(function(err) {
                    var msg = (err && err.message) ? String(err.message) : String(err);
                    TeslaBridge.onError(id, msg);
                  });
                })();
            """.trimIndent()
        }
    }
}
