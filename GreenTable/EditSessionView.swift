import SwiftUI

struct EditSessionView: View {
    let session: MealSession
    let onSave: () -> Void

    @Environment(\.dismiss) private var dismiss

    // Form fields
    @State private var locations: [DiningLocation] = []
    @State private var selectedLocationId: Int? = nil
    @State private var mealType: String = "lunch"
    @State private var scheduledTime: Date = Date()
    @State private var visibility: String = "open"

    // Invitations for this session, loaded from GET /sessions/{id}/invitations
    // Shown when visibility is invite_only
    @State private var invitations: [Invitation] = []

    // UI state
    @State private var loading = false
    @State private var errorText: String? = nil

    let mealTypes = ["breakfast", "lunch", "dinner"]

    var body: some View {
        NavigationStack {
            Form {

                // Location section
                // populated from GET /locations
                Section("Location") {
                    Picker("Dining hall", selection: $selectedLocationId) {
                        Text("Pick a location").tag(Optional<Int>.none)
                        ForEach(locations) { loc in
                            Text(loc.name).tag(Optional(loc.location_id))
                        }
                    }
                }

                // Time section
                Section("When") {
                    Picker("Meal", selection: $mealType) {
                        ForEach(mealTypes, id: \.self) { type in
                            Text(type.capitalized).tag(type)
                        }
                    }
                    DatePicker(
                        "Time",
                        selection: $scheduledTime,
                        in: Date()...,
                        displayedComponents: [.date, .hourAndMinute]
                    )
                }

                // Visibility section
                Section("Visibility") {
                    Picker("Who can join", selection: $visibility) {
                        Text("Open to friends").tag("open")
                        Text("Invite only").tag("invite_only")
                    }
                    .pickerStyle(.segmented)
                }

                // Invitations section
                // Lists everyone who was invited and lets the creator deletepending ones
                if visibility == "invite_only" {
                    Section("Invitations") {
                        if invitations.isEmpty {
                            Text("No invitations sent yet.").foregroundStyle(.secondary)
                        } else {
                            ForEach(invitations) { inv in
                                HStack {
                                    VStack(alignment: .leading) {
                                        Text(inv.invitee.name)
                                        // Show the current status (pending / accepted / declined)
                                        Text(inv.status.capitalized)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    // Show revoke for pending invitations
                                    if inv.status == "pending" {
                                        Button("Revoke") { revokeInvitation(inv.invitation_id) }
                                            .buttonStyle(.bordered)
                                            .controlSize(.small)
                                            .tint(.red)
                                            .disabled(loading)
                                    }
                                }
                            }
                        }
                    }
                }

                // Error message
                if let errorText = errorText {
                    Section {
                        Text(errorText).foregroundStyle(.red)
                    }
                }

                // Save button
                Section {
                    Button(action: saveChanges) {
                        HStack {
                            if loading { ProgressView() }
                            Text("Save changes").bold()
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .disabled(loading || selectedLocationId == nil)
                }
            }
            .navigationTitle("Edit session")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                        .disabled(loading)
                }
            }
            .task {
                await loadData()
            }
        }
    }

    // Load dining locations, pre-fill form fields, and fetch invitations
    private func loadData() async {
        do {
            locations = try await APIClient.shared.listLocations()
        } catch {
            errorText = errorMsg(error)
        }

        // Pre-fill every field with the session's values
        selectedLocationId = session.location_id
        mealType           = session.meal_type
        visibility         = session.visibility

        // Convert back to Date for the DatePicker.
        if let parsedDate = parseDate(session.scheduled_time), parsedDate > Date() {
            scheduledTime = parsedDate
        } else {
            scheduledTime = Calendar.current.date(byAdding: .hour, value: 1, to: Date()) ?? Date()
        }

        // Load invitations if this is an invite_only session
        if session.visibility == "invite_only" {
            do {
                invitations = try await APIClient.shared.listInvitations(sessionId: session.session_id)
            } catch {
                errorText = errorMsg(error)
            }
        }
    }

    // Date parsing helper
    // The backend returns scheduled_time as "2026-06-01T18:30:00" 
    // Try multiple formats to be safe
    private func parseDate(_ isoString: String?) -> Date? {
        guard let isoString = isoString else { return nil }

        // Try with fractional seconds
        let formatterA = ISO8601DateFormatter()
        formatterA.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatterA.date(from: isoString) { return date }

        // Try without fractional seconds
        let formatterB = ISO8601DateFormatter()
        formatterB.formatOptions = [.withInternetDateTime]
        if let date = formatterB.date(from: isoString) { return date }

        // Try plain "yyyy-MM-dd'T'HH:mm:ss"
        let formatterC = DateFormatter()
        formatterC.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return formatterC.date(from: isoString)
    }

    // Send PUT /sessions/{id} with the updated fields
    private func saveChanges() {
        guard let locId = selectedLocationId else { return }

        loading = true
        errorText = nil

        // Format the chosen date as ISO 8601 for the backend
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]

        let fields: [String: Any] = [
            "location_id":    locId,
            "meal_type":      mealType,
            "scheduled_time": formatter.string(from: scheduledTime),
            "visibility":     visibility
        ]

        Task {
            do {
                _ = try await APIClient.shared.updateSession(id: session.session_id, fields: fields)
                onSave()   
                dismiss()  
            } catch {
                errorText = errorMsg(error)
            }
            loading = false
        }
    }

    // Send DELETE /invitations/{id} then reload the invitations list
    private func revokeInvitation(_ invitationId: Int) {
        loading = true
        errorText = nil

        Task {
            do {
                try await APIClient.shared.revokeInvitation(id: invitationId)

                // Reload the invitations list 
                invitations = try await APIClient.shared.listInvitations(sessionId: session.session_id)
            } catch {
                errorText = errorMsg(error)
            }
            loading = false
        }
    }
}
