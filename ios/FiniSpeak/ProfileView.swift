import SwiftUI

struct ProfileView: View {
    @EnvironmentObject private var app: AppModel
    var embedded = false
    @State private var name = ""
    @State private var phone = ""
    @State private var status = ""
    @State private var interpreter: Interpreter?
    @State private var available = false
    @State private var loadedAvailability = false

    var body: some View {
        ScrollView {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 12) {
                AvatarView(name: app.account?.name ?? "FiniSpeak", size: 72)
                VStack(alignment: .leading, spacing: 4) {
                    Text(app.account?.name ?? "Profile").font(.system(size: 28, weight: .heavy)).foregroundStyle(FiniTheme.ink)
                    Text(app.account?.roleLabel ?? "").foregroundStyle(.secondary)
                    Text(app.account?.email ?? "").font(.footnote).foregroundStyle(.secondary)
                }
            }
            ConceptField(title: "Name", text: $name, contentType: .name)
            ConceptField(title: "Phone", text: $phone, keyboard: .phonePad, contentType: .telephoneNumber)
            Button("Save profile") { Task { await save() } }
                .buttonStyle(ConceptFilledButtonStyle())
            if let interpreter {
                Text(interpreter.verificationStatus.isEmpty ? "Profile started" : interpreter.verificationStatus.replacingOccurrences(of: "_", with: " ").capitalized)
                    .font(.headline)
                if !interpreter.languages.isEmpty { Text(interpreter.languages.joined(separator: ", ")).foregroundStyle(.secondary) }
                Toggle("Available now", isOn: $available)
                    .onChange(of: available) { _, value in
                        guard loadedAvailability else { return }
                        Task { await setAvailable(value) }
                    }
            } else if app.account?.role == "translator" || app.account?.role == "translator_applicant" {
                Text("Your interpreter profile is not available yet.").foregroundStyle(.secondary)
            } else {
                Button("Join as an interpreter") { Task { await enroll() } }
                    .buttonStyle(ConceptSoftButtonStyle())
            }
            Text("Credential documents and the full onboarding form stay on the FiniSpeak website. This phone uses the same account.")
                .font(.footnote)
                .foregroundStyle(.secondary)
            if !embedded {
                NavigationLink("Server") { ServerSettings() }
            }
            Button("Sign out") { Task { await app.signOut() } }
                .font(.body.weight(.bold))
                .foregroundStyle(.red)
            if !status.isEmpty { Text(status).font(.footnote) }
        }
        .padding(.horizontal, 18)
        .padding(.bottom, 12)
        }
        .navigationTitle(embedded ? "" : "Profile")
        .onAppear {
            name = app.account?.displayName ?? ""
            phone = app.account?.phone ?? ""
        }
        .task {
            await loadInterpreter()
            loadedAvailability = true
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
        let availability = interpreter?.availability
        do {
            try await app.api.updateAvailability(availableNow: value, days: availability?.days ?? [], start: availability?.start ?? "", end: availability?.end ?? "")
            status = value ? "You are available now." : "You are not available right now."
        }
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
