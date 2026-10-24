plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

// The version all of Dannify is at, from the one place it lives. Read through
// Gradle, so a new version is never built from a configuration kept from
// before it (the configuration cache, gradle.properties).
val appVersion: String = Regex("""__version__\s*=\s*'([^']+)'""")
    .find(providers.fileContents(rootProject.layout.projectDirectory.file("../Backend/dannify/__init__.py")).asText.get())!!
    .groupValues[1]

// 4.15.0 is 4150000 and its first fix (4.15.0.1) 4150001: Android installs a
// version over another only when this number grows.
val appVersionCode: Int = appVersion.split('.').map { it.toInt() }.let { p ->
    p[0] * 1_000_000 + p[1] * 10_000 + p[2] * 100 + (p.getOrNull(3) ?: 0)
}

// The Python that runs the build's own steps and compiles the app's Python:
// the same version the app carries.
val hostPython: String = System.getenv("DANNIFY_BUILD_PYTHON") ?: "python"

android {
    namespace = "app.dannify"
    // Compiled against Android 17, which today's AndroidX needs; it still
    // runs as an Android 16 app (targetSdk), with none of 17's new rules.
    compileSdk = 37

    defaultConfig {
        applicationId = "app.dannify"
        minSdk = 24
        targetSdk = 36
        versionCode = appVersionCode
        versionName = appVersion
    }

    // One APK per processor, each with only its own Python and programs:
    // arm64 for phones, x86_64 for Chromebooks and the emulator on a PC.
    flavorDimensions += "abi"
    productFlavors {
        create("arm64") {
            dimension = "abi"
            ndk { abiFilters += "arm64-v8a" }
        }
        create("x86_64") {
            dimension = "abi"
            ndk { abiFilters += "x86_64" }
        }
    }

    buildTypes {
        debug {
            // Beside the real app on the same phone, never in its place.
            applicationIdSuffix = ".dev"
            versionNameSuffix = "-dev"
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            // Signed on the release machine (packaging/publish.ps1), with the
            // key that never leaves it.
            signingConfig = null
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = true
    }

    packaging {
        jniLibs {
            // The programs the app carries (QuickJS, the media tool) have to
            // be files on the phone to run: installed, not left in the APK.
            useLegacyPackaging = true
        }
    }
}

chaquopy {
    defaultConfig {
        version = "3.14"
        System.getenv("DANNIFY_BUILD_PYTHON")?.let { buildPython(it) }
        pip {
            // pydantic-core, built for Android by .github/workflows/android-native.yml.
            options("--find-links", rootDir.resolve("native/wheels").path)
            install("-r", rootDir.resolve("requirements-android.txt").path)
        }
        // Compiled bytecode only: no source in the app.
        pyc {
            src = true
        }
        // Read by path, so they are files on the phone and not inside the APK.
        extractPackages("certifi", "yt_dlp_ejs", "ytmusicapi", "dannify")
    }
    sourceSets {
        getByName("main") {
            // The backend itself, as the desktop app runs it, without the
            // desktop's windows.
            srcDir("../../Backend")
            include("main.py", "dannify/**")
            exclude(
                "**/__pycache__/**",
                "dannify/shell/windows/**",
                "dannify/shell/linux/**",
                "dannify/shell/macos/**",
            )
        }
    }
}

// The packed interface (assets/dannify.res) and the programs the app carries
// (jniLibs/<abi>/lib*.so), made before every build by tools/prepare.py from
// frontend/dist and android/native.
val prepareDannify = tasks.register<Exec>("prepareDannify") {
    group = "dannify"
    description = "Packs the interface and places the programs the app carries."
    workingDir = rootDir
    commandLine(hostPython, "tools/prepare.py")
    inputs.dir(rootDir.resolve("../frontend/dist"))
    inputs.dir(rootDir.resolve("native"))
    inputs.file(rootDir.resolve("tools/prepare.py"))
    outputs.file(projectDir.resolve("src/main/assets/dannify.res"))
    outputs.dir(projectDir.resolve("src/main/jniLibs"))
}
tasks.named("preBuild") { dependsOn(prepareDannify) }

dependencies {
    implementation("androidx.core:core-ktx:1.19.1")
    implementation("androidx.activity:activity-ktx:1.13.0")
    implementation("androidx.core:core-splashscreen:1.2.0")
    implementation("androidx.webkit:webkit:1.18.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.11.0")
    implementation("androidx.media3:media3-common:1.11.1")
    implementation("androidx.media3:media3-session:1.11.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.11.0")
}
