# Part 2: Android TWA Setup and Status

## Completed

- Restored Gradle Wrapper: Gradle 8.13, Android Gradle Plugin 8.13.0, Android Studio Java 21.
- Corrected SDK path; compileSdk 35, targetSdk 34, minSdk 21.
- Package `com.helloworld.groupchat.twa`, launcher name `GroupChat`.
- Configured LauncherActivity, icon, HTTPS URL, and application asset statements.
- Built and installed a debug-signed APK on the physical device and emulator.
- Public `/.well-known/assetlinks.json` returns HTTP 200 and application/json with matching signing data.
- Android Lint passed with non-blocking SDK/dependency warnings.
- Cloudflare temporary HTTPS tunnel started with explicit user authorization.
- Public HTTPS/WSS verified signup/login, broadcasts, real inference, and saved messages.
- Physical Android 8.1 device verified signup, message submission, and visible bot responses.
- Mobile layout adjusted to keep input fields inside the viewport.
- Android Studio emulator `emulator-5554` (Android 17 with Chrome) verified full TWA without an address bar.
- Emulator verified registration, logout/login, model response `4`, and session/history restoration after reopening.
- Temporary test accounts, messages, and debug forwarding were cleaned up.

## APK and Website

APK: `artifacts/GroupChat-debug.apk`.
Historical acceptance screenshot: `artifacts/GroupChat-emulator.png`.

Current temporary website:
https://characteristics-ave-inventory-worldcat.trycloudflare.com/

APK SHA-256:
`8D23117F3AE01201AA6A9040642C8054AAAC416A597F95FFEC0E6293D2CD694A`

Signing certificate SHA-256:
`08:B3:62:77:07:75:CF:26:C1:B5:38:0B:F7:05:37:19:53:06:C3:3C:79:6E:99:00:8A:7E:EA:EE:53:8A:4D:C9`

The APK uses the existing `~/.android/debug.keystore`. Do not commit signing private keys.
Changing the key requires updating website fingerprints and reinstalling the APK.
Website text is served remotely; language updates do not require an APK rebuild.

## Runtime Requirements

The old physical device lacks a TWA-compatible browser and opens an ordinary browser window.
Full TWA acceptance was completed on the Android Studio emulator with Chrome, as the PDF permits.
Keep the computer, Docker services, backend, and HTTPS tunnel running.
The temporary hostname usually changes after restarting the tunnel; update and rebuild the APK then.

## Restart and Build

Start Part 1 services first; see [PART1_SETUP.md](PART1_SETUP.md).
Tunnel logs: `logs/tunnel.err.log`. Current URL: `logs/tunnel-url.txt`.
To start a new tunnel, run from `groupchat_app_src` and keep the process running:

```powershell
.\tools\cloudflared.exe tunnel --url http://127.0.0.1:8000 --protocol http2 --no-autoupdate
```

Official download:
https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe

From `twa_android_src`, replace the URL with the new HTTPS origin:

```powershell
python configure_site.py --url https://YOUR_NEW_HOST --sha256 08:B3:62:77:07:75:CF:26:C1:B5:38:0B:F7:05:37:19:53:06:C3:3C:79:6E:99:00:8A:7E:EA:EE:53:8A:4D:C9
$env:JAVA_HOME = 'D:\AndroidStudio\software\jbr'
.\gradlew.bat :app:assembleDebug :app:lintDebug --no-daemon --console plain
adb -s emulator-5554 install -r .\app\build\outputs\apk\debug\app-debug.apk
adb -s emulator-5554 shell am start -n com.helloworld.groupchat.twa/com.google.androidbrowserhelper.trusted.LauncherActivity
```

Use `adb devices -l` to find the current device serial.
Localhost USB forwarding has been removed; the final APK uses public HTTPS.
Open `twa_android_src` in Android Studio, SDK path `D:\AndroidStudio\sdk`.

## Acceptance Checklist

All items passed on the emulator and can be repeated for the video demonstration:

1. Launch GroupChat without a browser address bar.
2. Register/log in and send ordinary messages.
3. Send a question containing `?` and wait for the model reply.
4. Reopen the app and verify session and history restoration.

TWA documentation: https://developer.chrome.com/docs/android/trusted-web-activity/integration-guide
Temporary tunnels: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
