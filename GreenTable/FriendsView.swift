import SwiftUI

struct FriendsView: View {
    @State private var data: FriendsResponse?
    @State private var searchText = ""
    @State private var searchResults: [User] = []
    @State private var loading = false
    @State private var errorText: String?

    var body: some View {
        NavigationStack {
            List {
                Section("Find Dartmouth users") {
                    TextField("Search by name or email", text: $searchText)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .onSubmit { Task { await runSearch() } }
                    if !searchResults.isEmpty {
                        ForEach(searchResults) { u in
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(u.name).font(.body)
                                    Text(u.email).font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Button("Add") { sendRequest(to: u.user_id) }
                                    .buttonStyle(.borderedProminent)
                                    .controlSize(.small)
                            }
                        }
                    }
                }

                if let incoming = data?.incoming_requests, !incoming.isEmpty {
                    Section("Incoming requests") {
                        ForEach(incoming) { f in
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(f.user.name).font(.body)
                                    Text(f.user.email).font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Button("Accept") { respond(f.friendship_id, "accepted") }
                                    .buttonStyle(.borderedProminent)
                                    .controlSize(.small)
                                Button("Decline") { respond(f.friendship_id, "declined") }
                                    .buttonStyle(.bordered)
                                    .controlSize(.small)
                            }
                        }
                    }
                }

                Section("Friends") {
                    if let friends = data?.friends, !friends.isEmpty {
                        ForEach(friends) { f in
                            VStack(alignment: .leading) {
                                Text(f.user.name)
                                Text(f.user.email).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    } else {
                        Text("No friends yet").foregroundStyle(.secondary)
                    }
                }

                if let outgoing = data?.outgoing_requests, !outgoing.isEmpty {
                    Section("Pending (sent)") {
                        ForEach(outgoing) { f in
                            VStack(alignment: .leading) {
                                Text(f.user.name)
                                Text(f.user.email).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }

                if let errorText = errorText {
                    Section { Text(errorText).foregroundStyle(.red) }
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Friends")
            .refreshable { await refresh() }
            .task { await refresh() }
        }
    }

    private func refresh() async {
        loading = true; errorText = nil
        do {
            data = try await APIClient.shared.listFriends()
        } catch { errorText = errorMsg(error) }
        loading = false
    }

    private func runSearch() async {
        let q = searchText.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { searchResults = []; return }
        do {
            searchResults = try await APIClient.shared.searchUsers(query: q)
        } catch { errorText = errorMsg(error) }
    }

    private func sendRequest(to userId: Int) {
        Task {
            do {
                try await APIClient.shared.sendFriendRequest(addresseeId: userId)
                await refresh()
            } catch { errorText = errorMsg(error) }
        }
    }

    private func respond(_ id: Int, _ status: String) {
        Task {
            do {
                try await APIClient.shared.respondFriendship(id: id, status: status)
                await refresh()
            } catch { errorText = errorMsg(error) }
        }
    }
}
