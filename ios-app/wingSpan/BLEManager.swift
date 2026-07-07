import Foundation
import CoreBluetooth

/// CoreBluetooth central that scans for a wingSpan Pi peripheral,
/// subscribes to notify on the DATA characteristic, and writes a
/// single-byte command (0x01 = zero weight) to the CMD characteristic.
///
/// Matches the GATT contract in sensor_ble.py — same three UUIDs.
@MainActor
final class BLEManager: NSObject, ObservableObject {
    static let serviceUUID = CBUUID(string: "e80b5ce0-1111-4000-8000-000000000001")
    static let dataUUID    = CBUUID(string: "e80b5ce0-1111-4000-8000-000000000002")
    static let cmdUUID     = CBUUID(string: "e80b5ce0-1111-4000-8000-000000000003")

    static let cmdZeroWeight: UInt8 = 0x01

    enum State: Equatable {
        case poweredOff
        case unauthorized
        case idle
        case scanning
        case connecting(String)
        case connected(String)
        case reconnecting(String)
    }

    @Published private(set) var state: State = .idle
    @Published private(set) var reading: Reading = .empty
    @Published private(set) var lastError: String?

    private var central: CBCentralManager!
    private var peripheral: CBPeripheral?
    private var dataChar: CBCharacteristic?
    private var cmdChar:  CBCharacteristic?
    private var autoReconnect = false

    override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: .main)
    }

    // MARK: - Public actions

    func startScan() {
        lastError = nil
        guard central.state == .poweredOn else {
            state = mapPowerState(central.state)
            return
        }
        state = .scanning
        autoReconnect = true
        central.scanForPeripherals(withServices: [Self.serviceUUID],
                                   options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
    }

    func disconnect() {
        autoReconnect = false
        if let p = peripheral {
            central.cancelPeripheralConnection(p)
        }
        central.stopScan()
        state = .idle
    }

    func zeroWeight() {
        guard let peripheral = peripheral, let cmd = cmdChar else { return }
        peripheral.writeValue(Data([Self.cmdZeroWeight]),
                              for: cmd,
                              type: .withResponse)
    }

    // MARK: - Internals

    private func mapPowerState(_ s: CBManagerState) -> State {
        switch s {
        case .poweredOff:   return .poweredOff
        case .unauthorized: return .unauthorized
        default:            return .idle
        }
    }
}

// MARK: - Central delegate

extension BLEManager: CBCentralManagerDelegate {
    nonisolated func centralManagerDidUpdateState(_ central: CBCentralManager) {
        Task { @MainActor in
            switch central.state {
            case .poweredOn:
                if self.autoReconnect { self.startScan() }
            case .poweredOff:
                self.state = .poweredOff
            case .unauthorized:
                self.state = .unauthorized
            default:
                self.state = .idle
            }
        }
    }

    nonisolated func centralManager(_ central: CBCentralManager,
                                    didDiscover peripheral: CBPeripheral,
                                    advertisementData: [String: Any],
                                    rssi RSSI: NSNumber) {
        Task { @MainActor in
            central.stopScan()
            self.peripheral = peripheral
            peripheral.delegate = self
            let name = peripheral.name ?? "wingSpan"
            self.state = .connecting(name)
            central.connect(peripheral, options: nil)
        }
    }

    nonisolated func centralManager(_ central: CBCentralManager,
                                    didConnect peripheral: CBPeripheral) {
        Task { @MainActor in
            self.state = .connected(peripheral.name ?? "wingSpan")
            peripheral.discoverServices([Self.serviceUUID])
        }
    }

    nonisolated func centralManager(_ central: CBCentralManager,
                                    didFailToConnect peripheral: CBPeripheral,
                                    error: Error?) {
        Task { @MainActor in
            self.lastError = error?.localizedDescription ?? "connect failed"
            self.reconnectIfWanted()
        }
    }

    nonisolated func centralManager(_ central: CBCentralManager,
                                    didDisconnectPeripheral peripheral: CBPeripheral,
                                    error: Error?) {
        Task { @MainActor in
            self.dataChar = nil
            self.cmdChar  = nil
            if let e = error { self.lastError = e.localizedDescription }
            self.reconnectIfWanted()
        }
    }

    private func reconnectIfWanted() {
        guard autoReconnect else { state = .idle; return }
        let name = peripheral?.name ?? "wingSpan"
        state = .reconnecting(name)
        // Small delay so we don't spin if the Pi is off.
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
            self?.startScan()
        }
    }
}

// MARK: - Peripheral delegate

extension BLEManager: CBPeripheralDelegate {
    nonisolated func peripheral(_ peripheral: CBPeripheral,
                                didDiscoverServices error: Error?) {
        guard let svc = peripheral.services?.first(where: { $0.uuid == Self.serviceUUID })
        else { return }
        peripheral.discoverCharacteristics([Self.dataUUID, Self.cmdUUID], for: svc)
    }

    nonisolated func peripheral(_ peripheral: CBPeripheral,
                                didDiscoverCharacteristicsFor service: CBService,
                                error: Error?) {
        for c in service.characteristics ?? [] {
            if c.uuid == Self.dataUUID {
                Task { @MainActor in self.dataChar = c }
                peripheral.setNotifyValue(true, for: c)
                peripheral.readValue(for: c)
            } else if c.uuid == Self.cmdUUID {
                Task { @MainActor in self.cmdChar = c }
            }
        }
    }

    nonisolated func peripheral(_ peripheral: CBPeripheral,
                                didUpdateValueFor characteristic: CBCharacteristic,
                                error: Error?) {
        guard characteristic.uuid == Self.dataUUID, let data = characteristic.value
        else { return }
        do {
            let r = try JSONDecoder().decode(Reading.self, from: data)
            Task { @MainActor in self.reading = r }
        } catch {
            Task { @MainActor in
                self.lastError = "decode: \(error.localizedDescription)"
            }
        }
    }
}
