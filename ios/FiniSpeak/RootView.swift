import SwiftUI

struct RootView: View {
    @EnvironmentObject private var app: AppModel

    var body: some View {
        Group {
            if app.restoring {
                VStack(spacing: 16) {
                    ConceptGlobe(size: 48)
                    ProgressView("Opening FiniSpeak")
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color.white)
            } else if app.account == nil {
                WelcomeView()
            } else {
                MainTabView()
            }
        }
        .task { await app.restoreIfNeeded() }
        .fullScreenCover(item: $app.callSession) { session in
            CallView(session: session)
                .environmentObject(app)
        }
        .overlay {
            if let incoming = app.incoming, app.callSession == nil {
                ZStack {
                    Color.black.opacity(0.35).ignoresSafeArea()
                    VStack(alignment: .leading, spacing: 14) {
                        Text("Incoming call").font(.caption.weight(.semibold)).foregroundStyle(FiniTheme.blue)
                        Text(incoming.title).font(.title3.weight(.bold))
                        Text(incoming.detail).foregroundStyle(.secondary)
                        FiniButton(title: "Accept", systemImage: "phone.fill") { Task { await app.acceptIncoming() } }
                        FiniButton(title: "Decline", systemImage: "phone.down.fill", filled: false) { Task { await app.declineIncoming() } }
                    }
                    .padding(20)
                    .background(.white, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
                    .padding(24)
                }
            }
        }
    }
}

struct MainTabView: View {
    @EnvironmentObject private var app: AppModel
    @State private var section = FiniSection.home
    @State private var category = "Education"
    @State private var discoverPreset = ""
    @State private var menu = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ConceptHeader(onSearch: { section = .discover }, onAccount: { menu = true }, accountSymbol: "gearshape")
                screen
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                    .background(Color.white)
                AppTabBar(selection: AppTab.matching(section), unreadCount: app.unreadChats) { open($0) }
            }
            .background(Color.white)
            .toolbar(.hidden, for: .navigationBar)
            .sheet(isPresented: $menu) { ConceptMenu(section: $section) }
            .task { await app.refreshUnread() }
        }
        .environment(\.goHome) {
            menu = false
            section = .home
        }
        .environment(\.openTab) { open($0) }
    }

    private func open(_ tab: AppTab) {
        menu = false
        if tab == .translate, section != .discover {
            discoverPreset = ""
        }
        section = tab.section
    }

    @ViewBuilder
    private var screen: some View {
        switch section {
        case .home:
            HomeView(onFind: { section = .discover }, onLesson: { section = .classroom }, onCall: { section = .calls }, category: $category) { chosen in
                discoverPreset = chosen
                section = .discover
            }
        case .discover:
            DiscoverView(embedded: true, preset: discoverPreset, onBack: { section = .home })
        case .calls:
            DialView(embedded: true)
        case .classroom:
            ClassroomView { query in
                discoverPreset = query
                section = .discover
            }
        case .careers:
            CareersView(onProfile: { section = .profile }, onBusiness: {
                discoverPreset = "Business"
                section = .discover
            })
        case .friends:
            FriendsView(embedded: true)
        case .messages:
            MessagesView(embedded: true)
        case .profile:
            ProfileView(embedded: true)
        case .settings:
            SettingsScreen()
        }
    }
}

struct WelcomeView: View {
    @EnvironmentObject private var app: AppModel
    @State private var authPresented = false
    @State private var creating = false
    @State private var interpreterSignup = false
    @State private var discoverPresented = false
    @State private var category = "Education"
    @State private var featured: [Interpreter] = []

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ConceptHeader(onSearch: { discoverPresented = true }, onAccount: { creating = false; interpreterSignup = false; authPresented = true }, accountSymbol: "person")
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        ConceptHub(category: $category, onCategory: { _ in discoverPresented = true }, onFind: { discoverPresented = true }, onLesson: { creating = true; interpreterSignup = false; authPresented = true }, onCall: { creating = false; interpreterSignup = false; authPresented = true }, joinTitle: "Join as an interpreter") {
                            creating = true
                            interpreterSignup = true
                            authPresented = true
                        }
                        if !featured.isEmpty {
                            Text("Interpreter network").font(.headline).padding(.top, 8)
                            ForEach(featured.prefix(2)) { profile in
                                HStack(spacing: 12) {
                                    AvatarView(name: profile.name, size: 64)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(profile.name).font(.headline)
                                        Text(profile.headline.isEmpty ? "Interpreter" : profile.headline).font(.subheadline).foregroundStyle(.secondary)
                                    }
                                    Spacer()
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
                                .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(FiniTheme.line))
                            }
                        }
                        NavigationLink {
                            ServerSettings()
                        } label: {
                            Text("Server").font(.footnote.weight(.semibold)).foregroundStyle(.secondary)
                        }
                        .padding(.top, 8)
                    }
                    .padding(.horizontal, 18)
                    .padding(.bottom, 12)
                }
                AppTabBar(selection: discoverPresented ? .translate : nil) { tab in
                    if tab == .translate {
                        discoverPresented = true
                    } else {
                        creating = false
                        interpreterSignup = tab == .careers
                        authPresented = true
                    }
                }
            }
            .background(Color.white)
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(isPresented: $discoverPresented) { DiscoverView() }
            .sheet(isPresented: $authPresented) { AuthView(creating: creating, interpreter: interpreterSignup) }
            .task { featured = (try? await app.api.discover(language: nil, availableNow: false, search: "")) ?? [] }
        }
        .environment(\.goHome) {
            authPresented = false
            discoverPresented = false
        }
        .environment(\.openTab) { tab in
            if tab == .translate {
                discoverPresented = true
            } else {
                discoverPresented = false
                creating = false
                interpreterSignup = tab == .careers
                authPresented = true
            }
        }
    }
}

struct ConceptHub: View {
    @Binding var category: String
    var onCategory: (String) -> Void
    var onFind: () -> Void
    var onLesson: () -> Void
    var onCall: () -> Void
    var joinTitle: String?
    var onJoin: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("What do you need today?")
                .font(.system(size: 38, weight: .heavy))
                .foregroundStyle(FiniTheme.ink)
                .lineSpacing(-4)
                .frame(maxWidth: 220, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.bottom, 6)
            ConceptActionButton(title: "Find a Translator", systemImage: "arrow.triangle.2.circlepath", action: onFind)
            ConceptActionButton(title: "Book a Language Lesson", systemImage: "graduationcap", action: onLesson)
            ConceptActionButton(title: "Call Another User", systemImage: "phone", action: onCall)
            ConceptCategoryBar(selection: $category, onSelect: onCategory)
                .padding(.top, 4)
            Text("FiniSpeak connects you with verified bilingual speakers fluent in specific languages and dialects, ensuring precise and professional communication for your needs.")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(FiniTheme.blurb)
                .fixedSize(horizontal: false, vertical: true)
            if let joinTitle, let onJoin {
                Button(joinTitle, action: onJoin)
                    .font(.body.weight(.bold))
                    .foregroundStyle(FiniTheme.blue)
                    .frame(maxWidth: .infinity, minHeight: 42)
            }
        }
    }
}

struct AuthView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @State var creating = false
    @State var interpreter = false
    @State private var name = ""
    @State private var email = ""
    @State private var phone = ""
    @State private var password = ""
    @State private var status = ""
    @State private var busy = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Button { dismiss() } label: {
                        Label("Back", systemImage: "chevron.left")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(FiniTheme.ink)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .background(FiniTheme.soft, in: Capsule())
                    }
                    .buttonStyle(.plain)
                    Text("FiniSpeak account").font(.subheadline.weight(.heavy)).foregroundStyle(FiniTheme.blue)
                    Text(creating ? "Create account" : "Sign in")
                        .font(.system(size: 34, weight: .heavy))
                        .foregroundStyle(FiniTheme.ink)
                    if creating {
                        ConceptField(title: "Name", text: $name, contentType: .name)
                        ConceptField(title: "Phone number", text: $phone, keyboard: .phonePad, contentType: .telephoneNumber)
                        Toggle("Join as an interpreter", isOn: $interpreter)
                            .font(.subheadline.weight(.bold))
                    }
                    ConceptField(title: "Email", text: $email, keyboard: .emailAddress, contentType: .emailAddress)
                    ConceptField(title: "Password", text: $password, secure: true, contentType: .password)
                    Text("Signing in to \(app.serverURL)")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    if creating {
                        Text("Use at least 12 characters with letters and numbers.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    if !status.isEmpty { Text(status).font(.footnote).foregroundStyle(FiniTheme.ink) }
                    Button(busy ? "Please wait…" : (creating ? "Create account" : "Sign in")) { Task { await submit() } }
                        .buttonStyle(ConceptFilledButtonStyle())
                        .disabled(busy)
                    Button(creating ? "Already have an account? Sign in" : "Need an account? Create one") { creating.toggle(); status = "" }
                        .font(.body.weight(.bold))
                        .foregroundStyle(FiniTheme.blue)
                        .frame(maxWidth: .infinity)
                    if !creating {
                        Button("Forgot password?") { Task { await reset() } }
                            .font(.body.weight(.bold))
                            .foregroundStyle(FiniTheme.blue)
                            .frame(maxWidth: .infinity)
                    }
                }
                .padding(18)
            }
            .background(Color.white)
            .toolbar(.hidden, for: .navigationBar)
        }
    }

    private func submit() async {
        busy = true
        defer { busy = false }
        do {
            if creating {
                guard name.trimmingCharacters(in: .whitespaces).count > 1 else { status = "Enter your name."; return }
                guard passwordValid else { status = "Password must be 12–256 characters and contain letters and numbers."; return }
                status = try await app.register(name: name.trimmingCharacters(in: .whitespaces), email: email.trimmingCharacters(in: .whitespaces), password: password, phone: phone.trimmingCharacters(in: .whitespaces), role: interpreter ? "translator" : "customer")
                creating = false
            } else {
                try await app.login(email: email.trimmingCharacters(in: .whitespaces), password: password)
                dismiss()
            }
        } catch {
            status = error.localizedDescription
        }
    }

    private func reset() async {
        do { status = try await app.forgotPassword(email: email.trimmingCharacters(in: .whitespaces)) }
        catch { status = error.localizedDescription }
    }

    private var passwordValid: Bool {
        password.count >= 12 && password.count <= 256 && password.contains(where: \.isLetter) && password.contains(where: \.isNumber)
    }
}

struct ServerSettings: View {
    @EnvironmentObject private var app: AppModel
    @State private var draft = ""
    @State private var message = ""

    var body: some View {
        Form {
            Section {
                TextField(APIClient.productionBaseURL, text: $draft)
                    .textInputAutocapitalization(.never)
                    .keyboardType(.URL)
                    .autocorrectionDisabled()
                Text("Accounts and calls use https://finispeak.com. A localhost address is switched back to that server. Enter another computer's address, such as http://192.168.1.20:8080, only when that machine is running FiniSpeak.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            Button("Save and check") { Task { await saveAndCheck() } }
            if !message.isEmpty { Text(message) }
        }
        .navigationTitle("Server")
        .onAppear { draft = app.serverURL }
    }

    private func saveAndCheck() async {
        app.updateServer(draft)
        draft = app.serverURL
        do {
            let ok = try await app.api.health()
            message = ok ? "Connected to \(app.serverURL)." : "The server did not answer."
        } catch {
            message = error.localizedDescription
        }
    }
}
