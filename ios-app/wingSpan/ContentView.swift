import SwiftUI

private let bandFreq: [String: String] = [
    "hum":     "100–150 Hz · resting baseline",
    "workers": "200–270 Hz · flight / waggle",
    "queen":   "320–450 Hz · toot / quack",
    "swarm":   "400–500 Hz · swarm energy",
]

private let eventLabels: [String: String] = [
    "workers": "Workers active (200–270 Hz)",
    "queen":   "Queen signal (320–450 Hz)",
    "swarm":   "Swarm marker (400–500 Hz)",
]

private let eventColors: [String: Color] = [
    "workers": .blue,
    "queen":   .purple,
    "swarm":   .red,
]

struct ContentView: View {
    @StateObject private var ble = BLEManager()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    controls
                    statusLine
                    metricsGrid
                    activityCard
                    if hasLegs { legsCard }
                    if let ts = ble.reading.ts {
                        Text("Last update: \(Self.timeFormatter.string(from: Date(timeIntervalSince1970: ts)))")
                            .font(.footnote)
                            .foregroundStyle(.tertiary)
                    }
                }
                .padding()
            }
            .navigationTitle("wingSpan")
        }
    }

    private var controls: some View {
        HStack(spacing: 12) {
            Button(action: connectTapped) {
                Text(connectLabel)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
            }
            .buttonStyle(.borderedProminent)
            .disabled(ble.state == .poweredOff || ble.state == .unauthorized)

            Button(action: { ble.zeroWeight() }) {
                Text("Zero weight")
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
            }
            .buttonStyle(.bordered)
            .disabled(!isConnected)
        }
    }

    private var statusLine: some View {
        Text(statusText)
            .foregroundStyle(.secondary)
            .font(.callout)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var metricsGrid: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())],
                  spacing: 12) {
            Card(label: "Temperature",
                 value: format(ble.reading.t, digits: 1),
                 unit: "°C")
            Card(label: "Humidity",
                 value: format(ble.reading.h, digits: 1),
                 unit: "%")
            Card(label: "Hive weight",
                 value: format(ble.reading.w, digits: 2),
                 unit: "kg")
            Card(label: "Sound level",
                 value: format(ble.reading.db, digits: 1),
                 unit: "dBFS")
        }
    }

    private var activityCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("BEE ACTIVITY")
                .font(.caption).bold()
                .foregroundStyle(.secondary)

            let events = ble.reading.events ?? []
            if events.isEmpty {
                Text("quiet").foregroundStyle(.tertiary)
            } else {
                FlowLayout(spacing: 6) {
                    ForEach(events, id: \.self) { name in
                        Text(eventLabels[name] ?? name)
                            .font(.footnote).bold()
                            .foregroundStyle(.white)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(eventColors[name] ?? .orange, in: Capsule())
                    }
                }
            }

            if let bands = ble.reading.bands {
                VStack(spacing: 4) {
                    ForEach(["hum", "workers", "queen", "swarm"], id: \.self) { name in
                        if let db = bands[name] {
                            HStack {
                                Text(name.capitalized).font(.footnote)
                                Text(bandFreq[name] ?? "")
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                                Spacer()
                                Text(String(format: "%.1f dB", db)).font(.footnote)
                            }
                        }
                    }
                }
                .padding(.top, 4)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.gray.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
    }

    private var legsCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("LOAD CELLS")
                .font(.caption).bold()
                .foregroundStyle(.secondary)
            ForEach(["FL", "FR", "BL", "BR"], id: \.self) { leg in
                LegRow(leg: leg,
                       kg:   ble.reading.wLegs?[leg].flatMap { $0 },
                       bat:  ble.reading.bat?[leg].flatMap { $0 },
                       conn: ble.reading.conn?[leg] ?? false)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.gray.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Helpers

    private var hasLegs: Bool {
        ble.reading.wLegs != nil || ble.reading.conn != nil
    }

    private var isConnected: Bool {
        if case .connected = ble.state { return true } else { return false }
    }

    private var connectLabel: String {
        switch ble.state {
        case .connected:    return "Connected"
        case .scanning:     return "Scanning…"
        case .connecting:   return "Connecting…"
        case .reconnecting: return "Reconnecting…"
        default:            return "Connect"
        }
    }

    private var statusText: String {
        if let e = ble.lastError { return e }
        switch ble.state {
        case .poweredOff:            return "Bluetooth is off."
        case .unauthorized:          return "Enable Bluetooth for wingSpan in Settings."
        case .idle:                  return "Disconnected."
        case .scanning:              return "Scanning for wingSpan…"
        case .connecting(let n):     return "Connecting to \(n)…"
        case .connected(let n):      return "Connected to \(n)"
        case .reconnecting(let n):   return "Lost \(n) — retrying…"
        }
    }

    private func connectTapped() {
        if isConnected { ble.disconnect() } else { ble.startScan() }
    }

    private func format(_ v: Double?, digits: Int) -> String {
        guard let v else { return "—" }
        return String(format: "%.\(digits)f", v)
    }

    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.timeStyle = .medium
        return f
    }()
}

private struct Card: View {
    let label: String
    let value: String
    let unit: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label.uppercased())
                .font(.caption).bold()
                .foregroundStyle(.secondary)
            HStack(alignment: .lastTextBaseline, spacing: 4) {
                Text(value).font(.system(size: 30, weight: .semibold))
                Text(unit).font(.body).foregroundStyle(.secondary)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.gray.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
    }
}

private struct LegRow: View {
    let leg: String
    let kg: Double?
    let bat: Int?
    let conn: Bool

    var body: some View {
        HStack {
            Circle().fill(conn ? .green : .gray).frame(width: 8, height: 8)
            Text(leg).font(.callout.monospaced()).frame(width: 28, alignment: .leading)
            Text(kg.map { String(format: "%.2f kg", $0) } ?? "—")
                .frame(maxWidth: .infinity, alignment: .leading)
            Text(bat.map { "\($0)%" } ?? "—")
                .foregroundStyle(.secondary).font(.footnote)
        }
    }
}

// Minimal wrap-around layout for the event pills.
private struct FlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize,
                      subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowH: CGFloat = 0
        for sub in subviews {
            let s = sub.sizeThatFits(.unspecified)
            if x + s.width > width, x > 0 {
                x = 0; y += rowH + spacing; rowH = 0
            }
            x += s.width + spacing
            rowH = max(rowH, s.height)
        }
        return CGSize(width: proposal.width ?? x, height: y + rowH)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize,
                       subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        var y = bounds.minY
        var rowH: CGFloat = 0
        for sub in subviews {
            let s = sub.sizeThatFits(.unspecified)
            if x + s.width > bounds.maxX, x > bounds.minX {
                x = bounds.minX; y += rowH + spacing; rowH = 0
            }
            sub.place(at: CGPoint(x: x, y: y), proposal: .unspecified)
            x += s.width + spacing
            rowH = max(rowH, s.height)
        }
    }
}
