# wingSpan iOS app

Native SwiftUI viewer for the wingSpan Pi over BLE. iPhone equivalent of
`index.html` — iOS Safari does not support Web Bluetooth, so this native
app is the only way iPhone testers can see the hive.

## GATT contract (matches sensor_ble.py)

| UUID                                       | Property     | Purpose                          |
| ------------------------------------------ | ------------ | -------------------------------- |
| `e80b5ce0-1111-4000-8000-000000000001`     | primary svc  | wingSpan service                 |
| `e80b5ce0-1111-4000-8000-000000000002`     | read, notify | JSON payload                     |
| `e80b5ce0-1111-4000-8000-000000000003`     | write        | 1-byte command; `0x01` = tare    |

Payload fields (all optional; app tolerates both firmware generations):

```
{ "t": 24.3, "h": 55.1, "db": -35.2, "w": 12.34,
  "bands": {"hum": …, "workers": …, "queen": …, "swarm": …},
  "events": ["workers", …],
  "w_legs": {"FL": 3.1, "FR": 3.0, "BL": 3.2, "BR": 3.0},
  "bat":    {"FL": 92,  "FR": 88,  "BL": 90,  "BR": 87},
  "conn":   {"FL": true, "FR": true, "BL": true, "BR": true},
  "ts": 1782847845 }
```

## Build

1. `brew install xcodegen` if you don't have it.
2. From `ios-app/`: `xcodegen` — generates `wingSpan.xcodeproj`.
3. `open wingSpan.xcodeproj`.
4. In the project's *Signing & Capabilities* tab, set your **Team**
   (an Apple ID with Developer Program membership works; free accounts
   sign for on-device install but cannot upload to TestFlight).
5. Change `PRODUCT_BUNDLE_IDENTIFIER` in `project.yml` to something you
   own (e.g. `com.example.wingspan`), rerun `xcodegen`.
6. Select an iPhone destination, ⌘R.

The `.xcodeproj` is regenerated from `project.yml` and is not checked
in. Modify Swift sources or `project.yml`; never hand-edit the pbxproj.

## Ship to TestFlight

Assumes you already have an Apple Developer Program membership ($99/yr)
and an App Store Connect record for the bundle ID.

1. In Xcode: *Product → Archive* (must build for a generic iOS device,
   not a simulator).
2. *Organizer → Distribute App → App Store Connect → Upload*.
3. In App Store Connect *TestFlight* tab, wait ~10 min for processing.
4. **Internal testers** (up to 100 people in your team): no Apple review
   — invite instantly.
5. **External testers** (up to 10 000): first build needs a TestFlight
   review (24–48 h typical). Later builds usually skip review unless
   entitlements change.

## What's here

```
wingSpan/
  wingSpanApp.swift    entrypoint
  ContentView.swift    root SwiftUI view + cards / legs / activity
  BLEManager.swift     CBCentralManager + CBPeripheralDelegate, JSON decode
  Reading.swift        Codable payload struct
project.yml            XcodeGen spec
```

## What's not here (intentional — MVP scope)

- Multiple unit support (assumes one wingSpan advertising the service).
- History / charts.
- Background BLE — app pauses when backgrounded.
- Push notifications on swarm/queen events.
- Android build (would need Flutter or a separate Kotlin project).
