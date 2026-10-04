package com.teslasearch.vehicle

import android.os.Bundle
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.NumberFormat
import java.time.Year
import java.util.Locale

private val Bg = Color(0xFF0B0B0B)
private val Panel = Color(0xFF141414)
private val Input = Color(0xFF1C1C1C)
private val Fg = Color(0xFFF2F2F2)
private val Dim = Color(0xFF9A9A9A)
private val Accent = Color(0xFFE31937)
private val Best = Color(0xFF7DFFB0)

private val TeslaColors = darkColorScheme(
    primary = Accent,
    onPrimary = Color.White,
    background = Bg,
    onBackground = Fg,
    surface = Panel,
    onSurface = Fg,
    surfaceVariant = Input,
    onSurfaceVariant = Dim,
    outline = Color(0xFF2A2A2A),
    error = Accent,
)

data class UiState(
    val zip: String = "90210",
    val selectedModels: Set<String> = MODEL_CODES.keys.toSet(),
    val condition: String = "both",
    val yearMin: String = YEAR_LO_DEFAULT.toString(),
    val yearMax: String = (Year.now().value + 1).toString(),
    val distanceLabel: String = "Any / nationwide",
    val searching: Boolean = false,
    val status: String = "Ready. Set filters and tap Search.",
    val summary: String = "No results yet",
    val vehicles: List<Vehicle> = emptyList(),
    val errorDialog: String? = null,
    val showGuide: Boolean = false,
    val showAbout: Boolean = false,
    val listingUrl: String? = null,
    val listingTitle: String = "",
)

class SearchViewModel : ViewModel() {
    var ui by mutableStateOf(UiState())
        private set

    @Volatile
    var teslaFetch: (suspend (String) -> Pair<Int, String>)? = null

    private var job: Job? = null

    fun updateZip(value: String) { ui = ui.copy(zip = value.filter { it.isDigit() }.take(5)) }
    fun toggleModel(name: String) {
        val next = ui.selectedModels.toMutableSet()
        if (!next.add(name)) next.remove(name)
        ui = ui.copy(selectedModels = next)
    }
    fun setCondition(value: String) { ui = ui.copy(condition = value) }
    fun setYearMin(value: String) { ui = ui.copy(yearMin = value.filter { it.isDigit() }.take(4)) }
    fun setYearMax(value: String) { ui = ui.copy(yearMax = value.filter { it.isDigit() }.take(4)) }
    fun setDistance(label: String) { ui = ui.copy(distanceLabel = label) }
    fun dismissError() { ui = ui.copy(errorDialog = null) }
    fun showGuide(show: Boolean) { ui = ui.copy(showGuide = show) }
    fun showAbout(show: Boolean) { ui = ui.copy(showAbout = show) }
    fun openListing(vehicle: Vehicle) {
        val url = buildListingUrl(vehicle)
        if (url == null) {
            ui = ui.copy(
                errorDialog = if (vehicle.vin.isBlank()) {
                    "This result has no VIN, so the Tesla listing cannot be opened."
                } else {
                    "This result cannot be opened."
                },
            )
            return
        }
        val title = listOfNotNull(vehicle.year?.toString(), vehicle.modelName)
            .joinToString(" ")
            .ifBlank { "Tesla listing" }
        ui = ui.copy(listingUrl = url, listingTitle = title)
    }
    fun closeListing() { ui = ui.copy(listingUrl = null, listingTitle = "") }

    fun clearResults() {
        ui = ui.copy(vehicles = emptyList(), summary = "No results yet", status = "Results cleared.")
    }

    fun search() {
        if (job?.isActive == true) {
            ui = ui.copy(errorDialog = "A search is already running.")
            return
        }
        val fetch = teslaFetch
        if (fetch == null) {
            ui = ui.copy(errorDialog = "Inventory browser is not ready yet. Try again.")
            return
        }
        if (ui.selectedModels.isEmpty()) {
            ui = ui.copy(errorDialog = "Select at least one model.")
            return
        }
        val yearMin: Int
        val yearMax: Int
        val yearActive: Boolean
        try {
            val bounds = yearBounds(ui.yearMin, ui.yearMax)
            yearMin = bounds.first
            yearMax = bounds.second
            yearActive = bounds.third
        } catch (exc: InventoryException) {
            ui = ui.copy(errorDialog = exc.message)
            return
        }
        val models = MODEL_CODES.keys.filter { it in ui.selectedModels }
        val condition = ui.condition
        val zip = ui.zip.trim()
        val miles = DISTANCE_CHOICES.firstOrNull { it.first == ui.distanceLabel }?.second
        ui = ui.copy(
            searching = true,
            vehicles = emptyList(),
            summary = "Searching Tesla inventory…",
            status = "Searching…",
            errorDialog = null,
        )
        job = viewModelScope.launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    searchInventory(
                        modelNames = models,
                        condition = condition,
                        zipCode = zip,
                        maxMiles = miles,
                        yearMin = yearMin,
                        yearMax = yearMax,
                        yearFilterActive = yearActive,
                        teslaGet = fetch,
                    ) { msg ->
                        withContext(Dispatchers.Main) {
                            ui = ui.copy(status = msg)
                        }
                    }
                }
                val parts = mutableListOf("${result.vehicles.size} vehicle(s)")
                if (result.truncated) parts.add("results truncated (per-model cap)")
                if (result.errors.isNotEmpty()) parts.add("${result.errors.size} query warning(s)")
                var status = "Found ${result.vehicles.size} matching vehicle(s)."
                if (result.truncated) status += " Some queries hit the paging cap — results may be incomplete."
                if (result.errors.isNotEmpty()) status += " " + result.errors.take(2).joinToString("; ")
                ui = ui.copy(
                    searching = false,
                    vehicles = result.vehicles,
                    summary = parts.joinToString(" · "),
                    status = status,
                )
            } catch (exc: Exception) {
                ui = ui.copy(
                    searching = false,
                    summary = "Search failed",
                    status = "Error: ${exc.message}",
                    errorDialog = exc.message ?: "Search failed",
                )
            }
        }
    }
}

private fun yearBounds(minText: String, maxText: String): Triple<Int, Int, Boolean> {
    val parsedMin = minText.trim().toIntOrNull()
    val parsedMax = maxText.trim().toIntOrNull()
    if (parsedMin == null || parsedMax == null) {
        throw InventoryException("Year min/max must be integers.")
    }
    var yMin = parsedMin
    var yMax = parsedMax
    if (yMin > yMax) {
        val swap = yMin
        yMin = yMax
        yMax = swap
    }
    val yearHi = Year.now().value + 1
    var active = !(yMin <= YEAR_LO_DEFAULT && yMax >= yearHi)
    if (yMin <= 2012 && yMax >= yearHi) active = false
    return Triple(yMin, yMax, active)
}

class MainActivity : ComponentActivity() {
    private var inventoryBrowser: TeslaWebFetcher? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val browser = TeslaWebFetcher(this)
        inventoryBrowser = browser
        setContent {
            MaterialTheme(colorScheme = TeslaColors) {
                val vm: SearchViewModel = viewModel()
                SideEffect { vm.teslaFetch = browser::fetch }
                TeslaSearchScreen(vm)
            }
        }
    }

    override fun onDestroy() {
        inventoryBrowser?.destroy()
        inventoryBrowser = null
        super.onDestroy()
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
private fun TeslaSearchScreen(vm: SearchViewModel) {
    val ui = vm.ui
    var menu by remember { mutableStateOf(false) }
    var distanceOpen by remember { mutableStateOf(false) }

    Box(Modifier.fillMaxSize()) {
    Scaffold(
        containerColor = Bg,
        topBar = {
            TopAppBar(
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Bg, titleContentColor = Fg),
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("TESLA", color = Accent, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                        Text("  Vehicle Search", fontWeight = FontWeight.Bold)
                    }
                },
                actions = {
                    TextButton(onClick = { menu = true }) { Text("Help", color = Fg) }
                    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                        DropdownMenuItem(
                            text = { Text("User guide") },
                            onClick = { menu = false; vm.showGuide(true) },
                        )
                        DropdownMenuItem(
                            text = { Text("About") },
                            onClick = { menu = false; vm.showAbout(true) },
                        )
                    }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item {
                Text("Public inventory · best price first", color = Dim, fontSize = 13.sp)
                OutlinedTextField(
                    value = ui.zip,
                    onValueChange = vm::updateZip,
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("ZIP code") },
                    supportingText = { Text("Search origin") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                )
                Text("Models", color = Fg, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 8.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    MODEL_CODES.keys.forEach { name ->
                        FilterChip(
                            selected = name in ui.selectedModels,
                            onClick = { vm.toggleModel(name) },
                            label = { Text(name) },
                        )
                    }
                }
                Text("Condition", color = Fg, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 8.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("both" to "Both", "new" to "New", "used" to "Used").forEach { (value, label) ->
                        FilterChip(
                            selected = ui.condition == value,
                            onClick = { vm.setCondition(value) },
                            label = { Text(label) },
                        )
                    }
                }
                Text("Year range", color = Fg, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 8.dp))
                Row(modifier = Modifier.fillMaxWidth()) {
                    OutlinedTextField(
                        value = ui.yearMin,
                        onValueChange = vm::setYearMin,
                        modifier = Modifier.weight(1f),
                        label = { Text("Min") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    )
                    Spacer(Modifier.width(8.dp))
                    OutlinedTextField(
                        value = ui.yearMax,
                        onValueChange = vm::setYearMax,
                        modifier = Modifier.weight(1f),
                        label = { Text("Max") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    )
                }
                Text(
                    "Narrowing years excludes cars with no Year.",
                    color = Dim,
                    fontSize = 12.sp,
                )
                Text("Max distance", color = Fg, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 8.dp))
                OutlinedButton(onClick = { distanceOpen = true }, modifier = Modifier.fillMaxWidth()) {
                    Text(ui.distanceLabel, color = Fg)
                }
                DropdownMenu(expanded = distanceOpen, onDismissRequest = { distanceOpen = false }) {
                    DISTANCE_CHOICES.forEach { (label, _) ->
                        DropdownMenuItem(
                            text = { Text(label) },
                            onClick = {
                                vm.setDistance(label)
                                distanceOpen = false
                            },
                        )
                    }
                }
                Button(
                    onClick = vm::search,
                    enabled = !ui.searching,
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Accent, contentColor = Color.White),
                ) {
                    Text(if (ui.searching) "Searching…" else "Search inventory", fontWeight = FontWeight.Bold)
                }
                OutlinedButton(onClick = vm::clearResults, modifier = Modifier.fillMaxWidth()) {
                    Text("Clear results", color = Fg)
                }
                if (ui.searching) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        CircularProgressIndicator(color = Accent, modifier = Modifier.height(22.dp).width(22.dp), strokeWidth = 2.dp)
                        Text(ui.status, color = Dim, modifier = Modifier.padding(start = 10.dp), fontSize = 13.sp)
                    }
                } else {
                    Text(ui.status, color = Dim, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
                }
                Text(ui.summary, color = Fg, fontWeight = FontWeight.Medium, modifier = Modifier.padding(top = 4.dp))
            }
            items(ui.vehicles, key = { it.vin.ifBlank { it.hashCode().toString() } }) { vehicle ->
                VehicleCard(vehicle) { vm.openListing(vehicle) }
            }
        }
    }

    ui.errorDialog?.let { message ->
        AlertDialog(
            onDismissRequest = vm::dismissError,
            confirmButton = { TextButton(onClick = vm::dismissError) { Text("OK") } },
            title = { Text("Tesla Vehicle Search") },
            text = { Text(message) },
            containerColor = Panel,
        )
    }
    if (ui.showGuide) {
        AlertDialog(
            onDismissRequest = { vm.showGuide(false) },
            confirmButton = { TextButton(onClick = { vm.showGuide(false) }) { Text("Close") } },
            title = { Text("User guide") },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    Text(USER_GUIDE, color = Fg, fontSize = 14.sp)
                }
            },
            containerColor = Panel,
        )
    }
    if (ui.showAbout) {
        AlertDialog(
            onDismissRequest = { vm.showAbout(false) },
            confirmButton = { TextButton(onClick = { vm.showAbout(false) }) { Text("Close") } },
            title = { Text("Tesla Vehicle Search") },
            text = {
                Text("Android\nVersion ${BuildConfig.VERSION_NAME}\n\nSearches Tesla public US inventory and ranks matches by lowest effective price.")
            },
            containerColor = Panel,
        )
    }
    val listing = ui.listingUrl
    if (listing != null) {
        ListingScreen(
            url = listing,
            title = ui.listingTitle,
            onBack = vm::closeListing,
        )
    }
    }
}

@Composable
private fun VehicleCard(vehicle: Vehicle, onClick: () -> Unit) {
    Card(
        onClick = onClick,
        colors = CardDefaults.cardColors(containerColor = if (vehicle.isBestDeal) Color(0xFF14281C) else Panel),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            if (vehicle.isBestDeal) {
                Text("BEST DEAL", color = Best, fontWeight = FontWeight.Bold, fontSize = 12.sp)
            }
            Text(
                "${vehicle.year ?: "—"} ${vehicle.modelName} ${vehicle.trim}".trim(),
                color = Fg,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                "${money(vehicle.price)}    Discount ${if (vehicle.discount != null && vehicle.discount > 0) money(vehicle.discount) else "—"}",
                color = Fg,
            )
            Text(
                "${vehicle.condition.replaceFirstChar { it.titlecase(Locale.US) }} · ${miles(vehicle)}",
                color = Dim,
                fontSize = 13.sp,
            )
            Text(
                "${vehicle.location} · ${if (vehicle.distanceMiles != null) "${vehicle.distanceMiles.toInt()} mi" else "—"}",
                color = Dim,
                fontSize = 13.sp,
            )
            Text("VIN ${vehicle.vin.ifBlank { "—" }}", color = Dim, fontSize = 12.sp)
            Text("Tap to open Tesla listing", color = Dim, fontSize = 12.sp)
        }
    }
}

private fun money(value: Double?): String {
    if (value == null) return "—"
    val fmt = NumberFormat.getCurrencyInstance(Locale.US)
    fmt.maximumFractionDigits = 0
    return fmt.format(value)
}

private fun miles(vehicle: Vehicle): String {
    val odo = vehicle.odometer ?: return "—"
    val formatted = if (vehicle.condition.equals("new", true) && odo < 50) {
        odo.toLong().toString()
    } else {
        NumberFormat.getIntegerInstance(Locale.US).format(odo)
    }
    return "$formatted ${vehicle.odometerUnit}"
}


private const val LISTING_CHROME_UA =
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) " +
        "Chrome/154.0.0.0 Mobile Safari/537.36"

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ListingScreen(url: String, title: String, onBack: () -> Unit) {
    var progress by remember(url) { mutableIntStateOf(0) }
    val webViewHolder = remember { mutableStateOf<WebView?>(null) }
    BackHandler {
        val view = webViewHolder.value
        if (view != null && view.canGoBack()) view.goBack() else onBack()
    }
    Scaffold(
        containerColor = Bg,
        topBar = {
            TopAppBar(
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Bg, titleContentColor = Fg),
                navigationIcon = {
                    TextButton(onClick = onBack) { Text("Back", color = Fg) }
                },
                title = {
                    Column {
                        Text(title, fontWeight = FontWeight.SemiBold, maxLines = 1)
                        Text("Tesla listing", color = Dim, fontSize = 12.sp)
                    }
                },
            )
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            if (progress in 1..99) {
                LinearProgressIndicator(
                    progress = { progress / 100f },
                    modifier = Modifier.fillMaxWidth(),
                    color = Accent,
                    trackColor = Input,
                )
            }
            AndroidView(
                modifier = Modifier.fillMaxSize(),
                onRelease = { view ->
                    view.stopLoading()
                    view.destroy()
                },
                factory = { context ->
                    WebView(context).apply {
                        val cookies = CookieManager.getInstance()
                        cookies.setAcceptCookie(true)
                        cookies.setAcceptThirdPartyCookies(this, true)
                        settings.javaScriptEnabled = true
                        settings.domStorageEnabled = true
                        settings.loadsImagesAutomatically = true
                        settings.userAgentString = LISTING_CHROME_UA
                        settings.setSupportZoom(true)
                        settings.builtInZoomControls = true
                        settings.displayZoomControls = false
                        webViewClient = WebViewClient()
                        webChromeClient = object : WebChromeClient() {
                            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                                progress = newProgress
                            }
                        }
                        tag = url
                        loadUrl(url)
                    }
                },
                update = { view ->
                    webViewHolder.value = view
                    if (view.tag != url) {
                        view.tag = url
                        progress = 0
                        view.loadUrl(url)
                    }
                },
            )
        }
    }
}

private val USER_GUIDE = """
Tesla Vehicle Search looks up Tesla's public US inventory and ranks matches by the lowest effective purchase price (PurchasePrice, otherwise InventoryPrice, otherwise Price). The cheapest match is marked Best deal.

ZIP code — At the top. Default 90210, labeled ZIP code, hint Search origin. The app geocodes it with zippopotam.us and sends that latitude and longitude to Tesla.

Models — Multi-select Model 3, Y, S, X, and Cybertruck. Default is all. Codes sent to Tesla: m3, my, ms, mx, ct.

Condition — Both, New, or Used. Default Both. Both runs separate new and used queries.

Year — Min and max. Left wide open, cars with no Year stay in the list. If you narrow the range, missing or out-of-range years are dropped.

Max distance — A mile radius, or Any / nationwide (large range plus outsideSearch). Distance is still measured from the ZIP.

Results show trim, year, price, discount, mileage, city/state (or Location TBA), distance, and VIN. Tap a card to open that car's Tesla listing (photos, price, and options) inside the app. Back returns to these results. Search runs off the main thread. Each model and condition is paged, about 200 vehicles, with a short delay between pages.

Inventory comes from Tesla's public endpoint inventory/api/v4/inventory-results. No Tesla account is used. If Tesla returns HTTP 403, the error is shown as-is.
""".trimIndent()
