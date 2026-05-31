import SwiftUI

struct AuthView: View {
    @EnvironmentObject var auth: AuthStore

    @State private var mode: Mode = .login
    @State private var name = ""
    @State private var email = ""
    @State private var password = ""
    @State private var loading = false
    @State private var errorText: String?

    enum Mode: String, CaseIterable, Identifiable {
        case login, register
        var id: String { rawValue }
        var label: String { self == .login ? "Log in" : "Register" }
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Spacer()
                Text("GreenTable")
                    .font(.largeTitle.bold())
                Text("Dartmouth dining, together")
                    .foregroundStyle(.secondary)

                Picker("Mode", selection: $mode) {
                    ForEach(Mode.allCases) { m in
                        Text(m.label).tag(m)
                    }
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)

                VStack(spacing: 12) {
                    if mode == .register {
                        TextField("Name", text: $name)
                            .textContentType(.name)
                            .textFieldStyle(.roundedBorder)
                    }
                    TextField("netid@dartmouth.edu", text: $email)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .textFieldStyle(.roundedBorder)
                    SecureField("Password", text: $password)
                        .textFieldStyle(.roundedBorder)
                }
                .padding(.horizontal)

                if let errorText = errorText {
                    Text(errorText)
                        .foregroundStyle(.red)
                        .font(.footnote)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                }

                Button(action: submit) {
                    HStack {
                        if loading { ProgressView().tint(.white) }
                        Text(mode.label).bold()
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.accentColor)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                }
                .padding(.horizontal)
                .disabled(loading)

                Spacer()
            }
            .padding(.vertical)
        }
    }

    private func submit() {
        errorText = nil
        let trimmedEmail = email.trimmingCharacters(in: .whitespaces).lowercased()
        guard trimmedEmail.hasSuffix("@dartmouth.edu") else {
            errorText = "Email must end with @dartmouth.edu"
            return
        }
        guard !password.isEmpty else {
            errorText = "Password is required"
            return
        }
        if mode == .register && name.trimmingCharacters(in: .whitespaces).isEmpty {
            errorText = "Name is required"
            return
        }

        loading = true
        Task {
            do {
                if mode == .register {
                    _ = try await APIClient.shared.register(name: name, email: trimmedEmail, password: password)
                }
                let resp = try await APIClient.shared.login(email: trimmedEmail, password: password)
                auth.login(token: resp.token, user: resp.user)
            } catch {
                errorText = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            }
            loading = false
        }
    }
}
