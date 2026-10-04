package com.teslasearch.vehicle

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL
import java.util.Locale
import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.round
import kotlin.math.sin
import kotlin.math.sqrt

const val INVENTORY_URL = "https://www.tesla.com/inventory/api/v4/inventory-results"
private const val ZIPPO_URL = "https://api.zippopotam.us/us/"

const val USER_AGENT =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " +
        "AppleWebKit/537.36 (KHTML, like Gecko) " +
        "Chrome/131.0.0.0 Safari/537.36"

val MODEL_CODES = linkedMapOf(
    "Model 3" to "m3",
    "Model Y" to "my",
    "Model S" to "ms",
    "Model X" to "mx",
    "Cybertruck" to "ct",
)
private val CODE_TO_NAME = MODEL_CODES.entries.associate { it.value to it.key }

const val PAGE_SIZE = 50
const val PER_QUERY_CAP = 200
private const val PAGE_DELAY_MS = 350L
const val YEAR_LO_DEFAULT = 2018

val DISTANCE_CHOICES = listOf(
    "Any / nationwide" to null,
    "25 miles" to 25,
    "50 miles" to 50,
    "100 miles" to 100,
    "200 miles" to 200,
    "500 miles" to 500,
)

class InventoryException(message: String, val statusCode: Int? = null) : Exception(message)

data class GeoPoint(
    val lat: Double,
    val lng: Double,
    val zipCode: String,
    val placeName: String = "",
    val state: String = "",
)

data class Vehicle(
    val vin: String,
    val modelCode: String,
    val modelName: String,
    val trim: String,
    val year: Int?,
    val price: Double?,
    val listPrice: Double?,
    val discount: Double?,
    val odometer: Double?,
    val odometerUnit: String,
    val city: String,
    val state: String,
    val location: String,
    val distanceMiles: Double?,
    val condition: String,
    val transportationFee: Double?,
    val paint: String,
    val interior: String,
    val isBestDeal: Boolean = false,
)

data class SearchResult(
    val vehicles: List<Vehicle>,
    val truncated: Boolean,
    val errors: List<String>,
)

private fun percentEncode(value: String): String {
    val sb = StringBuilder(value.length * 2)
    for (b in value.toByteArray(Charsets.UTF_8)) {
        val c = b.toInt() and 0xFF
        val ch = c.toChar()
        val safe = (ch in 'A'..'Z') || (ch in 'a'..'z') || (ch in '0'..'9') ||
            ch == '-' || ch == '_' || ch == '.' || ch == '~'
        if (safe) sb.append(ch) else sb.append(String.format(Locale.US, "%%%02X", c))
    }
    return sb.toString()
}

private fun httpGet(url: String, timeoutMs: Int): Pair<Int, String> {
    val conn = (URL(url).openConnection() as HttpURLConnection).apply {
        requestMethod = "GET"
        connectTimeout = timeoutMs
        readTimeout = timeoutMs
        instanceFollowRedirects = true
        setRequestProperty("User-Agent", USER_AGENT)
        setRequestProperty("Accept", "application/json, text/plain, */*")
        setRequestProperty("Accept-Language", "en-US,en;q=0.9")
    }
    try {
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val body = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
        return code to body
    } finally {
        conn.disconnect()
    }
}

fun geocodeZip(zipCode: String): GeoPoint {
    val zip = zipCode.trim()
    if (zip.length != 5 || zip.any { !it.isDigit() }) {
        throw InventoryException("Enter a valid 5-digit US ZIP code.")
    }
    val code: Int
    val body: String
    try {
        val resp = httpGet(ZIPPO_URL + zip, 15_000)
        code = resp.first
        body = resp.second
    } catch (exc: Exception) {
        throw InventoryException("Could not geocode ZIP $zip: ${exc.message}")
    }
    if (code == 404) throw InventoryException("ZIP code $zip was not found.")
    if (code !in 200..299) throw InventoryException("Geocoder HTTP $code")
    val data = try {
        JSONObject(body)
    } catch (exc: Exception) {
        throw InventoryException("Could not geocode ZIP $zip: ${exc.message}")
    }
    val places = data.optJSONArray("places") ?: JSONArray()
    if (places.length() == 0) throw InventoryException("No location found for ZIP $zip.")
    val place = places.getJSONObject(0)
    return GeoPoint(
        lat = place.getString("latitude").toDouble(),
        lng = place.getString("longitude").toDouble(),
        zipCode = zip,
        placeName = place.optString("place name"),
        state = place.optString("state abbreviation"),
    )
}

private suspend fun teslaGetJson(
    url: String,
    teslaGet: suspend (String) -> Pair<Int, String>,
): JSONObject {
    val code: Int
    val body: String
    try {
        val resp = teslaGet(url)
        code = resp.first
        body = resp.second
    } catch (exc: CancellationException) {
        throw exc
    } catch (exc: SocketTimeoutException) {
        throw InventoryException("Timed out waiting for Tesla inventory.")
    } catch (exc: InventoryException) {
        throw exc
    } catch (exc: Exception) {
        throw InventoryException("Network error contacting Tesla inventory: ${exc.message}")
    }
    if (code == 403) {
        throw InventoryException(
            "Tesla refused the inventory request (HTTP 403).",
            statusCode = 403,
        )
    }
    if (code !in 200..299) {
        throw InventoryException(
            "Tesla inventory HTTP $code: ${body.take(300)}",
            statusCode = code,
        )
    }
    return try {
        JSONObject(body)
    } catch (exc: Exception) {
        throw InventoryException(
            "Tesla inventory returned non-JSON (API schema may have changed). " +
                "Status $code. Body starts: ${body.take(160)}"
        )
    }
}

private fun JSONObject.numOrNull(key: String): Double? {
    if (!has(key) || isNull(key)) return null
    return when (val value = opt(key)) {
        is Number -> value.toDouble()
        is String -> value.trim().toDoubleOrNull()
        else -> null
    }
}

private fun flattenResults(payload: JSONObject): List<JSONObject> {
    if (!payload.has("results") || payload.isNull("results")) return emptyList()
    return when (val results = payload.get("results")) {
        is JSONArray -> buildList {
            for (i in 0 until results.length()) results.optJSONObject(i)?.let { add(it) }
        }
        is JSONObject -> {
            val out = mutableListOf<JSONObject>()
            for (key in listOf("exact", "approximate", "approximateOutside")) {
                val bucket = results.optJSONArray(key) ?: continue
                for (i in 0 until bucket.length()) bucket.optJSONObject(i)?.let { out.add(it) }
            }
            if (out.isEmpty()) {
                val keys = results.keys()
                while (keys.hasNext()) {
                    val value = results.opt(keys.next())
                    if (value is JSONArray) {
                        for (i in 0 until value.length()) value.optJSONObject(i)?.let { out.add(it) }
                    }
                }
            }
            out
        }
        else -> emptyList()
    }
}

private fun haversineMiles(lat1: Double, lng1: Double, lat2: Double, lng2: Double): Double {
    val r = 3958.7613
    val p1 = Math.toRadians(lat1)
    val p2 = Math.toRadians(lat2)
    val dphi = Math.toRadians(lat2 - lat1)
    val dlmb = Math.toRadians(lng2 - lng1)
    val a = sin(dphi / 2).let { it * it } + cos(p1) * cos(p2) * sin(dlmb / 2).let { it * it }
    return 2 * r * asin(sqrt(a))
}

private fun firstLatLng(raw: JSONObject): Pair<Double?, Double?> {
    val vrl = raw.optJSONArray("vrlList")
    if (vrl != null && vrl.length() > 0) {
        val item = vrl.optJSONObject(0)
        if (item != null) {
            val lat = item.numOrNull("lat")
            val lng = item.numOrNull("lon") ?: item.numOrNull("lng")
            if (lat != null && lng != null && !(lat == 0.0 && lng == 0.0)) return lat to lng
        }
    }
    val geo = raw.optJSONArray("geoPoints")
    if (geo != null && geo.length() > 0) {
        val first = geo.opt(0)
        if (first is JSONArray && first.length() > 0) {
            val coord = first.optString(0)
            if (coord.contains(",")) {
                val parts = coord.split(",", limit = 2)
                val lat = parts[0].toDoubleOrNull()
                val lng = parts.getOrNull(1)?.toDoubleOrNull()
                if (lat != null && lng != null && !(lat == 0.0 && lng == 0.0)) return lat to lng
            }
        }
    }
    return null to null
}

private fun effectivePrice(raw: JSONObject): Double? {
    for (key in listOf("PurchasePrice", "InventoryPrice", "Price", "TotalPrice")) {
        val value = raw.numOrNull(key)
        if (value != null && value > 0) return value
    }
    return null
}

private fun listPrice(raw: JSONObject): Double? {
    for (key in listOf("TotalPrice", "Price", "InventoryPrice")) {
        val value = raw.numOrNull(key)
        if (value != null && value > 0) return value
    }
    return null
}

private fun discountAmount(raw: JSONObject, purchase: Double?, listed: Double?): Double? {
    val disc = raw.numOrNull("Discount")
    if (disc != null && disc > 0) return disc
    val totalDisc = raw.numOrNull("TotalDiscount")
    if (totalDisc != null && totalDisc > 0) return totalDisc
    val cash = raw.optJSONObject("CashDetails")?.optJSONObject("cash")
    val cashDisc = cash?.numOrNull("inventoryDiscountWithTax")
    if (cashDisc != null && cashDisc > 0) return cashDisc
    if (purchase != null && listed != null && listed > purchase) return listed - purchase
    return disc
}

private fun optionLabel(raw: JSONObject, key: String): String {
    val arr = raw.optJSONArray(key) ?: return ""
    if (arr.length() == 0) return ""
    return arr.optString(0).replace("_", " ").split(" ").joinToString(" ") { word ->
        word.replaceFirstChar { if (it.isLowerCase()) it.titlecase(Locale.US) else it.toString() }
    }
}

fun parseVehicle(raw: JSONObject, condition: String, origin: GeoPoint): Vehicle {
    val modelCode = raw.optString("Model").lowercase(Locale.US).trim()
    val modelName = CODE_TO_NAME[modelCode] ?: modelCode.uppercase(Locale.US).ifEmpty { "Unknown" }
    val purchase = effectivePrice(raw)
    val listed = listPrice(raw)
    val city = raw.optString("City").trim()
    val state = raw.optString("StateProvince").trim()
    val metro = raw.optString("MetroName").trim()
    val location = when {
        city.isNotEmpty() && state.isNotEmpty() -> "$city, $state"
        metro.isNotEmpty() -> metro
        city.isNotEmpty() || state.isNotEmpty() -> city.ifEmpty { state }
        else -> "Location TBA"
    }
    val (lat, lng) = firstLatLng(raw)
    val distance = if (lat != null && lng != null) {
        round(haversineMiles(origin.lat, origin.lng, lat, lng) * 10.0) / 10.0
    } else {
        null
    }
    val yearNum = raw.numOrNull("Year")
    return Vehicle(
        vin = raw.optString("VIN"),
        modelCode = modelCode,
        modelName = modelName,
        trim = raw.optString("TrimName").ifBlank { raw.optString("TrimCode") }.trim(),
        year = yearNum?.toInt(),
        price = purchase,
        listPrice = listed,
        discount = discountAmount(raw, purchase, listed),
        odometer = raw.numOrNull("Odometer"),
        odometerUnit = raw.optString("OdometerTypeShort").ifBlank { raw.optString("OdometerType") }.ifBlank { "mi" },
        city = city,
        state = state,
        location = location,
        distanceMiles = distance,
        condition = condition,
        transportationFee = raw.numOrNull("TransportationFee"),
        paint = optionLabel(raw, "PAINT"),
        interior = optionLabel(raw, "INTERIOR"),
    )
}

private fun buildQuery(
    modelCode: String,
    condition: String,
    geo: GeoPoint,
    rangeMiles: Int,
    offset: Int,
    count: Int,
): String {
    val inner = JSONObject()
    inner.put("model", modelCode)
    inner.put("condition", condition)
    inner.put("options", JSONObject())
    inner.put("arrangeby", "Price")
    inner.put("order", "asc")
    inner.put("market", "US")
    inner.put("language", "en")
    inner.put("super_region", "north america")
    inner.put("zip", geo.zipCode)
    inner.put("lat", geo.lat)
    inner.put("lng", geo.lng)
    inner.put("range", rangeMiles)
    val root = JSONObject()
    root.put("query", inner)
    root.put("offset", offset)
    root.put("count", count)
    root.put("outsideOffset", 0)
    root.put("outsideSearch", true)
    return root.toString()
}

private suspend fun fetchPage(
    queryJson: String,
    teslaGet: suspend (String) -> Pair<Int, String>,
): JSONObject {
    val url = "$INVENTORY_URL?query=${percentEncode(queryJson)}"
    return teslaGetJson(url, teslaGet)
}

private fun yearInRange(year: Int?, yearMin: Int, yearMax: Int, filterActive: Boolean): Boolean {
    if (!filterActive) return true
    if (year == null) return false
    return year in yearMin..yearMax
}

suspend fun searchInventory(
    modelNames: List<String>,
    condition: String,
    zipCode: String,
    maxMiles: Int?,
    yearMin: Int,
    yearMax: Int,
    yearFilterActive: Boolean,
    teslaGet: suspend (String) -> Pair<Int, String>,
    onProgress: suspend (String) -> Unit,
): SearchResult {
    onProgress("Geocoding ZIP $zipCode…")
    val geo = geocodeZip(zipCode)

    val modelCodes = mutableListOf<String>()
    for (name in modelNames) {
        val code = (MODEL_CODES[name] ?: name).lowercase(Locale.US).trim()
        if (code in CODE_TO_NAME && code !in modelCodes) modelCodes.add(code)
    }
    if (modelCodes.isEmpty()) throw InventoryException("Select at least one model.")

    val condNorm = condition.lowercase(Locale.US)
    val conditions = when (condNorm) {
        "both" -> listOf("new", "used")
        "new", "used" -> listOf(condNorm)
        else -> throw InventoryException("Condition must be New, Used, or Both.")
    }

    val nationwide = maxMiles == null
    val rangeMiles = maxMiles ?: 5000
    val vehicles = mutableListOf<Vehicle>()
    val seen = mutableSetOf<String>()
    val errors = mutableListOf<String>()
    var truncated = false

    for (modelCode in modelCodes) {
        for (cond in conditions) {
            val label = "${CODE_TO_NAME[modelCode] ?: modelCode} ($cond)"
            onProgress("Searching $label…")
            var offset = 0
            var gathered = 0
            try {
                while (gathered < PER_QUERY_CAP) {
                    val count = minOf(PAGE_SIZE, PER_QUERY_CAP - gathered)
                    val query = buildQuery(modelCode, cond, geo, rangeMiles, offset, count)
                    val payload = fetchPage(query, teslaGet)
                    val page = flattenResults(payload)
                    val totalRaw = if (payload.has("total_matches_found") && !payload.isNull("total_matches_found")) {
                        payload.opt("total_matches_found")
                    } else {
                        null
                    }
                    val totalMatches = when (totalRaw) {
                        is Number -> totalRaw.toInt()
                        is String -> totalRaw.toIntOrNull()
                        else -> null
                    }
                    if (page.isEmpty()) break
                    for (raw in page) {
                        val vehicle = parseVehicle(raw, cond, geo)
                        if (vehicle.vin.isNotEmpty() && vehicle.vin in seen) continue
                        if (vehicle.vin.isNotEmpty()) seen.add(vehicle.vin)
                        if (vehicle.price == null) continue
                        if (!yearInRange(vehicle.year, yearMin, yearMax, yearFilterActive)) continue
                        if (!nationwide && vehicle.distanceMiles != null && vehicle.distanceMiles > rangeMiles) continue
                        vehicles.add(vehicle)
                        gathered += 1
                        if (gathered >= PER_QUERY_CAP) break
                    }
                    offset += page.size
                    if (page.size < PAGE_SIZE) break
                    if (totalMatches != null && offset >= totalMatches) break
                    if (gathered >= PER_QUERY_CAP) {
                        if (totalMatches != null && totalMatches > PER_QUERY_CAP) truncated = true
                        else if (totalMatches == null) truncated = true
                        break
                    }
                    delay(PAGE_DELAY_MS)
                }
            } catch (exc: InventoryException) {
                errors.add("$label: ${exc.message}")
                onProgress(exc.message ?: "Search error")
                if (exc.statusCode == 403) throw exc
            }
        }
    }

    val sorted = vehicles.sortedWith(compareBy<Vehicle> { it.price == null }.thenBy { it.price ?: Double.MAX_VALUE })
    val marked = if (sorted.isNotEmpty()) {
        sorted.mapIndexed { index, vehicle -> vehicle.copy(isBestDeal = index == 0) }
    } else {
        sorted
    }
    onProgress("Done. ${marked.size} matching vehicle(s).")
    return SearchResult(marked, truncated, errors)
}
