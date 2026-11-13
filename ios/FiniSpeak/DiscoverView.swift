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
        .fullScreenCover(item: $selection) { profile in
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
    @Environment(\.goHome) private var goHome
    let profile: Interpreter
    @State private var detail: Interpreter?
    @State private var status = ""
    @State private var busy = false
    @State private var category = "Education"
    @State private var chat: Conversation?
    @State private var dial = false

    private var shown: Interpreter { detail ?? profile }
    private var languageBadges: [String] { Array((shown.languages + shown.dialects).filter { !$0.isEmpty }.prefix(3)) }
    private var specialtyLine: String {
        let specialties = shown.specialties.filter { !$0.isEmpty }
        if !specialties.isEmpty { return specialties.prefix(2).joined(separator: ", ") }
        let languages = shown.languages.filter { !$0.isEmpty }
        return languages.isEmpty ? "Professional interpreter" : languages.prefix(2).joined(separator: ", ")
    }
    private var sessionTime: String {
        let start = shown.availability.start
        let end = shown.availability.end
        guard !start.isEmpty, !end.isEmpty else { return "11:00 AM – 12:00 PM" }
        return "\(Self.clock(start)) – \(Self.clock(end))"
    }
    private var slotDetail: String {
        let detail = (shown.specialties + shown.languages).filter { !$0.isEmpty }
        return detail.isEmpty ? "Live session" : detail.prefix(2).joined(separator: ", ")
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                ConceptBrandButton {
                    goHome()
                    dismiss()
                }
                Spacer()
                ConceptRoundButton(systemImage: "magnifyingglass") { dismiss() }
            }
            .padding(.horizontal, 16)
            .padding(.top, 8)
            .padding(.bottom, 4)
            Button { dismiss() } label: {
                Label("Back to interpreters", systemImage: "chevron.left")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(FiniTheme.ink)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(FiniTheme.soft, in: Capsule())
            }
            .buttonStyle(.plain)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 18)
            .padding(.bottom, 6)
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    HStack(alignment: .top, spacing: 12) {
                        ProfilePhoto(name: shown.name, url: photoURL, size: 84)
                        VStack(alignment: .leading, spacing: 6) {
                            Text(shown.name)
                                .font(.system(size: 28, weight: .heavy))
                                .foregroundStyle(FiniTheme.ink)
                                .fixedSize(horizontal: false, vertical: true)
                            if shown.verificationStatus == "verified" {
                                Label("Verified", systemImage: "checkmark")
                                    .font(.system(size: 12, weight: .heavy))
                                    .foregroundStyle(.white)
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 3)
                                    .background(FiniTheme.blue, in: Capsule())
                            }
                            if !languageBadges.isEmpty {
                                FlowRows(spacing: 6) {
                                    ForEach(languageBadges, id: \.self) { badge in
                                        Text(badge)
                                            .font(.system(size: 12, weight: .heavy))
                                            .foregroundStyle(.white)
                                            .padding(.horizontal, 8)
                                            .padding(.vertical, 3)
                                            .background(FiniTheme.blue, in: Capsule())
                                    }
                                }
                            }
                            HStack(spacing: 6) {
                                Text(stars).foregroundStyle(FiniTheme.star)
                                Text(shown.rating > 0 ? String(format: "%.1f", shown.rating) : "New")
                                    .font(.subheadline.weight(.heavy))
                                    .foregroundStyle(FiniTheme.ink)
                            }
                            .font(.subheadline)
                            Text(specialtyLine)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(Color(red: 51 / 255, green: 65 / 255, blue: 85 / 255))
                        }
                    }
                    weekRow
                    HStack(spacing: 12) {
                        ProfilePhoto(name: shown.name, url: photoURL, size: 44)
                        Image(systemName: "calendar")
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundStyle(Color(red: 100 / 255, green: 116 / 255, blue: 139 / 255))
                        VStack(alignment: .leading, spacing: 1) {
                            Text(sessionTime).font(.body.weight(.bold)).foregroundStyle(FiniTheme.ink)
                            Text(slotDetail).font(.subheadline.weight(.semibold)).foregroundStyle(.secondary)
                        }
                    }
                    actions
                    if !status.isEmpty { Text(status).font(.footnote).foregroundStyle(FiniTheme.ink) }
                    sectionTitle("About", "Meet your interpreter")
                    Text(shown.bio.isEmpty ? "This interpreter has not added a professional bio yet." : shown.bio)
                        .foregroundStyle(Color(red: 51 / 255, green: 65 / 255, blue: 85 / 255))
                    sectionTitle("Expertise", "Languages and specialties")
                    tagGroup("Languages", shown.languages + shown.dialects)
                    tagGroup("Specialties", shown.specialties)
                    sectionTitle("Community feedback", "Most recent reviews")
                    if shown.recentReviews.isEmpty {
                        Text("No reviews yet. Completed customer reviews will appear here.").foregroundStyle(.secondary)
                    } else {
                        ForEach(shown.recentReviews) { review in
                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(review.authorName).font(.subheadline.weight(.bold))
                                        Text(FiniTime.label(review.createdAt)).font(.caption).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    Text(String(repeating: "★", count: min(5, review.rating)) + String(repeating: "☆", count: max(0, 5 - review.rating)))
                                        .foregroundStyle(FiniTheme.star)
                                        .font(.caption)
                                }
                                if !review.text.isEmpty { Text(review.text) }
                            }
                            .padding(14)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(FiniTheme.field, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                        }
                    }
                    facts
                }
                .padding(.horizontal, 18)
                .padding(.bottom, 16)
            }
            ConceptCategoryBar(selection: $category) { _ in }
                .padding(.horizontal, 18)
                .padding(.vertical, 8)
                .background(Color.white)
        }
        .background(Color.white)
        .task { detail = try? await app.api.interpreter(id: profile.id) }
        .sheet(item: $chat) { conversation in
            NavigationStack {
                ConversationView(conversationId: conversation.id, title: conversation.name)
                    .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { chat = nil } } }
            }
        }
        .sheet(isPresented: $dial) { DialView() }
    }

    private var weekRow: some View {
        let today = Date()
        let days = (0..<5).map { offset -> String in
            guard let date = Calendar.current.date(byAdding: .day, value: offset, to: today) else { return "" }
            return offset == 0 ? "Today" : String(Calendar.current.component(.day, from: date))
        }
        return HStack {
            ForEach(Array(days.enumerated()), id: \.offset) { index, label in
                Text(label)
                    .font(.subheadline.weight(index == 0 ? .heavy : .semibold))
                    .foregroundStyle(index == 0 ? FiniTheme.ink : Color(red: 100 / 255, green: 116 / 255, blue: 139 / 255))
                    .frame(maxWidth: .infinity)
            }
        }
        .padding(.vertical, 13)
        .padding(.horizontal, 8)
        .background(FiniTheme.soft, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    @ViewBuilder
    private var actions: some View {
        if app.account == nil {
            Text("Sign in to call this interpreter.").foregroundStyle(.secondary)
        } else if app.account?.isInterpreter == true {
            Text("Translators cannot call other translators.").foregroundStyle(.secondary)
        } else {
            Button(busy ? "Calling…" : "Request Instant Call") { Task { await call() } }
                .buttonStyle(ConceptFilledButtonStyle())
                .disabled(busy)
            Button("Schedule a Session") { status = "Scheduling stays on finispeak.com." }
                .buttonStyle(ConceptFilledButtonStyle())
            Button("Chat with translator") { Task { await openChat() } }
                .font(.body.weight(.bold))
                .foregroundStyle(FiniTheme.blue)
                .frame(maxWidth: .infinity)
            Button("Start a call with another person") { dial = true }
                .font(.body.weight(.bold))
                .foregroundStyle(FiniTheme.blue)
                .frame(maxWidth: .infinity)
        }
    }

    private var facts: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Profile details").font(.headline).padding(.bottom, 4)
            fact("Experience", "\(shown.yearsExperience) years")
            fact("Service location", shown.serviceLocation?.label.isEmpty == false ? (shown.serviceLocation?.label ?? "Remote only") : "Remote only")
            fact("Schedule", scheduleLine)
            fact("Verification", shown.verificationStatus.isEmpty ? "Not submitted" : shown.verificationStatus.replacingOccurrences(of: "_", with: " ").capitalized)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(FiniTheme.field, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(FiniTheme.line))
    }

    private var scheduleLine: String {
        let days = shown.availability.days.filter { !$0.isEmpty }
        guard !days.isEmpty else { return "Not listed" }
        let labels = days.map { $0.prefix(3).capitalized }.joined(separator: ", ")
        if shown.availability.start.isEmpty || shown.availability.end.isEmpty { return labels }
        return "\(labels) · \(Self.clock(shown.availability.start))–\(Self.clock(shown.availability.end))"
    }

    private var stars: String {
        let filled = shown.rating > 0 ? min(5, max(1, Int(shown.rating.rounded()))) : 0
        return String(repeating: "★", count: filled) + String(repeating: "☆", count: 5 - filled)
    }

    private var photoURL: URL? {
        guard let raw = shown.photoUrl?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else { return nil }
        if raw.hasPrefix("http://") || raw.hasPrefix("https://") { return URL(string: raw) }
        if raw.hasPrefix("/") { return URL(string: raw, relativeTo: app.api.baseURL)?.absoluteURL }
        return nil
    }

    private func sectionTitle(_ kicker: String, _ title: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(kicker).font(.subheadline.weight(.heavy)).foregroundStyle(FiniTheme.avatarInk)
            Text(title).font(.system(size: 22, weight: .heavy)).foregroundStyle(FiniTheme.ink)
        }
        .padding(.top, 8)
    }

    @ViewBuilder
    private func tagGroup(_ title: String, _ values: [String]) -> some View {
        let items = values.filter { !$0.isEmpty }
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text(title).font(.subheadline.weight(.bold))
                FlowRows(spacing: 7) {
                    ForEach(items, id: \.self) { item in
                        Text(item)
                            .font(.system(size: 13, weight: .bold))
                            .foregroundStyle(FiniTheme.avatarInk)
                            .padding(.horizontal, 9)
                            .padding(.vertical, 5)
                            .background(Color(red: 239 / 255, green: 246 / 255, blue: 1), in: Capsule())
                    }
                }
            }
        }
    }

    private func fact(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title.uppercased()).font(.caption.weight(.heavy)).foregroundStyle(.secondary)
            Text(value).font(.subheadline.weight(.semibold))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 10)
        .overlay(alignment: .bottom) { Divider() }
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

    private func openChat() async {
        do {
            chat = try await app.api.openDirect(userId: shown.id)
        } catch {
            status = error.localizedDescription
        }
    }

    private static func clock(_ value: String) -> String {
        let parts = value.split(separator: ":")
        guard parts.count >= 2, let hour = Int(parts[0]), (0...23).contains(hour) else { return value }
        let minute = String(parts[1].prefix(2))
        guard minute.count == 2, Int(minute) != nil else { return value }
        let suffix = hour >= 12 ? "PM" : "AM"
        return "\(hour % 12 == 0 ? 12 : hour % 12):\(minute) \(suffix)"
    }
}

private struct ProfilePhoto: View {
    let name: String
    let url: URL?
    var size: CGFloat

    var body: some View {
        ZStack {
            AvatarView(name: name, size: size)
            if let url {
                AsyncImage(url: url) { phase in
                    if let image = phase.image {
                        image.resizable().scaledToFill()
                    }
                }
                .frame(width: size, height: size)
                .clipShape(Circle())
            }
        }
        .frame(width: size, height: size)
    }
}

private struct FlowRows: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 0
        guard width > 0 else {
            let sizes = subviews.map { $0.sizeThatFits(.unspecified) }
            let total = sizes.reduce(CGFloat(0)) { $0 + $1.width } + spacing * CGFloat(max(0, sizes.count - 1))
            return CGSize(width: total, height: sizes.map(\.height).max() ?? 0)
        }
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x > 0, x + size.width > width {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
        }
        return CGSize(width: width, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x > bounds.minX, x + size.width > bounds.maxX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            view.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
        }
    }
}
