import SwiftUI

enum FiniSection: Hashable {
    case home, discover, classroom, friends, messages, profile, settings
}

struct ConceptGlobe: View {
    var size: CGFloat = 28

    var body: some View {
        Image(systemName: "globe")
            .font(.system(size: size * 0.52, weight: .semibold))
            .foregroundStyle(.white)
            .frame(width: size, height: size)
            .background(FiniTheme.blue, in: Circle())
    }
}

struct ConceptRoundButton: View {
    let systemImage: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(FiniTheme.ink)
                .frame(width: 36, height: 36)
                .background(FiniTheme.soft, in: Circle())
        }
        .buttonStyle(.plain)
    }
}

struct ConceptHeader: View {
    var onSearch: () -> Void
    var onAccount: () -> Void
    var accountSymbol: String

    var body: some View {
        HStack(spacing: 8) {
            ConceptGlobe()
            Text("FiniSpeak")
                .font(.system(size: 22, weight: .bold))
                .foregroundStyle(FiniTheme.ink)
            Spacer()
            ConceptRoundButton(systemImage: "magnifyingglass", action: onSearch)
            ConceptRoundButton(systemImage: accountSymbol, action: onAccount)
        }
        .padding(.horizontal, 16)
        .padding(.top, 6)
        .padding(.bottom, 8)
        .background(Color.white)
    }
}

struct ConceptActionButton: View {
    let title: String
    let systemImage: String
    var filled = true
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: systemImage)
                    .font(.system(size: 18, weight: .semibold))
                Text(title)
                    .font(.system(size: 17, weight: .heavy))
            }
            .frame(maxWidth: .infinity)
            .frame(minHeight: 58)
            .background(filled ? FiniTheme.blue : FiniTheme.soft, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .foregroundStyle(filled ? Color.white : FiniTheme.ink)
        }
        .buttonStyle(.plain)
    }
}

struct ConceptCategoryBar: View {
    @Binding var selection: String
    var onSelect: (String) -> Void
    private let items = ["Business", "Education", "Personal"]

    var body: some View {
        HStack(spacing: 8) {
            ForEach(items, id: \.self) { item in
                Button {
                    selection = item
                    onSelect(item)
                } label: {
                    Text(item)
                        .font(.system(size: 15, weight: .bold))
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                        .frame(maxWidth: .infinity, minHeight: 40)
                        .background(selection == item ? FiniTheme.blue : FiniTheme.chip, in: Capsule())
                        .foregroundStyle(selection == item ? Color.white : FiniTheme.ink)
                }
                .buttonStyle(.plain)
            }
        }
    }
}

struct ConceptTitle: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.system(size: 34, weight: .heavy))
            .foregroundStyle(FiniTheme.ink)
            .lineSpacing(-2)
            .fixedSize(horizontal: false, vertical: true)
    }
}

struct ConceptField: View {
    let title: String
    @Binding var text: String
    var secure = false
    var keyboard: UIKeyboardType = .default
    var contentType: UITextContentType?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.subheadline.weight(.bold)).foregroundStyle(FiniTheme.ink)
            Group {
                if secure {
                    SecureField("", text: $text)
                } else {
                    TextField("", text: $text)
                }
            }
            .textContentType(contentType)
            .keyboardType(keyboard)
            .textInputAutocapitalization(keyboard == .emailAddress ? .never : .sentences)
            .autocorrectionDisabled(keyboard == .emailAddress)
            .padding(13)
            .background(FiniTheme.field, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
    }
}

struct ConceptMenu: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @Binding var section: FiniSection

    private var rows: [(FiniSection, String, String)] {
        var items: [(FiniSection, String, String)] = [
            (.home, "Home", "house"),
            (.discover, "Discover", "magnifyingglass"),
            (.classroom, "Classroom", "book"),
            (.friends, "Friends", "person.2"),
            (.messages, "Messages", "bubble.left"),
            (.profile, "Profile", "person"),
            (.settings, "Settings", "gearshape"),
        ]
        return items
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 12) {
                AvatarView(name: app.account?.name ?? "FiniSpeak", size: 48)
                VStack(alignment: .leading, spacing: 2) {
                    Text(app.account?.name ?? "FiniSpeak").font(.headline)
                    Text(app.account?.roleLabel ?? "Customer").font(.subheadline).foregroundStyle(.secondary)
                }
            }
            .padding(.bottom, 8)
            ForEach(Array(rows.enumerated()), id: \.offset) { item in
                let row = item.element
                Button {
                    section = row.0
                    dismiss()
                } label: {
                    Label(row.1, systemImage: row.2)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(section == row.0 ? FiniTheme.blue : FiniTheme.ink)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 12)
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
        .padding(20)
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
        .presentationBackground(Color.white)
    }
}

struct ClassroomView: View {
    @EnvironmentObject private var app: AppModel
    var onFind: (String) -> Void
    @State private var selectedCall: CallRecord?

    var body: some View {
        ScrollView {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                ConceptTitle(text: "Education Portal")
                Spacer()
                Image(systemName: "gearshape")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(FiniTheme.blue)
                    .frame(width: 40, height: 40)
                    .background(Color(red: 238 / 255, green: 242 / 255, blue: 1), in: Circle())
            }
            Text("Verified Translator Pool").font(.headline)
            Button("Book for Parent Meeting") { onFind("Education") }
                .buttonStyle(ConceptSoftButtonStyle())
            Button("Live Classroom Support") { onFind("Education") }
                .buttonStyle(ConceptFilledButtonStyle())
            Text("Student History").font(.headline).padding(.top, 8)
            if app.history.isEmpty {
                Text("Calls you join will show up here.").foregroundStyle(.secondary)
            } else {
                ForEach(app.history.prefix(6)) { call in
                    Button { selectedCall = call } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(call.otherName(than: app.account?.uid ?? "")).font(.headline)
                                Text(FiniTime.label(call.createdAt)).font(.subheadline).foregroundStyle(.secondary)
                            }
                            Spacer()
                            VStack(alignment: .trailing, spacing: 2) {
                                Text(call.language ?? "Call").font(.headline)
                                Text(call.status ?? "Saved").font(.subheadline).foregroundStyle(.secondary)
                            }
                        }
                        .padding(12)
                        .background(Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(FiniTheme.line))
                    }
                    .buttonStyle(.plain)
                }
            }
            HStack {
                Text("Transcript Archive").font(.headline)
                Spacer()
                Text("● Saved text only").font(.subheadline.weight(.bold)).foregroundStyle(Color(red: 21 / 255, green: 128 / 255, blue: 61 / 255))
            }
            .padding(.top, 8)
        }
        .padding(.horizontal, 18)
        .padding(.bottom, 12)
        }
        .sheet(item: $selectedCall) { call in TranscriptHistoryView(call: call) }
        .task { await app.refreshHistory() }
    }
}

struct ConceptFilledButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 17, weight: .heavy))
            .frame(maxWidth: .infinity, minHeight: 52)
            .background(FiniTheme.blue.opacity(configuration.isPressed ? 0.85 : 1), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .foregroundStyle(.white)
    }
}

struct ConceptSoftButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 17, weight: .heavy))
            .frame(maxWidth: .infinity, minHeight: 52)
            .background(FiniTheme.soft, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .foregroundStyle(FiniTheme.ink)
    }
}

struct SettingsScreen: View {
    @EnvironmentObject private var app: AppModel

    var body: some View {
        ScrollView {
        VStack(alignment: .leading, spacing: 16) {
            Text("Preferences").font(.subheadline.weight(.heavy)).foregroundStyle(FiniTheme.blue)
            ConceptTitle(text: "Settings")
            Text("Manage your FiniSpeak account experience.").foregroundStyle(.secondary)
            settingsCard("Account") {
                Text("Signed in as \(app.account?.email ?? "this account").")
                Button("Sign out") { Task { await app.signOut() } }
                    .buttonStyle(ConceptSoftButtonStyle())
            }
            settingsCard("Privacy") {
                Text("Finalized transcript text can be saved with a call. Raw microphone audio is not stored by FiniSpeak.")
            }
            NavigationLink {
                ServerSettings()
            } label: {
                Text("Server")
                    .font(.system(size: 17, weight: .heavy))
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .background(FiniTheme.soft, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .foregroundStyle(FiniTheme.ink)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 18)
        .padding(.bottom, 12)
        }
    }

    private func settingsCard<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(.headline)
            content()
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(FiniTheme.line))
    }
}
