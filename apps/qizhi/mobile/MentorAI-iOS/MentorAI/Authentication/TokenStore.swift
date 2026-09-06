import Foundation
import Security
import os

struct TokenStore {
    var load: () -> AuthSession?
    var save: (AuthSession) -> Void
    var clear: () -> Void

    static let keychain: TokenStore = .keychain(
        service: "com.mentorai.app.auth",
        account: "currentSession"
    )

    static let ephemeral: TokenStore = {
        var storage: AuthSession?
        return TokenStore(
            load: { storage },
            save: { storage = $0 },
            clear: { storage = nil }
        )
    }()

    static func keychain(service: String, account: String) -> TokenStore {
        let log = Logger(subsystem: "com.mentorai.app", category: "TokenStore")
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .custom { date, encoder in
            var container = encoder.singleValueContainer()
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            try container.encode(f.string(from: date))
        }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(String.self)
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let d = f.date(from: raw) { return d }
            f.formatOptions = [.withInternetDateTime]
            if let d = f.date(from: raw) { return d }
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Invalid ISO8601 date: \(raw)")
        }

        let baseQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]

        return TokenStore(
            load: {
                var query = baseQuery
                query[kSecMatchLimit as String] = kSecMatchLimitOne
                query[kSecReturnData as String] = true
                var item: AnyObject?
                let status = SecItemCopyMatching(query as CFDictionary, &item)
                guard status == errSecSuccess, let data = item as? Data else {
                    if status == errSecItemNotFound {
                        log.info("No saved session in Keychain")
                    } else {
                        log.warning("Keychain load status=\(status, privacy: .public)")
                    }
                    return nil
                }
                guard let session = try? decoder.decode(AuthSession.self, from: data) else {
                    log.error("Failed to decode saved session; clearing it")
                    SecItemDelete(baseQuery as CFDictionary)
                    return nil
                }
                log.info("Restored session from Keychain (token length=\(session.accessToken.count))")
                return session
            },
            save: { session in
                guard let data = try? encoder.encode(session) else {
                    log.error("Failed to encode session for Keychain")
                    return
                }
                let attributes: [String: Any] = [
                    kSecValueData as String: data,
                    kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
                ]
                let updateStatus = SecItemUpdate(baseQuery as CFDictionary, attributes as CFDictionary)
                if updateStatus == errSecSuccess {
                    log.info("Updated session in Keychain")
                    return
                }
                if updateStatus == errSecItemNotFound {
                    var newItem = baseQuery
                    newItem.merge(attributes) { _, new in new }
                    let addStatus = SecItemAdd(newItem as CFDictionary, nil)
                    if addStatus == errSecSuccess {
                        log.info("Added new session to Keychain")
                    } else {
                        log.error("SecItemAdd failed status=\(addStatus, privacy: .public)")
                    }
                } else {
                    log.error("SecItemUpdate failed status=\(updateStatus, privacy: .public)")
                }
            },
            clear: {
                let status = SecItemDelete(baseQuery as CFDictionary)
                if status == errSecSuccess {
                    log.info("Cleared Keychain session")
                } else if status != errSecItemNotFound {
                    log.warning("Keychain clear status=\(status, privacy: .public)")
                }
            }
        )
    }
}
