import SwiftUI

struct CreateSessionView: View {
    @State private var locations: [DiningLocation] = []
    @State private var friends: [User] = []
    @State private var selectedLocationId: Int?
    @State private var mealType: String = "lunch"
    @State private var scheduledTime: Date = Calendar.current.date(byAdding: .hour, value: 1, to: Date()) ?? Date()
    @State private var visibility: String = "open"
    @State private var selectedInvitees: Set<Int> = []
    @State private var loading = false
    @State private var errorText: String?
    @State private var successText: String?

    let mealTypes = ["breakfast", "lunch", "dinner"]
    let visibilities = ["open", "invite_only"]

    var body: some View {
        NavigationStack {
            Form {
                Section("Location") {
                    Picker("Dining hall", selection: $selectedLocationId) {
                        Text("Pick a location").tag(Optional<Int>.none)
                        ForEach(locations) { loc in
                            Text(loc.name).tag(Optional(loc.location_id))
                        }
                    }
                }

                Section("When") {
                    Picker("Meal", selection: $mealType) {
                        ForEach(mealTypes, id: \.self) { Text($0.capitalized).tag($0) }
                    }
                    DatePicker("Time",
                               selection: $scheduledTime,
                               in: Date()...,
                               displayedComponents: [.date, .hourAndMinute])
                }

                Section("Visibility") {
                    Picker("Who can join", selection: $visibility) {
                        Text("Open to friends").tag("open")
                        Text("Invite only").tag("invite_only")
                    }
                    .pickerStyle(.segmented)
                }

                if visibility == "invite_only" {
                    Section("Invite friends") {
                        if friends.isEmpty {
                            Text("Add friends first to invite them.")
                                .foregroundStyle(.secondary)
                        } else {
                            ForEach(friends) { f in
                                Button {
                                    if selectedInvitees.contains(f.user_id) {
                                        selectedInvitees.remove(f.user_id)
                                    } else {
                                        selectedInvitees.insert(f.user_id)
                                    }
                                } label: {
                                    HStack {
                                        VStack(alignment: .leading) {
                                            Text(f.name).foregroundStyle(.primary)
                                            Text(f.email).font(.caption).foregroundStyle(.secondary)
                                        }
                                        Spacer()
                                        if selectedInvitees.contains(f.user_id) {
                                            Image(systemName: "checkmark.circle.fill")
                                                .foregroundStyle(.green)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                if let errorText = errorText {
                    Section { Text(errorText).foregroundStyle(.red) }
                }
                if let successText = successText {
                    Section { Text(successText).foregroundStyle(.green) }
                }

                Section {
                    Button(action: submit) {
                        HStack {
                            if loading { ProgressView() }
                            Text("Create session").bold()
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .disabled(loading || selectedLocationId == nil)
                }
            }
            .navigationTitle("New session")
            .task { await loadInitial() }
        }
    }

    private func loadInitial() async {
        do {
            locations = try await APIClient.shared.listLocations()
            friends = try await APIClient.shared.listFriends().friends.map { $0.user }
        } catch {
            errorText = errorMsg(error)
        }
    }

    private func submit() {
        guard let locId = selectedLocationId else { return }
        loading = true
        errorText = nil
        successText = nil
        let invitees = visibility == "invite_only" ? Array(selectedInvitees) : []
        Task {
            do {
                let s = try await APIClient.shared.createSession(
                    locationId: locId,
                    mealType: mealType,
                    scheduledTime: scheduledTime,
                    visibility: visibility,
                    inviteeIds: invitees
                )
                successText = "Created \(s.meal_type) at \(s.location_name ?? "?")"
                selectedInvitees.removeAll()
            } catch {
                errorText = errorMsg(error)
            }
            loading = false
        }
    }
}
