import SwiftUI

struct RootView: View {
    @EnvironmentObject private var app: AppModel

    var body: some View {
        Group {
            if app.restoring {
                VStack(spacing: 16) {
                    Image(systemName: "globe")
                        .font(.system(size: 36, weight: .semibold))
                        .foregroundStyle(FiniTheme.blue)
                    ProgressView("Opening FiniSpeak")
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(FiniTheme.mist)
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
    var body: some View {
        TabView {
            HomeView()
                .tabItem { Label("Home", systemImage: "house") }
            DiscoverView()
                .tabItem { Label("Discover", systemImage: "magnifyingglass") }
            MessagesView()
                .tabItem { Label("Messages", systemImage: "bubble.left.and.bubble.right") }
            FriendsView()
                .tabItem { Label("Friends", systemImage: "person.2") }
            ProfileView()
                .tabItem { Label("Profile", systemImage: "person.crop.circle") }
        }
    }
}

struct WelcomeView: View {
    @EnvironmentObject private var app: AppModel
    @State private var authPresented = false
    @State private var discoverPresented = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    HStack(spacing: 8) {
                        Image(systemName: "globe")
                            .foregroundStyle(.white)
                            .frame(width: 32, height: 32)
                            .background(FiniTheme.blue, in: Circle())
                        Text("FiniSpeak").font(.title2.weight(.bold))
                        Spacer()
                        NavigationLink("Server") { ServerSettings() }
                            .font(.subheadline.weight(.semibold))
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        Text("What do you need today?")
                            .font(.title.weight(.bold))
                        Text("Find a verified interpreter, call someone who already uses FiniSpeak, or create an account on the same server as the website.")
                            .foregroundStyle(.secondary)
                    }
                    FiniButton(title: "Find a translator", systemImage: "magnifyingglass") { discoverPresented = true }
                    FiniButton(title: "Create an account", systemImage: "person.badge.plus", filled: false) { authPresented = true }
                    FiniButton(title: "Log in", systemImage: "person") { authPresented = true }
                }
                .padding(20)
            }
            .background(FiniTheme.mist)
            .navigationDestination(isPresented: $discoverPresented) { DiscoverView() }
            .sheet(isPresented: $authPresented) { AuthView() }
        }
    }
}

struct AuthView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var creating = false
    @State private var name = ""
    @State private var email = ""
    @State private var phone = ""
    @State private var password = ""
    @State private var interpreter = false
    @State private var status = ""
    @State private var busy = false

    var body: some View {
        NavigationStack {
            Form {
                if creating {
                    TextField("Name", text: $name)
                    TextField("Phone", text: $phone)
                        .keyboardType(.phonePad)
                    Toggle("Join as an interpreter", isOn: $interpreter)
                }
                TextField("Email", text: $email)
                    .textInputAutocapitalization(.never)
                    .keyboardType(.emailAddress)
                    .autocorrectionDisabled()
                SecureField("Password", text: $password)
                if creating {
                    Text("Use at least 12 characters with letters and numbers.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                if !status.isEmpty { Text(status).font(.footnote) }
                Button(creating ? "Create account" : "Sign in") { Task { await submit() } }
                    .disabled(busy)
                Button(creating ? "Already have an account? Sign in" : "Need an account? Create one") { creating.toggle(); status = "" }
                if !creating {
                    Button("Forgot password?") { Task { await reset() } }
                }
            }
            .navigationTitle(creating ? "Create account" : "Sign in")
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } } }
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
                TextField("https://example.com", text: $draft)
                    .textInputAutocapitalization(.never)
                    .keyboardType(.URL)
                    .autocorrectionDisabled()
                Text("The iOS Simulator can use http://127.0.0.1:8080 while `python app.py` is running on this Mac. A physical iPhone needs the computer's address, such as http://192.168.1.20:8080.")
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
