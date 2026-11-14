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
    var onBack: (() -> Void)?
    var onManageFriends: (() -> Void)?
    @State private var digits = ""
    @State private var friendEmail = ""
    @State private var friendId = ""
    @State private var targetName = ""
    @State private var friends: [Friend] = []
    @State private var status = ""
    @State private var busy = false
    @State private var historyOpen = false
    @State private var editingFriends = false
    @State private var selectedCall: CallRecord?
    private let keys = [
        ("1", ""), ("2", "ABC"), ("3", "DEF"),
        ("4", "GHI"), ("5", "JKL"), ("6", "MNO"),
        ("7", "PQRS"), ("8", "TUV"), ("9", "WXYZ"),
        ("*", ""), ("0", ""), ("#", "")
    ]

    private var readout: String {
        digits.isEmpty ? "Dial a number" : formatted(digits)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Button {
                    if let onBack { onBack() } else { dismiss() }
                } label: {
                    Label("Back", systemImage: "chevron.left")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(FiniTheme.ink)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(FiniTheme.soft, in: Capsule())
                }
                .buttonStyle(.plain)
                ZStack {
                    Text(readout)
                        .font(.system(size: 22, weight: .bold))
                        .foregroundStyle(digits.isEmpty ? Color(red: 100 / 255, green: 116 / 255, blue: 139 / 255) : FiniTheme.ink)
                        .lineLimit(1)
                        .minimumScaleFactor(0.6)
                        .padding(.horizontal, 48)
                    HStack {
                        Spacer()
                        Button(action: backspace) {
                            Image(systemName: "delete.left")
                                .font(.system(size: 16, weight: .medium))
                                .foregroundStyle(FiniTheme.ink)
                                .frame(width: 40, height: 40)
                                .background(FiniTheme.soft, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Delete last digit")
                    }
                }
                .frame(maxWidth: .infinity)
                if !targetName.isEmpty {
                    Text(targetName)
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(FiniTheme.blue)
                        .frame(maxWidth: .infinity)
                        .multilineTextAlignment(.center)
                }
                LazyVGrid(columns: Array(repeating: GridItem(.fixed(72), spacing: 18), count: 3), spacing: 12) {
                    ForEach(keys, id: \.0) { key in
                        Button {
                            press(key.0)
                        } label: {
                            VStack(spacing: 1) {
                                Text(key.0)
                                    .font(.system(size: key.0 == "*" || key.0 == "#" ? 26 : 24, weight: .bold))
                                    .foregroundStyle(FiniTheme.ink)
                                if !key.1.isEmpty {
                                    Text(key.1)
                                        .font(.system(size: 9, weight: .heavy))
                                        .tracking(0.8)
                                        .foregroundStyle(Color(red: 100 / 255, green: 116 / 255, blue: 139 / 255))
                                }
                            }
                            .frame(width: 72, height: 72)
                            .background(FiniTheme.soft, in: Circle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(key.1.isEmpty ? key.0 : "\(key.0), \(key.1)")
                    }
                }
                .frame(maxWidth: .infinity)
                Button { Task { await start() } } label: {
                    Image(systemName: "phone.fill")
                        .font(.system(size: 26, weight: .semibold))
                        .foregroundStyle(.white)
                        .frame(width: 74, height: 74)
                        .background(FiniTheme.blue, in: Circle())
                        .shadow(color: FiniTheme.blue.opacity(0.28), radius: 10, y: 6)
                }
                .buttonStyle(.plain)
                .disabled(busy)
                .frame(maxWidth: .infinity)
                .accessibilityLabel("Start in-app call")
                Text("This starts a secure in-app call. It does not dial a cellular or landline number.")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: .infinity)
                if !status.isEmpty {
                    Text(status)
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(FiniTheme.ink)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                }
                HStack {
                    Text("Friends").font(.headline)
                    Spacer()
                    Button("Add or edit") {
                        if let onManageFriends { onManageFriends() } else { editingFriends = true }
                    }
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(FiniTheme.blue)
                }
                if friends.isEmpty {
                    Text("No friends yet. Add the people you call inside FiniSpeak.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(friends) { friend in
                        Button { select(friend) } label: { friendRow(friend) }
                            .buttonStyle(.plain)
                    }
                }
                Button { historyOpen.toggle() } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "arrowtriangle.right.fill")
                            .font(.system(size: 10, weight: .bold))
                            .rotationEffect(.degrees(historyOpen ? 90 : 0))
                        Text("Review recent conversations")
                            .font(.subheadline.weight(.bold))
                    }
                    .foregroundStyle(FiniTheme.blue)
                }
                .buttonStyle(.plain)
                if historyOpen {
                    if app.history.isEmpty {
                        Text("Calls you join will show up here.").foregroundStyle(.secondary)
                    } else {
                        ForEach(app.history.prefix(6)) { call in
                            Button { selectedCall = call } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(call.otherName(than: app.account?.uid ?? "")).font(.headline).foregroundStyle(FiniTheme.ink)
                                        Text(FiniTime.label(call.createdAt)).font(.subheadline).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    Text(call.language ?? "Call").font(.subheadline.weight(.semibold)).foregroundStyle(FiniTheme.ink)
                                }
                                .padding(12)
                                .background(Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                                .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(FiniTheme.line))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .padding(.horizontal, 18)
            .padding(.bottom, 16)
        }
        .background(Color.white)
        .sheet(isPresented: $editingFriends) { FriendsView() }
        .sheet(item: $selectedCall) { call in TranscriptHistoryView(call: call) }
        .task {
            friends = (try? await app.api.friends()) ?? []
            await app.refreshHistory()
        }
    }

    private func friendRow(_ friend: Friend) -> some View {
        let online = friend.online == true
        let detail = friend.savedPhone ?? friend.phone ?? friend.email ?? ""
        return HStack(spacing: 10) {
            AvatarView(name: friend.name, size: 40)
            VStack(alignment: .leading, spacing: 1) {
                Text(friend.name)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(FiniTheme.ink)
                    .lineLimit(1)
                Text("\(online ? "Online" : "Offline")\(detail.isEmpty ? "" : " · \(detail)")")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 8)
            Circle()
                .fill(online ? Color(red: 34 / 255, green: 163 / 255, blue: 90 / 255) : Color(red: 148 / 255, green: 163 / 255, blue: 184 / 255))
                .frame(width: 11, height: 11)
                .padding(4)
                .background(online ? Color(red: 220 / 255, green: 252 / 255, blue: 231 / 255) : Color(red: 226 / 255, green: 232 / 255, blue: 240 / 255), in: Circle())
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(FiniTheme.line))
    }

    private func press(_ key: String) {
        guard key.count == 1, key >= "0", key <= "9", digits.count < 15 else { return }
        friendEmail = ""
        friendId = ""
        targetName = ""
        digits.append(key)
    }

    private func backspace() {
        friendEmail = ""
        friendId = ""
        targetName = ""
        if !digits.isEmpty { digits.removeLast() }
    }

    private func select(_ friend: Friend) {
        friendEmail = ""
        friendId = friend.uid
        targetName = friend.name
        let raw = friend.savedPhone ?? friend.phone ?? ""
        let numbers = raw.filter(\.isNumber)
        if !numbers.isEmpty {
            if numbers.count == 11, numbers.hasPrefix("1") {
                digits = String(numbers.dropFirst())
            } else {
                digits = String(numbers.prefix(15))
            }
        } else if let email = friend.email, !email.isEmpty {
            digits = ""
            friendEmail = email
            targetName = "\(friend.name) · \(email)"
        }
    }

    private func formatted(_ value: String) -> String {
        let area = value.prefix(3)
        let prefix = value.dropFirst(3).prefix(3)
        let line = value.dropFirst(6).prefix(4)
        let extra = value.dropFirst(10)
        if value.count <= 3 { return String(area) }
        if value.count <= 6 { return "(\(area)) \(prefix)" }
        return "(\(area)) \(prefix)-\(line)\(extra)"
    }

    private func start() async {
        busy = true
        defer { busy = false }
        do {
            if !friendId.isEmpty {
                guard friendId != app.account?.uid else { status = "You cannot call yourself."; return }
                try await app.placeCall(receiverId: friendId)
                status = ""
                if onBack == nil { dismiss() }
                return
            }
            let email = friendEmail.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !email.isEmpty || !phoneCandidates.isEmpty else {
                status = "Dial a FiniSpeak number or choose a friend."
                return
            }
            let account: Account
            if !email.isEmpty {
                account = try await app.api.lookup(email: email, phone: nil)
            } else if let found = try await lookupDialedNumber() {
                account = found
            } else {
                status = "No FiniSpeak account was found with that number. Ask them to save it in their profile, then try again."
                return
            }
            guard account.uid != app.account?.uid else { status = "You cannot call yourself."; return }
            guard ["customer", "admin"].contains(account.role ?? "") else { status = "That account cannot receive a customer call. Open their interpreter profile to call them directly."; return }
            try await app.placeCall(receiverId: account.uid)
            status = ""
            if onBack == nil { dismiss() }
        } catch {
            status = error.localizedDescription
        }
    }

    private var phoneCandidates: [String] {
        let numbers = digits.filter(\.isNumber)
        guard (7...15).contains(numbers.count) else { return [] }
        var values = [numbers]
        if numbers.count == 10 { values.insert("1" + numbers, at: 0) }
        if numbers.count == 11, numbers.hasPrefix("1") { values.append(String(numbers.dropFirst())) }
        var seen = Set<String>()
        return values.filter { seen.insert($0).inserted }
    }

    private func lookupDialedNumber() async throws -> Account? {
        for candidate in phoneCandidates {
            do {
                return try await app.api.lookup(email: nil, phone: candidate)
            } catch let error as APIError where error.status == 404 {
                continue
            }
        }
        return nil
    }
}

struct CareersView: View {
    @EnvironmentObject private var app: AppModel
    var onProfile: () -> Void
    var onBusiness: () -> Void
    @State private var status = ""
    @State private var busy = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("Careers").font(.subheadline.weight(.heavy)).foregroundStyle(FiniTheme.blue)
                ConceptTitle(text: "Interpret with FiniSpeak")
                Text("Use a language you speak to help people in business, school, and everyday conversations.")
                    .foregroundStyle(.secondary)
                Button("Browse business sessions", action: onBusiness)
                    .buttonStyle(ConceptFilledButtonStyle())
                if app.account?.isInterpreter == true {
                    Button("Your interpreter profile", action: onProfile)
                        .buttonStyle(ConceptSoftButtonStyle())
                } else {
                    Button(busy ? "Starting…" : "Join as an interpreter") { Task { await enroll() } }
                        .buttonStyle(ConceptSoftButtonStyle())
                        .disabled(busy)
                }
                Text("Credential documents and the full onboarding form stay on the FiniSpeak website. This phone uses the same account.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                if !status.isEmpty { Text(status).font(.footnote).foregroundStyle(.secondary) }
            }
            .padding(.horizontal, 18)
            .padding(.bottom, 12)
        }
    }

    private func enroll() async {
        busy = true
        defer { busy = false }
        do {
            _ = try await app.api.enrollInterpreter(phone: app.account?.phone ?? "")
            status = "Interpreter profile started. Finish credentials on the website."
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
