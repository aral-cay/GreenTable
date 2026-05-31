import SwiftUI

struct DashboardView: View {
    @EnvironmentObject var auth: AuthStore
    @State private var data: SessionsResponse?
    @State private var loading = false
    @State private var errorText: String?

    var body: some View {
        NavigationStack {
            Group {
                if loading && data == nil {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    List {
                        if let invitations = data?.invitations, !invitations.isEmpty {
                            Section("Pending Invitations") {
                                ForEach(invitations) { s in
                                    SessionRow(session: s, onAction: { refresh() })
                                }
                            }
                        }
                        Section("My sessions") {
                            ForEach(data?.created ?? []) { s in
                                SessionRow(session: s, onAction: { refresh() })
                            }
                            if (data?.created ?? []).isEmpty {
                                Text("None yet").foregroundStyle(.secondary)
                            }
                        }
                        Section("Joined") {
                            ForEach(data?.joined ?? []) { s in
                                SessionRow(session: s, onAction: { refresh() })
                            }
                            if (data?.joined ?? []).isEmpty {
                                Text("None yet").foregroundStyle(.secondary)
                            }
                        }
                        Section("Open sessions from friends") {
                            ForEach(data?.friends_open ?? []) { s in
                                SessionRow(session: s, onAction: { refresh() })
                            }
                            if (data?.friends_open ?? []).isEmpty {
                                Text("None right now").foregroundStyle(.secondary)
                            }
                        }
                        if let errorText = errorText {
                            Section { Text(errorText).foregroundStyle(.red) }
                        }
                    }
                    .listStyle(.insetGrouped)
                    .refreshable { await refreshAsync() }
                }
            }
            .navigationTitle("GreenTable")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        if let u = auth.user {
                            Text(u.email)
                        }
                        Button("Log out", role: .destructive) { auth.logout() }
                    } label: {
                        Image(systemName: "person.crop.circle")
                    }
                }
            }
            .task { await refreshAsync() }
        }
    }

    private func refresh() {
        Task { await refreshAsync() }
    }

    private func refreshAsync() async {
        loading = true
        errorText = nil
        do {
            data = try await APIClient.shared.listSessions()
        } catch {
            errorText = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
        loading = false
    }
}

// MARK: - Row

struct SessionRow: View {
    let session: MealSession
    let onAction: () -> Void

    @EnvironmentObject var auth: AuthStore
    @State private var busy = false
    @State private var rowError: String?
    @State private var showDeleteConfirm = false
    @State private var showLeaveConfirm = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(session.location_name ?? "Location")
                    .font(.headline)
                Spacer()
                Text(session.meal_type.capitalized)
                    .font(.caption)
                    .padding(.horizontal, 8).padding(.vertical, 3)
                    .background(.thinMaterial)
                    .clipShape(Capsule())
            }

            Text(formattedDate(session.scheduled_time))
                .font(.subheadline)

            HStack(spacing: 8) {
                Text("by \(session.creator_name ?? "Unknown")")
                Text("• \(session.participant_count) joined")
                Text("• \(session.visibility.replacingOccurrences(of: "_", with: " "))")
                if session.status != "active" {
                    Text("• \(session.status)").foregroundStyle(.red)
                }
            }
            .font(.caption)
            .foregroundStyle(.secondary)

            if let err = rowError {
                Text(err).foregroundStyle(.red).font(.caption)
            }

            HStack {
                if session.viewer_role == "invited",
                   let invId = session.invitation_id {
                    Button("Accept") { respondInvite(invId, "accepted") }
                        .buttonStyle(.borderedProminent)
                        .disabled(busy)
                    Button("Decline") { respondInvite(invId, "declined") }
                        .buttonStyle(.bordered)
                        .disabled(busy)
                } else if session.viewer_role == "friend_open" && session.status == "active" {
                    Button("Join") { join() }
                        .buttonStyle(.borderedProminent)
                        .disabled(busy)
                } else if session.viewer_role == "creator" && session.status == "active" {
                    Button(role: .destructive) { cancel() } label: { Text("Cancel session") }
                        .buttonStyle(.bordered)
                        .disabled(busy)
                } else if session.viewer_role == "creator" && session.status == "cancelled" {
                    Button(role: .destructive) { showDeleteConfirm = true } label: {
                        Label("Delete permanently", systemImage: "trash")
                    }
                    .buttonStyle(.bordered)
                    .disabled(busy)
                } else if session.viewer_role == "participant" && session.status == "active" {
                    Button(role: .destructive) { showLeaveConfirm = true } label: {
                        Text("Leave session")
                    }
                    .buttonStyle(.bordered)
                    .disabled(busy)
                }
            }
            .padding(.top, 4)
        }
        .padding(.vertical, 4)
        .confirmationDialog(
            "Delete this cancelled session? This cannot be undone.",
            isPresented: $showDeleteConfirm,
            titleVisibility: .visible
        ) {
            Button("Delete permanently", role: .destructive) { deletePermanently() }
            Button("Cancel", role: .cancel) {}
        }
        .confirmationDialog(
            "Leave this session?",
            isPresented: $showLeaveConfirm,
            titleVisibility: .visible
        ) {
            Button("Leave", role: .destructive) { leave() }
            Button("Stay", role: .cancel) {}
        }
    }

    private func join() {
        busy = true; rowError = nil
        Task {
            do {
                _ = try await APIClient.shared.joinSession(id: session.session_id)
                onAction()
            } catch { rowError = errorMsg(error) }
            busy = false
        }
    }

    private func cancel() {
        busy = true; rowError = nil
        Task {
            do {
                _ = try await APIClient.shared.cancelSession(id: session.session_id)
                onAction()
            } catch { rowError = errorMsg(error) }
            busy = false
        }
    }

    private func deletePermanently() {
        busy = true; rowError = nil
        Task {
            do {
                try await APIClient.shared.deleteSessionPermanently(id: session.session_id)
                onAction()
            } catch { rowError = errorMsg(error) }
            busy = false
        }
    }

    private func leave() {
        busy = true; rowError = nil
        Task {
            do {
                _ = try await APIClient.shared.leaveSession(id: session.session_id)
                onAction()
            } catch { rowError = errorMsg(error) }
            busy = false
        }
    }

    private func respondInvite(_ id: Int, _ status: String) {
        busy = true; rowError = nil
        Task {
            do {
                try await APIClient.shared.respondInvitation(id: id, status: status)
                onAction()
            } catch { rowError = errorMsg(error) }
            busy = false
        }
    }

    private func formattedDate(_ iso: String?) -> String {
        guard let iso = iso else { return "—" }
        let parsers: [ISO8601DateFormatter] = [{
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            return f
        }(), {
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withInternetDateTime]
            return f
        }()]
        var date: Date?
        for f in parsers {
            if let d = f.date(from: iso) { date = d; break }
        }
        if date == nil {
            let f = DateFormatter()
            f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
            date = f.date(from: iso)
        }
        guard let date = date else { return iso }
        let df = DateFormatter()
        df.dateStyle = .medium
        df.timeStyle = .short
        return df.string(from: date)
    }
}

func errorMsg(_ error: Error) -> String {
    (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
}
