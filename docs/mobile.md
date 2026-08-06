# autoMate on your phone

The phone is a **controller** for your hub, not a host for it. A phone
sandbox can't run shell commands, drive your real Chrome, or call your
local file system — those things stay on your laptop / NAS / VPS. The
phone shows the same UI, sets reminders, captures notes, browses files.

autoMate ships as a **PWA** (Progressive Web App). One install path
covers both Android and iOS — no app store, no sideloading.

| Phone | What you do | Account / fees |
|---|---|---|
| Android | Open the hub URL in Chrome → menu → **Add to Home Screen** | none |
| iOS | Open the hub URL in Safari → Share → **Add to Home Screen** | none |
| iOS | TestFlight / App Store native build | not provided (Developer Program $99/yr + Xcode + review) |

## Why PWA-only

A native Android APK and an iOS .ipa would each cost build complexity,
keystores, signing, and (for iOS) an Apple Developer membership and
manual review. Modern PWAs cover the same ground — full-screen icon on
the home screen, push notifications (Android always, iOS 17.4+),
offline-friendly. For an open-source self-hosted tool the PWA path is
better-than-native: instant updates, zero distribution overhead.

## Android install

1. On your laptop: `automate serve --host 0.0.0.0`
2. On your phone (same WiFi), Chrome → `http://<laptop-ip>:8765`
3. Three-dot menu → **Add to Home Screen** → confirm
4. The PWA icon appears alongside your other apps; tapping it opens
   the SPA full-screen, like a native app (own task, push notifications,
   offline shell).

## iOS install

1. On your laptop: `automate serve --host 0.0.0.0`
2. On your phone, Safari → `http://<laptop-ip>:8765`
3. Tap Share (square with up-arrow) → **Add to Home Screen**
4. Confirm the name → **Add**
5. The autoMate icon appears on the home screen; tapping it opens the
   SPA full-screen.

iOS PWAs in 17.4+ support Web Push (you'll get reminders).

## Hub-URL strategies

The SPA needs to know where the hub is.

- **At home**: laptop on same WiFi, hub bound to `0.0.0.0:8765` — use
  the laptop's LAN IP. Easy. Free.
- **On the go**: hub on a NAS / VPS, accessed via Tailscale or
  Cloudflare Tunnel — paste that public URL.
- **No setup wanted**: `automate relay …` (when the hosted relay opens),
  paste the relay-issued URL. See [relay.md](./relay.md).

The PWA persists the hub address in `automate-hub-base` localStorage;
change it from Help → "Connect this UI to a different hub".
