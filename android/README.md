# Tesla Search (Android)

Phone port of the desktop Tesla Vehicle Search app. Same public inventory API, filters, and lowest-price ranking.

- Package: `com.teslasearch.vehicle`
- Label: Tesla Search
- minSdk 30, targetSdk / compileSdk 34
- Debug APK (universal; no native ABI split, runs on arm64-v8a including Pixel 5): `TeslaSearch.apk`

Install:

```bash
adb install -r TeslaSearch.apk
```

Rebuild (JDK 17, Android SDK with platform 34 and build-tools 34.0.0):

```bash
export JAVA_HOME=/path/to/jdk-17
echo "sdk.dir=$ANDROID_HOME" > local.properties
./gradlew assembleDebug
```

Gradle is configured to try the Aliyun Google/Maven mirrors before `google()` / Maven Central, because some networks cannot reach `dl.google.com`.
