import SwiftUI

struct DiscoverView: View {
    @EnvironmentObject private var app: AppModel
    @State private var search = ""
    @State private var language = ""
    @State private var availableOnly = false
    @State private var profiles: [Interpreter] = []
    @State private var status = "Loading interpreters…"
    @State private var selection: Interpreter?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    TextField("Language, name, or specialty", text: $search)
                        .textFieldStyle(.roundedBorder)
                        .textInputAutocapitalization(.never)
                        .onSubmit { Task { await load() } }
                    HStack {
                        TextField("Language", text: $language)
                            .textFieldStyle(.roundedBorder)
                        Toggle("Available", isOn: $availableOnly)
                            .labelsHidden()
                        Text("Available").font(.subheadline)
                    }
                    Button("Search") { Task { await load() } }
                        .buttonStyle(.borderedProminent)
                    if profiles.isEmpty {
                        Text(status).foregroundStyle(.secondary)
                    } else {
                        ForEach(profiles) { profile in
                            Button { selection = profile } label: { profileCard(profile) }
                                .buttonStyle(.plain)
                        }
                    }
                }
                .padding(20)
            }
            .background(FiniTheme.mist)
            .navigationTitle("Find an interpreter")
            .sheet(item: $selection) { profile in
                InterpreterDetailView(profile: profile)
            }
            .task { await load() }
            .onChange(of: availableOnly) { Task { await load() } }
        }
    }

    private func profileCard(_ profile: Interpreter) -> some View {
        FiniCard {
            HStack(alignment: .top, spacing: 12) {
                AvatarView(name: profile.name)
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(profile.name).font(.headline)
                        if profile.verificationStatus == "verified" { Image(systemName: "checkmark.seal.fill").foregroundStyle(FiniTheme.blue) }
                    }
                    Text(profile.headline.isEmpty ? "Interpreter" : profile.headline).font(.subheadline).foregroundStyle(.secondary)
                    HStack(spacing: 8) {
                        if profile.rating > 0 { Text(String(format: "%.1f", profile.rating)) }
                        Text("\(profile.yearsExperience) years")
                        if profile.availableNow { Text("Available").foregroundStyle(.green) }
                    }
                    .font(.caption)
                }
                Spacer()
            }
        }
    }

    private func load() async {
        do {
            profiles = try await app.api.discover(language: language.trimmingCharacters(in: .whitespacesAndNewlines), availableNow: availableOnly, search: search)
            status = profiles.isEmpty ? "No interpreters match that search." : ""
        } catch {
            profiles = []
            status = error.localizedDescription
        }
    }
}

struct InterpreterDetailView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let profile: Interpreter
    @State private var detail: Interpreter?
    @State private var status = ""
    @State private var busy = false

    private var shown: Interpreter { detail ?? profile }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    HStack(spacing: 12) {
                        AvatarView(name: shown.name, size: 64)
                        VStack(alignment: .leading) {
                            Text(shown.name).font(.title2.weight(.bold))
                            Text(shown.headline).foregroundStyle(.secondary)
                        }
                    }
                    if !shown.bio.isEmpty { Text(shown.bio) }
                    tagRow("Languages", shown.languages + shown.dialects)
                    tagRow("Specialties", shown.specialties)
                    Text("\(shown.yearsExperience) years of experience")
                    if let label = shown.serviceLocation?.label, !label.isEmpty {
                        Text(label)
                    }
                    if shown.availableNow { Text("Available now").foregroundStyle(.green) }
                    if app.account == nil {
                        Text("Sign in to call this interpreter.").foregroundStyle(.secondary)
                    } else if app.account?.isInterpreter == true {
                        Text("Interpreter accounts cannot call other interpreters.").foregroundStyle(.secondary)
                    } else {
                        FiniButton(title: busy ? "Calling…" : "Call \(shown.name)", systemImage: "phone") { Task { await call() } }
                            .disabled(busy)
                    }
                    if !status.isEmpty { StatusBanner(text: status) }
                    if !shown.recentReviews.isEmpty {
                        Text("Reviews").font(.headline)
                        ForEach(shown.recentReviews) { review in
                            VStack(alignment: .leading, spacing: 4) {
                                Text("\(review.authorName) · \(review.rating)/5").font(.subheadline.weight(.semibold))
                                Text(review.text)
                            }
                        }
                    }
                }
                .padding(20)
            }
            .background(FiniTheme.mist)
            .navigationTitle("Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } } }
            .task { detail = try? await app.api.interpreter(id: profile.id) }
        }
    }

    @ViewBuilder
    private func tagRow(_ title: String, _ values: [String]) -> some View {
        if !values.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text(title).font(.headline)
                Text(values.joined(separator: " · "))
            }
        }
    }

    private func call() async {
        busy = true
        defer { busy = false }
        do {
            try await app.placeCall(receiverId: shown.id, purpose: "translator_chat")
            dismiss()
        } catch {
            status = error.localizedDescription
        }
    }
}
