# autoMate on your phone

The phone is a **controller** for your hub, not a host for it. A phone
sandbox can't run shell commands, drive your real Chrome, or call your
local file system — those things stay on your laptop / NAS / VPS. The
phone shows the same UI, sets reminders, captures notes, browses files.

Two flavours:

| Phone | App | What you install | Account / fees |
|---|---|---|---|
| Android | **APK** (real native app) | `autoMate-android.apk` from the GitHub Release — sideload | none |
| Android | PWA (alternative) | Open hub URL in Chrome → Add to Home Screen | none |
| iOS | **PWA only** | Open hub URL in Safari → Share → Add to Home Screen | none |
| iOS | TestFlight or App Store | Not provided — Apple requires Developer Program ($99/yr), macOS + Xcode, and review | varies |

## Why no .ipa for iOS

Apple does not allow installing apps from outside the App Store (no
sideloading like Android). The only way to ship an iOS app is to:

1. Buy an Apple Developer Program membership ($99 / year)
2. Build with Xcode on macOS (CI runners can do this but cost more)
3. Submit to TestFlight (beta) or App Store (public) — **manual review**, days to weeks
4. Get every user to install via TestFlight invitation or App Store search

For an open-source / self-hosted tool that's a lot of friction. The PWA
route gives you 90% of the experience with **zero** of that — Safari
will install autoMate to your home screen with a real icon, full-screen
mode, and (with permissions) push notifications.

If autoMate ever has paying users who specifically need a TestFlight or
App Store version, we'll do that work then. For now, iOS is PWA-only and
that's the documented expectation.

## Android: APK install

1. Download `autoMate-android.apk` from the
   [latest release](https://github.com/yuruotong1/autoMate/releases/latest).
2. Open it from Files / Downloads on your phone. Android will ask you to
   enable "Install from unknown sources" for whatever app you're opening
   it from (typically your file manager or browser). Allow it once.
3. The first time you launch autoMate, it will ask **Connect to your
   autoMate hub** — paste the URL where the hub is reachable:
   - Same WiFi:  `http://<laptop-ip>:8765`  (after `automate serve --host 0.0.0.0`)
   - Relay:      `https://your-relay.example/u/<hub-id>/`  (see [relay.md](./relay.md))
4. The app stores the URL and reuses it next launch. Use the menu →
   **Change hub URL** any time.

The APK bundles the SPA inside it (no GitHub Pages needed), so it works
even if your hub server has been restarted or moved IP — only the URL
needs updating.

## Android: PWA alternative

If you'd rather not sideload an APK:

1. On your laptop:  `automate serve --host 0.0.0.0`
2. On your phone (same WiFi), Chrome → `http://<laptop-ip>:8765`
3. Three-dot menu → **Add to Home Screen** → confirm
4. The PWA icon appears alongside your other apps; tapping it opens
   the SPA full-screen, just like a native app.

Chrome PWAs on Android are nearly indistinguishable from native apps
once installed (own task in the recents view, push notifications,
offline shell).

## iOS: PWA install

1. On your laptop:  `automate serve --host 0.0.0.0`
2. On your phone, Safari → `http://<laptop-ip>:8765`
3. Tap the Share button (square with up-arrow) → **Add to Home Screen**
4. Confirm the name → **Add**
5. The autoMate icon appears on the home screen; tapping it opens the
   SPA in full-screen.

iOS PWAs in 17.4+ support Web Push (you'll get reminders).

## Both: hub-URL strategies

Whichever app you use, the SPA needs to know where the hub is.

- **At home**: laptop on same WiFi, hub bound to `0.0.0.0:8765` — use
  the laptop's LAN IP. Easy. Free.
- **On the go**: hub on a NAS/VPS, accessed via Tailscale or
  Cloudflare Tunnel — paste that public URL.
- **No setup wanted**: `automate relay …` (when the hosted relay opens),
  paste the relay-issued URL. See [relay.md](./relay.md).

The bundled APK and the in-browser PWA both honour `automate-hub-base`
in localStorage; the APK exposes a "Change hub URL" menu entry, the PWA
exposes the same setting in Help → "Connect this UI to a different hub".
