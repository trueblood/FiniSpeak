import SwiftUI

struct HomeView: View {
    @EnvironmentObject private var app: AppModel
    var onFind: () -> Void
    var onLesson: () -> Void
    var onCall: () -> Void
    @Binding var category: String
    var onCategory: (String) -> Void
    @State private var selectedCall: CallRecord?

    var body: some View {
        ScrollView {
        VStack(alignment: .leading, spacing: 0) {
            ConceptHub(category: $category, onCategory: onCategory, onFind: onFind, onLesson: onLesson, onCall: onCall, joinTitle: nil, onJoin: nil)
            DisclosureGroup("Review recent conversations") {
                if app.history.isEmpty {
                    Text("Calls you join will show up here.").foregroundStyle(.secondary).padding(.top, 8)
                } else {
                    VStack(spacing: 8) {
                        ForEach(app.history.prefix(8)) { call in
                            Button { selectedCall = call } label: { callRow(call) }
                                .buttonStyle(.plain)
                        }
                    }
                    .padding(.top, 8)
                }
            }
            .font(.subheadline.weight(.bold))
            .foregroundStyle(FiniTheme.blue)
            .padding(.top, 18)
        }
        .padding(.horizontal, 18)
        .padding(.bottom, 12)
        }
        .sheet(item: $selectedCall) { call in TranscriptHistoryView(call: call) }
        .task { await app.refreshHistory() }
    }

    private func callRow(_ call: CallRecord) -> some View {
        FiniCard {
            HStack {
                AvatarView(name: call.otherName(than: app.account?.uid ?? ""), size: 42)
                VStack(alignment: .leading, spacing: 2) {
                    Text(call.otherName(than: app.account?.uid ?? "")).font(.headline)
                    Text([call.status, call.language, FiniTime.label(call.createdAt)].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }
        }
    }
}

struct DialView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var email = ""
    @State private var phone = ""
    @State private var friends: [Friend] = []
    @State private var status = ""
    @State private var busy = false

    var body: some View {
        NavigationStack {
            Form {
                Section("FiniSpeak account") {
                    TextField("Email", text: $email)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.emailAddress)
                        .autocorrectionDisabled()
                    TextField("Or phone number", text: $phone)
                        .keyboardType(.phonePad)
                }
                if !friends.isEmpty {
                    Section("Friends") {
                        ForEach(friends) { friend in
                            Button(friend.name) {
                                email = friend.email ?? ""
                                phone = friend.savedPhone ?? friend.phone ?? ""
                            }
                        }
                    }
                }
                if !status.isEmpty { Text(status) }
                Section { Button(busy ? "Calling…" : "Start call") { Task { await start() } }.disabled(busy) }
            }
            .navigationTitle("Call")
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } } }
            .task { friends = (try? await app.api.friends()) ?? [] }
        }
    }

    private func start() async {
        busy = true
        defer { busy = false }
        do {
            let lookupEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
            let lookupPhone = phone.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !lookupEmail.isEmpty || !lookupPhone.isEmpty else { status = "Enter an email or phone number."; return }
            let account = try await app.api.lookup(email: lookupEmail.isEmpty ? nil : lookupEmail, phone: lookupPhone.isEmpty ? nil : lookupPhone)
            guard account.uid != app.account?.uid else { status = "You cannot call yourself."; return }
            guard ["customer", "admin"].contains(account.role ?? "") else { status = "That account cannot receive a customer call. Open their interpreter profile to call them directly."; return }
            try await app.placeCall(receiverId: account.uid)
            dismiss()
        } catch {
            status = error.localizedDescription
        }
    }
}

struct TranscriptHistoryView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let call: CallRecord
    @State private var lines: [TranscriptLine] = []
    @State private var status = "Loading transcript…"

    var body: some View {
        NavigationStack {
            Group {
                if lines.isEmpty {
                    Text(status).foregroundStyle(.secondary).padding()
                } else {
                    List(lines) { line in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(line.speakerName ?? "Speaker").font(.caption.weight(.semibold))
                            Text(line.text)
                            if let created = line.createdAt { Text(FiniTime.label(created)).font(.caption2).foregroundStyle(.secondary) }
                        }
                    }
                }
            }
            .navigationTitle(call.otherName(than: app.account?.uid ?? ""))
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } } }
            .task { await load() }
        }
    }

    private func load() async {
        do {
            lines = try await app.api.transcripts(callId: call.id)
            status = lines.isEmpty ? "No transcript was saved for this call." : ""
        } catch {
            status = error.localizedDescription
        }
    }
}
