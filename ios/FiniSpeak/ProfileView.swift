import SwiftUI

struct ProfileView: View {
    @EnvironmentObject private var app: AppModel
    @State private var name = ""
    @State private var phone = ""
    @State private var status = ""
    @State private var interpreter: Interpreter?
    @State private var available = false
    @State private var loadedAvailability = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Account") {
                    Text(app.account?.email ?? "")
                    Text(app.account?.roleLabel ?? "")
                    TextField("Name", text: $name)
                    TextField("Phone", text: $phone).keyboardType(.phonePad)
                    Button("Save profile") { Task { await save() } }
                }
                Section("Interpreter") {
                    if let interpreter {
                        Text(interpreter.verificationStatus.isEmpty ? "Profile started" : interpreter.verificationStatus.replacingOccurrences(of: "_", with: " ").capitalized)
                        if !interpreter.languages.isEmpty { Text(interpreter.languages.joined(separator: ", ")) }
                        Toggle("Available now", isOn: $available)
                            .onChange(of: available) { _, value in
                                guard loadedAvailability else { return }
                                Task { await setAvailable(value) }
                            }
                    } else if app.account?.role == "translator" || app.account?.role == "translator_applicant" {
                        Text("Your interpreter profile is not available yet.")
                    } else {
                        Button("Join as an interpreter") { Task { await enroll() } }
                    }
                    Text("Credential documents and the full onboarding form stay on the FiniSpeak website. This phone uses the same account.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                Section {
                    NavigationLink("Server") { ServerSettings() }
                    Button("Sign out", role: .destructive) { Task { await app.signOut() } }
                }
                if !status.isEmpty { Section { Text(status) } }
            }
            .navigationTitle("Profile")
            .onAppear {
                name = app.account?.displayName ?? ""
                phone = app.account?.phone ?? ""
            }
            .task {
                await loadInterpreter()
                loadedAvailability = true
            }
        }
    }

    private func save() async {
        do {
            app.account = try await app.api.updateAccount(displayName: name.trimmingCharacters(in: .whitespacesAndNewlines), phone: phone.trimmingCharacters(in: .whitespacesAndNewlines))
            status = "Profile saved."
        } catch { status = error.localizedDescription }
    }

    private func loadInterpreter() async {
        guard app.account?.isInterpreter == true || app.account?.role == "admin" else { return }
        interpreter = try? await app.api.myInterpreterProfile()
        available = interpreter?.availableNow ?? false
    }

    private func setAvailable(_ value: Bool) async {
        do { try await app.api.updateAvailability(availableNow: value); status = value ? "You are available now." : "You are not available right now." }
        catch { status = error.localizedDescription }
    }

    private func enroll() async {
        do {
            interpreter = try await app.api.enrollInterpreter(phone: phone)
            app.account = try? await app.api.currentAccount()
            status = "Interpreter profile started. Finish credentials on the website, then sign in again."
        } catch { status = error.localizedDescription }
    }
}
