import Foundation

struct AnyStringKey: CodingKey {
    var stringValue: String
    var intValue: Int? { nil }
    init?(stringValue: String) { self.stringValue = stringValue }
    init?(intValue: Int) { nil }
    init(_ s: String) { self.stringValue = s }
}

extension KeyedDecodingContainer where Key == AnyStringKey {
    func firstString(_ names: [String]) -> String? {
        for name in names {
            let key = AnyStringKey(name)
            if let v = try? decodeIfPresent(String.self, forKey: key), !v.isEmpty { return v }
        }
        return nil
    }

    func firstInt(_ names: [String]) -> Int? {
        for name in names {
            let key = AnyStringKey(name)
            if let v = try? decodeIfPresent(Int.self, forKey: key) { return v }
        }
        return nil
    }

    func firstDecodable<T: Decodable>(_ type: T.Type, _ names: [String]) -> T? {
        for name in names {
            let key = AnyStringKey(name)
            if let v = try? decodeIfPresent(T.self, forKey: key) { return v }
        }
        return nil
    }
}

extension KeyedEncodingContainer where Key == AnyStringKey {
    mutating func encodeIfPresent<T: Encodable>(_ value: T?, name: String) throws {
        try encodeIfPresent(value, forKey: AnyStringKey(name))
    }
}
