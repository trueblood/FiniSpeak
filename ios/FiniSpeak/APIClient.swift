import Foundation

struct APIError: LocalizedError {
    var status: Int
    var message: String
    var errorDescription: String? { message }
}

final class APIClient {
    static let productionBaseURL = "https://finispeak.com"
    private static let defaultsKey = "finispeak.apiBaseURL"

    var baseURL: URL
    var token: String?
    var onUnauthorized: (() -> Void)?
    private let session: URLSession
    private let decoder = JSONDecoder()

    init(baseURL: URL) {
        self.baseURL = baseURL
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpShouldSetCookies = false
        configuration.httpCookieAcceptPolicy = .never
        configuration.httpCookieStorage = nil
        configuration.timeoutIntervalForRequest = 30
        session = URLSession(configuration: configuration)
    }

    /// The address the app should call. A saved loopback address, including the old `http://127.0.0.1:8080` default, is replaced on every launch.
    static func storedBaseURL() -> String {
        let stored = UserDefaults.standard.string(forKey: defaultsKey).map(normalize) ?? productionBaseURL
        let resolved = isLoopback(stored) ? productionBaseURL : stored
        if UserDefaults.standard.string(forKey: defaultsKey) != resolved {
            UserDefaults.standard.set(resolved, forKey: defaultsKey)
        }
        return resolved
    }

    @discardableResult
    static func saveBaseURL(_ value: String) -> String {
        let resolved = isLoopback(value) ? productionBaseURL : value
        UserDefaults.standard.set(resolved, forKey: defaultsKey)
        return resolved
    }

    static func normalize(_ raw: String) -> String {
        var value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        while value.hasSuffix("/") { value.removeLast() }
        if !value.contains("://") {
            value = (prefersHTTP(value) ? "http://" : "https://") + value
        }
        return value
    }

    private static func isLoopback(_ value: String) -> Bool {
        guard let host = URLComponents(string: value)?.host else { return isLocalHost(value) }
        return isLocalHost(host)
    }

    private static func prefersHTTP(_ value: String) -> Bool {
        if isLocalHost(value) { return true }
        let host = hostPart(value)
        let octets = host.split(separator: ".").compactMap { Int($0) }
        guard octets.count == 4, octets.allSatisfy({ (0...255).contains($0) }) else { return false }
        if octets[0] == 10 { return true }
        if octets[0] == 192 && octets[1] == 168 { return true }
        if octets[0] == 172 && (16...31).contains(octets[1]) { return true }
        return false
    }

    private static func isLocalHost(_ value: String) -> Bool {
        let host = hostPart(value)
        return host == "localhost" || host == "127.0.0.1" || host == "::1" || host == "[::1]"
    }

    private static func hostPart(_ value: String) -> String {
        let lowered = value.lowercased()
        if lowered == "::1" || lowered == "[::1]" || lowered.hasPrefix("[::1]") { return lowered }
        return lowered.split(separator: ":", maxSplits: 1).first.map(String.init) ?? lowered
    }

    func health() async throws -> Bool {
        let data = try await send("GET", "/api/health", logoutOn401: false)
        let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        return json?["status"] as? String == "ok"
    }

    func login(email: String, password: String) async throws -> AuthSession {
        try await decode(AuthSession.self, "POST", "/api/auth/login", body: ["email": email, "password": password], logoutOn401: false)
    }

    func register(name: String, email: String, password: String, phone: String, role: String) async throws -> ServerMessage {
        var body: [String: Any] = ["displayName": name, "email": email, "password": password, "role": role]
        if !phone.isEmpty { body["phone"] = phone }
        return try await decode(ServerMessage.self, "POST", "/api/auth/register", body: body, logoutOn401: false)
    }

    func forgotPassword(email: String) async throws -> ServerMessage {
        try await decode(ServerMessage.self, "POST", "/api/auth/forgot-password", body: ["email": email], logoutOn401: false)
    }

    func logout() async {
        _ = try? await send("POST", "/api/auth/logout", body: [:])
    }

    func session() async throws -> Account {
        struct Envelope: Decodable { var user: Account }
        return try await decode(Envelope.self, "GET", "/api/auth/session").user
    }

    func currentAccount() async throws -> Account {
        try await decode(AccountEnvelope.self, "GET", "/api/accounts/me").account
    }

    func updateAccount(displayName: String, phone: String) async throws -> Account {
        try await decode(AccountEnvelope.self, "PATCH", "/api/accounts/me", body: ["displayName": displayName, "phone": phone]).account
    }

    func lookup(email: String?, phone: String?) async throws -> Account {
        var items: [URLQueryItem] = []
        if let email, !email.isEmpty { items.append(URLQueryItem(name: "email", value: email)) }
        if let phone, !phone.isEmpty { items.append(URLQueryItem(name: "phone", value: phone)) }
        return try await decode(AccountEnvelope.self, "GET", "/api/accounts/lookup\(query(items))").account
    }

    func discover(language: String?, availableNow: Bool, search: String) async throws -> [Interpreter] {
        var items = [URLQueryItem(name: "limit", value: "50"), URLQueryItem(name: "verified", value: "true")]
        if let language, !language.isEmpty { items.append(URLQueryItem(name: "language", value: language)) }
        if availableNow { items.append(URLQueryItem(name: "available", value: "now")) }
        let page: DiscoveryPage = try await decode(DiscoveryPage.self, "GET", "/api/discovery\(query(items))")
        let needle = search.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !needle.isEmpty else { return page.interpreters }
        return page.interpreters.filter { profile in
            let place = [profile.serviceLocation?.city, profile.serviceLocation?.state, profile.serviceLocation?.country].compactMap { $0 }
            let haystack = ([profile.displayName, profile.bio] + place + profile.languages + profile.dialects + profile.specialties).joined(separator: " ").lowercased()
            return haystack.contains(needle)
        }
    }

    func interpreter(id: String) async throws -> Interpreter {
        try await decode(Interpreter.self, "GET", "/api/translators/\(path(id))")
    }

    func myInterpreterProfile() async throws -> Interpreter {
        struct Envelope: Decodable { var profile: Interpreter }
        return try await decode(Envelope.self, "GET", "/api/translators/me/profile").profile
    }

    func enrollInterpreter(phone: String) async throws -> Interpreter {
        struct Envelope: Decodable { var profile: Interpreter }
        return try await decode(Envelope.self, "POST", "/api/translators/enroll", body: ["phone": phone]).profile
    }

    func updateAvailability(availableNow: Bool) async throws {
        _ = try await send("PATCH", "/api/availability", body: ["availableNow": availableNow, "days": [String](), "start": "", "end": ""])
    }

    func friends() async throws -> [Friend] {
        try await decode(FriendList.self, "GET", "/api/friends").friends
    }

    func addFriend(email: String, nickname: String) async throws -> Friend {
        var body: [String: Any] = ["email": email]
        if !nickname.isEmpty { body["nickname"] = nickname }
        return try await decode(FriendEnvelope.self, "POST", "/api/friends", body: body).friend
    }

    func updateFriend(id: String, nickname: String, savedPhone: String) async throws -> Friend {
        try await decode(FriendEnvelope.self, "PATCH", "/api/friends/\(path(id))", body: ["nickname": nickname, "savedPhone": savedPhone]).friend
    }

    func removeFriend(id: String) async throws {
        _ = try await send("DELETE", "/api/friends/\(path(id))")
    }

    func conversations() async throws -> [Conversation] {
        try await decode(ConversationList.self, "GET", "/api/messages/conversations").conversations
    }

    func openDirect(email: String? = nil, userId: String? = nil) async throws -> Conversation {
        var body: [String: Any] = ["kind": "direct"]
        if let email, !email.isEmpty { body["email"] = email }
        if let userId, !userId.isEmpty { body["userId"] = userId }
        return try await decode(ConversationEnvelope.self, "POST", "/api/messages/conversations", body: body).conversation
    }

    func conversation(id: String) async throws -> ConversationDetail {
        try await decode(ConversationDetail.self, "GET", "/api/messages/conversations/\(path(id))")
    }

    func sendMessage(conversationId: String, body: String) async throws -> ChatMessage {
        try await decode(MessageEnvelope.self, "POST", "/api/messages/conversations/\(path(conversationId))/messages", body: ["body": body]).message
    }

    func sessions() async throws -> [CallRecord] {
        try await decode(CallList.self, "GET", "/api/sessions").records
    }

    func pendingCalls() async throws -> [CallRecord] {
        try await decode(CallList.self, "GET", "/api/calls/pending").records
    }

    func invitations() async throws -> [CallRecord] {
        try await decode(CallList.self, "GET", "/api/calls/invitations").records
    }

    func createCall(receiverId: String, purpose: String?, translatorId: String?) async throws -> CallCreated {
        var body: [String: Any] = ["receiverId": receiverId, "processingMode": "streaming"]
        if let purpose, !purpose.isEmpty { body["purpose"] = purpose }
        if let translatorId, !translatorId.isEmpty { body["translatorId"] = translatorId }
        let key = UUID().uuidString
        return try await decode(CallCreated.self, "POST", "/api/calls/", body: body, headers: ["Idempotency-Key": key])
    }

    func call(id: String) async throws -> CallRecord {
        try await decode(CallEnvelope.self, "GET", "/api/calls/\(path(id))").call
    }

    func updateCallState(id: String, state: String) async throws -> CallRecord {
        try await decode(CallEnvelope.self, "PATCH", "/api/calls/\(path(id))/state", body: ["state": state]).call
    }

    func leaveCall(id: String) async throws {
        _ = try await send("POST", "/api/calls/\(path(id))/leave", body: [:])
    }

    func claimTranslator(id: String) async throws -> CallRecord {
        try await decode(CallEnvelope.self, "POST", "/api/calls/\(path(id))/translator-claim", body: [:]).call
    }

    func requestTranslator(callId: String, translatorId: String) async throws -> CallRecord {
        try await decode(CallEnvelope.self, "POST", "/api/calls/\(path(callId))/translator-request", body: ["translatorId": translatorId]).call
    }

    func declineTranslator(callId: String) async throws {
        _ = try await send("POST", "/api/calls/\(path(callId))/translator-request", body: ["decline": true])
    }

    func callExperience(id: String, action: String, extra: [String: Any] = [:]) async throws -> CallRecord {
        var body = extra
        body["action"] = action
        return try await decode(CallEnvelope.self, "POST", "/api/calls/\(path(id))/experience", body: body).call
    }

    func joinParticipant(callId: String, role: String, displayName: String) async throws {
        _ = try await send("POST", "/api/sessions/\(path(callId))/participants", body: ["role": role, "displayName": displayName])
    }

    func participants(callId: String) async throws -> [ParticipantRecord] {
        try await decode(ParticipantList.self, "GET", "/api/sessions/\(path(callId))/participants").participants
    }

    func transcripts(callId: String) async throws -> [TranscriptLine] {
        try await decode(TranscriptList.self, "GET", "/api/calls/\(path(callId))/transcripts").transcripts.compactMap { $0.line() }
    }

    func saveTranscript(callId: String, id: String, text: String) async throws -> TranscriptLine? {
        let saved: TranscriptSaved = try await decode(
            TranscriptSaved.self,
            "POST",
            "/api/calls/\(path(callId))/transcripts",
            body: ["id": id, "text": text, "isFinal": true, "clientCreatedAt": Int(Date().timeIntervalSince1970 * 1000)],
            headers: ["Idempotency-Key": id]
        )
        return saved.transcript?.line()
    }

    func iceServers() async throws -> [IceServerConfig] {
        let data = try await send("GET", "/api/webrtc-config")
        let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        let rows = json?["iceServers"] as? [[String: Any]] ?? []
        let servers: [IceServerConfig] = rows.compactMap { row in
            let urls: [String]
            if let many = row["urls"] as? [String] { urls = many }
            else if let one = row["urls"] as? String { urls = [one] }
            else { return nil }
            return IceServerConfig(urls: urls, username: row["username"] as? String, credential: row["credential"] as? String)
        }
        if !servers.isEmpty { return servers }
        return [IceServerConfig(urls: ["stun:stun.l.google.com:19302", "stun:stun.cloudflare.com:3478"], username: nil, credential: nil)]
    }

    private func query(_ items: [URLQueryItem]) -> String {
        var components = URLComponents()
        components.queryItems = items
        guard let encoded = components.percentEncodedQuery, !encoded.isEmpty else { return "" }
        return "?\(encoded)"
    }

    private func path(_ value: String) -> String {
        value.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? value
    }

    private func decode<T: Decodable>(_ type: T.Type, _ method: String, _ path: String, body: [String: Any]? = nil, headers: [String: String] = [:], logoutOn401: Bool = true) async throws -> T {
        let data = try await send(method, path, body: body, headers: headers, logoutOn401: logoutOn401)
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError(status: 0, message: "The server returned an unexpected response.")
        }
    }

    @discardableResult
    func send(_ method: String, _ path: String, body: [String: Any]? = nil, headers: [String: String] = [:], logoutOn401: Bool = true) async throws -> Data {
        guard let url = URL(string: path, relativeTo: baseURL)?.absoluteURL else {
            throw APIError(status: 0, message: "The server address is not a valid URL.")
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token, !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        headers.forEach { request.setValue($1, forHTTPHeaderField: $0) }
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await session.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        if (200..<300).contains(status) { return data }
        let envelope = try? decoder.decode(ServerMessage.self, from: data)
        let message = envelope?.error ?? envelope?.message ?? "Request failed (\(status))."
        if status == 401 && logoutOn401 { onUnauthorized?() }
        throw APIError(status: status, message: message)
    }
}
