import Foundation

/// Lightweight async REST client for the GreenTable backend.
final class APIClient {
    static let shared = APIClient()

    /// Update this to point at your Flask server.
    /// - iOS Simulator can reach `http://127.0.0.1:5050`.
    /// - On a physical device, replace with your Mac's LAN IP.
    var baseURL = URL(string: "http://127.0.0.1:5050")!

    var token: String?

    private let session: URLSession = .shared
    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        return d
    }()
    private let encoder: JSONEncoder = JSONEncoder()

    // MARK: Generic request

    enum Method: String { case GET, POST, PUT, DELETE }

    func request<T: Decodable>(
        _ path: String,
        method: Method = .GET,
        body: [String: Any]? = nil,
        query: [URLQueryItem]? = nil
    ) async throws -> T {
        var components = URLComponents(
            url: baseURL.appendingPathComponent(path),
            resolvingAgainstBaseURL: false
        )!
        components.queryItems = query

        var req = URLRequest(url: components.url!)
        req.httpMethod = method.rawValue
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = token {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body = body {
            req.httpBody = try JSONSerialization.data(withJSONObject: body, options: [])
        }

        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse else {
            throw APIError(error: "invalid server response")
        }

        if !(200..<300).contains(http.statusCode) {
            if let apiErr = try? decoder.decode(APIError.self, from: data) {
                throw apiErr
            }
            throw APIError(error: "HTTP \(http.statusCode)")
        }

        if T.self == EmptyResponse.self {
            return EmptyResponse() as! T
        }
        return try decoder.decode(T.self, from: data)
    }

    // MARK: Auth

    func register(name: String, email: String, password: String) async throws -> User {
        let resp: UserWrapper = try await request(
            "/users/register",
            method: .POST,
            body: ["name": name, "email": email, "password": password]
        )
        return resp.user
    }

    func login(email: String, password: String) async throws -> AuthResponse {
        let resp: AuthResponse = try await request(
            "/users/login",
            method: .POST,
            body: ["email": email, "password": password]
        )
        return resp
    }

    func searchUsers(query q: String) async throws -> [User] {
        let resp: UsersList = try await request(
            "/users/search",
            query: [URLQueryItem(name: "q", value: q)]
        )
        return resp.users
    }

    // MARK: Friends

    func listFriends() async throws -> FriendsResponse {
        try await request("/friends")
    }

    func sendFriendRequest(addresseeId: Int) async throws {
        let _: EmptyResponse = try await request(
            "/friends/request",
            method: .POST,
            body: ["addressee_id": addresseeId]
        )
    }

    func respondFriendship(id: Int, status: String) async throws {
        let _: EmptyResponse = try await request(
            "/friends/respond",
            method: .PUT,
            body: ["friendship_id": id, "status": status]
        )
    }

    // MARK: Locations

    func listLocations() async throws -> [DiningLocation] {
        let resp: LocationsResponse = try await request("/locations")
        return resp.locations
    }

    // MARK: Sessions

    func listSessions() async throws -> SessionsResponse {
        try await request("/sessions")
    }

    func createSession(
        locationId: Int,
        mealType: String,
        scheduledTime: Date,
        visibility: String,
        inviteeIds: [Int]
    ) async throws -> MealSession {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime]
        let body: [String: Any] = [
            "location_id": locationId,
            "meal_type": mealType,
            "scheduled_time": iso.string(from: scheduledTime),
            "visibility": visibility,
            "invitee_ids": inviteeIds
        ]
        let resp: SessionWrapper = try await request(
            "/sessions",
            method: .POST,
            body: body
        )
        return resp.session
    }

    func joinSession(id: Int) async throws -> MealSession {
        let resp: SessionWrapper = try await request(
            "/sessions/\(id)/join",
            method: .POST
        )
        return resp.session
    }

    func cancelSession(id: Int) async throws -> MealSession {
        let resp: SessionWrapper = try await request(
            "/sessions/\(id)",
            method: .DELETE
        )
        return resp.session
    }

    func deleteSessionPermanently(id: Int) async throws {
        let _: EmptyResponse = try await request(
            "/sessions/\(id)/permanent",
            method: .DELETE
        )
    }

    func leaveSession(id: Int) async throws -> MealSession {
        let resp: SessionWrapper = try await request(
            "/sessions/\(id)/leave",
            method: .POST
        )
        return resp.session
    }

    func updateSession(id: Int, fields: [String: Any]) async throws -> MealSession {
        let resp: SessionWrapper = try await request(
            "/sessions/\(id)",
            method: .PUT,
            body: fields
        )
        return resp.session
    }

    func respondInvitation(id: Int, status: String) async throws {
        let _: EmptyResponse = try await request(
            "/invitations/respond",
            method: .PUT,
            body: ["invitation_id": id, "status": status]
        )
    }
}

struct EmptyResponse: Decodable {}
