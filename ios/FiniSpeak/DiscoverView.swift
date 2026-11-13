import SwiftUI

struct DiscoverView: View {
    @EnvironmentObject private var app: AppModel
    var embedded = false
    var preset = ""
    @State private var search = ""
    @State private var language = ""
    @State private var availableOnly = false
    @State private var profiles: [Interpreter] = []
    @State private var status = "Loading interpreters…"
    @State private var selection: Interpreter?
    private let chips = ["Spanish", "Legal", "Medical", "Available now"]

    var body: some View {
        ScrollView {
        VStack(alignment: .leading, spacing: 12) {
            TextField("Find a Translator by Language/Dialect", text: $search)
                .textInputAutocapitalization(.never)
                .padding(.horizontal, 16)
                .frame(minHeight: 46)
                .background(FiniTheme.search, in: Capsule())
                .onSubmit { Task { await load() } }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(chips, id: \.self) { chip in
                        Button {
                            if chip == "Available now" {
                                availableOnly.toggle()
                            } else {
                                search = chip
                                Task { await load() }
                            }
                        } label: {
                            Text(chip)
                                .font(.subheadline.weight(.bold))
                                .padding(.horizontal, 12)
                                .frame(minHeight: 40)
                                .background((chip == "Available now" ? availableOnly : search == chip) ? FiniTheme.blue : FiniTheme.chip, in: Capsule())
                                .foregroundStyle((chip == "Available now" ? availableOnly : search == chip) ? Color.white : FiniTheme.ink)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            if profiles.isEmpty {
                Text(status).foregroundStyle(.secondary)
            } else {
                ForEach(profiles) { profile in
                    Button { selection = profile } label: { profileCard(profile) }
                        .buttonStyle(.plain)
                }
            }
        }
        .padding(.horizontal, embedded ? 18 : 18)
        .padding(.bottom, 12)
        }
        .navigationTitle(embedded ? "" : "Find a Translator")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(item: $selection) { profile in
            InterpreterDetailView(profile: profile)
        }
        .task {
            if search.isEmpty, !preset.isEmpty { search = preset }
            await load()
        }
        .onChange(of: availableOnly) { Task { await load() } }
        .onChange(of: preset) {
            guard !preset.isEmpty, preset != search else { return }
            search = preset
            Task { await load() }
        }
    }

    private func profileCard(_ profile: Interpreter) -> some View {
        HStack(spacing: 12) {
            AvatarView(name: profile.name, size: 64)
            VStack(alignment: .leading, spacing: 3) {
                Text(profile.name).font(.headline).foregroundStyle(FiniTheme.ink)
                Text(profile.headline.isEmpty ? "Interpreter" : profile.headline).font(.subheadline).foregroundStyle(.secondary)
                HStack(spacing: 8) {
                    if profile.rating > 0 { Text(String(repeating: "★", count: min(5, Int(profile.rating.rounded())))).foregroundStyle(FiniTheme.star) }
                    Text("\(profile.yearsExperience) yrs")
                    if profile.availableNow { Text("Available").foregroundStyle(.green) }
                }
                .font(.caption.weight(.semibold))
            }
            Spacer(minLength: 0)
            if profile.verificationStatus == "verified" {
                Text("✓")
                    .font(.caption.weight(.heavy))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(FiniTheme.blue, in: Capsule())
            }
        }
        .padding(12)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(FiniTheme.line))
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
                    HStack(alignment: .center, spacing: 12) {
                        AvatarView(name: shown.name, size: 84)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(shown.name).font(.system(size: 28, weight: .heavy)).foregroundStyle(FiniTheme.ink)
                            if !shown.languages.isEmpty {
                                Text(shown.languages.joined(separator: " · "))
                                    .font(.caption.weight(.heavy))
                                    .foregroundStyle(.white)
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 3)
                                    .background(FiniTheme.blue, in: Capsule())
                            }
                            if shown.rating > 0 {
                                Text(String(repeating: "★", count: min(5, Int(shown.rating.rounded()))) + String(format: "  %.1f", shown.rating))
                                    .foregroundStyle(FiniTheme.star)
                                    .font(.subheadline.weight(.bold))
                            }
                            Text(shown.headline.isEmpty ? "Professional interpreter" : shown.headline).foregroundStyle(.secondary)
                        }
                    }
                    if shown.availableNow { Text("Available now").font(.subheadline.weight(.bold)).foregroundStyle(.green) }
                    if app.account == nil {
                        Text("Sign in to call this interpreter.").foregroundStyle(.secondary)
                    } else if app.account?.isInterpreter == true {
                        Text("Interpreter accounts cannot call other interpreters.").foregroundStyle(.secondary)
                    } else {
                        Button(busy ? "Calling…" : "Request Instant Call") { Task { await call() } }
                            .buttonStyle(ConceptFilledButtonStyle())
                            .disabled(busy)
                    }
                    if !status.isEmpty { StatusBanner(text: status) }
                    if !shown.bio.isEmpty {
                        Text("About").font(.subheadline.weight(.heavy)).foregroundStyle(FiniTheme.blue)
                        Text("Meet your interpreter").font(.title3.weight(.heavy))
                        Text(shown.bio)
                    }
                    tagRow("Languages", shown.languages + shown.dialects)
                    tagRow("Specialties", shown.specialties)
                    Text("\(shown.yearsExperience) years of experience")
                    if let label = shown.serviceLocation?.label, !label.isEmpty { Text(label) }
                    if !shown.recentReviews.isEmpty {
                        Text("Most recent reviews").font(.title3.weight(.heavy)).padding(.top, 8)
                        ForEach(shown.recentReviews) { review in
                            VStack(alignment: .leading, spacing: 4) {
                                Text("\(review.authorName) · \(review.rating)/5").font(.subheadline.weight(.semibold))
                                Text(review.text)
                            }
                            .padding(12)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(FiniTheme.field, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                        }
                    }
                }
                .padding(18)
            }
            .background(Color.white)
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
