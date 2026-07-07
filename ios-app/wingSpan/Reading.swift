import Foundation

/// One JSON payload from the Pi's DATA characteristic.
///
/// Fields are all optional so a single decoder handles both the
/// pre-load-cell firmware and the post-load-cell firmware that adds
/// `w_legs`, `bat`, and `conn`.
struct Reading: Codable, Equatable {
    let t:  Double?
    let h:  Double?
    let db: Double?
    let w:  Double?
    let bands:  [String: Double]?
    let events: [String]?
    let wLegs:  [String: Double?]?
    let bat:    [String: Int?]?
    let conn:   [String: Bool]?
    let ts:     TimeInterval?

    enum CodingKeys: String, CodingKey {
        case t, h, db, w, bands, events, ts
        case wLegs = "w_legs"
        case bat, conn
    }
}

extension Reading {
    static let empty = Reading(t: nil, h: nil, db: nil, w: nil,
                               bands: nil, events: nil,
                               wLegs: nil, bat: nil, conn: nil, ts: nil)
}
