import Foundation
import SwiftUI
import Combine

/// Holds the signed-in user and JWT token. Token is persisted in UserDefaults
/// for the demo (good enough for a class project; use Keychain in real apps).
@MainActor
final class AuthStore: ObservableObject {
    @Published var token: String?
    @Published var user: User?
    
    var isAuthenticated: Bool {
        token != nil
    }

    private let tokenKey = "gt.token"
    private let userKey = "gt.user"

    init() {
        if let saved = UserDefaults.standard.string(forKey: tokenKey) {
            self.token = saved
            APIClient.shared.token = saved
        }
        if let data = UserDefaults.standard.data(forKey: userKey),
           let decoded = try? JSONDecoder().decode(User.self, from: data) {
            self.user = decoded
        }
    }

    func login(token: String, user: User) {
        self.token = token
        self.user = user
        APIClient.shared.token = token
        UserDefaults.standard.set(token, forKey: tokenKey)
        if let data = try? JSONEncoder().encode(user) {
            UserDefaults.standard.set(data, forKey: userKey)
        }
    }

    func logout() {
        token = nil
        user = nil
        APIClient.shared.token = nil
        UserDefaults.standard.removeObject(forKey: tokenKey)
        UserDefaults.standard.removeObject(forKey: userKey)
    }
}
