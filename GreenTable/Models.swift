import Foundation

// MARK: - Users

struct User: Codable, Identifiable, Hashable {
    let user_id: Int
    let name: String
    let email: String
    let created_at: String?

    var id: Int { user_id }
}

struct AuthResponse: Codable {
    let token: String
    let user: User
}

struct UserWrapper: Codable {
    let user: User
}

struct UsersList: Codable {
    let users: [User]
}

// MARK: - Friends

struct Friendship: Codable, Identifiable, Hashable {
    let friendship_id: Int
    let status: String
    let created_at: String?
    let user: User

    var id: Int { friendship_id }
}

struct FriendsResponse: Codable {
    let friends: [Friendship]
    let incoming_requests: [Friendship]
    let outgoing_requests: [Friendship]
}

// MARK: - Locations

struct DiningLocation: Codable, Identifiable, Hashable {
    let location_id: Int
    let name: String
    let address: String?

    var id: Int { location_id }
}

struct LocationsResponse: Codable {
    let locations: [DiningLocation]
}

// MARK: - Sessions

struct MealSession: Codable, Identifiable, Hashable {
    let session_id: Int
    let creator_id: Int
    let creator_name: String?
    let location_id: Int
    let location_name: String?
    let meal_type: String
    let scheduled_time: String?
    let visibility: String
    let status: String
    let participant_count: Int
    let created_at: String?
    let viewer_role: String?
    let invitation_id: Int?
    let invitation_status: String?

    var id: Int { session_id }
}

struct SessionsResponse: Codable {
    let sessions: [MealSession]
    let created: [MealSession]
    let joined: [MealSession]
    let friends_open: [MealSession]
    let invitations: [MealSession]
}

struct SessionWrapper: Codable {
    let session: MealSession
}

// MARK: - Errors

struct APIError: Codable, Error, LocalizedError {
    let error: String
    var errorDescription: String? { error }
}
