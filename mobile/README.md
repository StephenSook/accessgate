# AccessGate Mobile

A React Native (Expo) second surface for AccessGate. It is a real client of the
same live backend as the web app (`https://accessgate-api.onrender.com`), not a
wrapper: it loads the live conformance report and Granite executive summary,
lists the failing rules with their standard citations, and runs the gated
generative fix (watsonx vision drafts an audio description for a silent gap, the
DCMP validator checks it, and the row flips green). It can also check a caption
file picked on-device via the `/check-captions` endpoint.

Built with Expo SDK 57 / React Native 0.86. Shares the backend's typed contract
(`src/api.ts` mirrors the web `frontend/src/api/client.ts`).

## Run on iOS (simulator, no Apple Developer account)

```bash
cd mobile
npm install
npx expo start --ios          # opens Expo Go on the booted iOS simulator
```

If port 8081 is taken, add `--port 8082`. If the simulator can't reach Metro,
start with `REACT_NATIVE_PACKAGER_HOSTNAME=127.0.0.1` so it binds IPv4.

## Build an Android APK (cloud, no local Android SDK)

```bash
cd mobile
eas login                     # free Expo account
eas build -p android --profile preview   # produces an installable .apk
```

The `preview` profile is configured in `eas.json` for APK output. Download the
APK from the EAS build page and install it on any Android device or emulator.

## Screens

- **Home** — Load Demo, or Check a Caption File (on-device picker).
- **Report** — metrics, Granite executive summary, dialogue-free gaps, rule results.
- **Gap fix** — tap a gap → watsonx vision drafts the audio description → DCMP
  validation → accept → flips green.
