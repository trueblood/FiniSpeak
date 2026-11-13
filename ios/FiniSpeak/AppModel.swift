import Foundation

@MainActor
final class AppModel: ObservableObject {
    struct IncomingCall: Identifiable, Equatable {
        enum Kind: Equatable { case customer, directTranslator, translator, invite }
        var id: String { call.id }
        var call: CallRecord
        var kind: Kind
        var title: String
        var detail: String
    }

    @Published var account: Account?
    @Published var restoring = true
    @Published var serverURL: String
    @Published var incoming: IncomingCall?
    @Published var callSession: CallSession?
    @Published var history: [CallRecord] = []

    let api: APIClient
    private var didRestore = false
    private var dismissedIncomingId: String?
    private var inviteTask: Task<Void, Never>?

    init() {
        let normalized = APIClient.storedBaseURL()
        serverURL = normalized
        api = APIClient(baseURL: URL(string: normalized) ?? URL(string: APIClient.productionBaseURL)!)
        api.token = KeychainStore.load()
        api.onUnauthorized = { [weak self] in
            Task { @MainActor in self?.signOutLocal() }
        }
    }

    func restoreIfNeeded() async {
        guard !didRestore else { return }
        didRestore = true
        defer { restoring = false }
        guard api.token != nil else { return }
        do {
            _ = try await api.session()
            account = try await api.currentAccount()
            startIncomingPolling()
            history = (try? await api.sessions()) ?? []
        } catch {
            signOutLocal()
        }
    }

    func login(email: String, password: String) async throws {
        let session = try await api.login(email: email, password: password)
        guard let token = session.accessToken, !token.isEmpty else {
            throw APIError(status: 0, message: session.message ?? "Sign-in did not return a session.")
        }
        api.token = token
        KeychainStore.save(token: token)
        account = (try? await api.currentAccount()) ?? session.user
        startIncomingPolling()
        history = (try? await api.sessions()) ?? []
    }

    func register(name: String, email: String, password: String, phone: String, role: String) async throws -> String {
        let result = try await api.register(name: name, email: email, password: password, phone: phone, role: role)
        return result.message ?? "Account created. You can sign in now."
    }

    func forgotPassword(email: String) async throws -> String {
        let result = try await api.forgotPassword(email: email)
        return result.message ?? "If the account exists, a recovery link will be sent."
    }

    func signOut() async {
        await api.logout()
        signOutLocal()
    }

    func updateServer(_ raw: String) {
        let normalized = APIClient.saveBaseURL(APIClient.normalize(raw))
        guard normalized != serverURL else { return }
        serverURL = normalized
        api.baseURL = URL(string: normalized) ?? api.baseURL
        if account != nil { signOutLocal() }
    }

    func placeCall(receiverId: String, purpose: String? = nil, translatorId: String? = nil) async throws {
        let created = try await api.createCall(receiverId: receiverId, purpose: purpose, translatorId: translatorId)
        begin(created.call)
    }

    func acceptIncoming() async {
        guard let incoming, let account else { return }
        let call = incoming.call
        self.incoming = nil
        do {
            switch incoming.kind {
            case .customer, .directTranslator:
                _ = try await api.updateCallState(id: call.id, state: "connected")
            case .invite:
                _ = try await api.callExperience(id: call.id, action: "accept-invite")
            case .translator:
                break
            }
            let latest = (try? await api.call(id: call.id)) ?? call
            begin(latest, user: account)
        } catch {
            self.incoming = nil
        }
    }

    func declineIncoming() async {
        guard let incoming else { return }
        let call = incoming.call
        dismissedIncomingId = call.id
        self.incoming = nil
        switch incoming.kind {
        case .customer, .directTranslator:
            _ = try? await api.updateCallState(id: call.id, state: "declined")
        case .invite:
            _ = try? await api.callExperience(id: call.id, action: "decline-invite")
        case .translator:
            _ = try? await api.declineTranslator(callId: call.id)
        }
    }

    func finishCall() {
        callSession = nil
        Task { history = (try? await api.sessions()) ?? history }
    }

    func refreshHistory() async {
        history = (try? await api.sessions()) ?? []
    }

    private func begin(_ call: CallRecord, user: Account? = nil) {
        guard let user = user ?? account else { return }
        let session = CallSession(call: call, user: user, api: api)
        session.onEnded = { [weak self] in
            self?.finishCall()
        }
        callSession = session
        incoming = nil
        Task { await session.start() }
    }

    private func startIncomingPolling() {
        inviteTask?.cancel()
        inviteTask = Task { [weak self] in
            while let self, !Task.isCancelled {
                await self.refreshIncoming()
                try? await Task.sleep(nanoseconds: 4_000_000_000)
            }
        }
    }

    private func refreshIncoming() async {
        guard let account, callSession == nil else { return }
        let next: IncomingCall?
        if account.role == "translator" {
            next = (try? await api.pendingCalls())?.first.flatMap { classifyTranslator($0, user: account) }
        } else {
            let ringing = ((try? await api.sessions()) ?? []).filter { $0.receiverId == account.uid && $0.status == "ringing" }
            if let call = ringing.sorted(by: { ($0.createdAt ?? "") > ($1.createdAt ?? "") }).first {
                next = IncomingCall(call: call, kind: .customer, title: "\(call.callerName ?? "Someone") is calling", detail: "Accept to connect. The live transcript appears after you join.")
            } else {
                next = nil
            }
        }
        let resolved: IncomingCall?
        if let next {
            resolved = next
        } else if let invite = (try? await api.invitations())?.first {
            resolved = IncomingCall(call: invite, kind: .invite, title: "\(invite.callerName ?? "Someone") invited you", detail: "Accept to join this call.")
        } else {
            resolved = nil
        }
        guard let resolved else {
            incoming = nil
            return
        }
        if resolved.id == dismissedIncomingId {
            incoming = nil
            return
        }
        incoming = resolved
    }

    private func classifyTranslator(_ call: CallRecord, user: Account) -> IncomingCall? {
        if call.purpose == "translator_chat" && call.receiverId == user.uid && call.status == "ringing" {
            return IncomingCall(call: call, kind: .directTranslator, title: "\(call.callerName ?? "Someone") is calling you", detail: "Accept to talk with them directly.")
        }
        guard call.invitedTranslatorId == user.uid else { return nil }
        return IncomingCall(call: call, kind: .translator, title: "\(call.callerName ?? "Someone") asked you to interpret", detail: "Accept to join the call as the interpreter.")
    }

    private func signOutLocal() {
        inviteTask?.cancel()
        Task { await callSession?.hangUp() }
        callSession = nil
        incoming = nil
        account = nil
        history = []
        api.token = nil
        KeychainStore.clear()
    }
}
