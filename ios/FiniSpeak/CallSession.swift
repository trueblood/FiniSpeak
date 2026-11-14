import AVFoundation
import Foundation

struct CallPerson: Identifiable, Equatable {
    var id: String
    var name: String
    var role: String
    var state: String
}

@MainActor
final class CallSession: ObservableObject, Identifiable {
    @Published var call: CallRecord
    @Published var people: [CallPerson] = []
    @Published var transcripts: [TranscriptLine] = []
    @Published var transcriptStatus = ""
    @Published var status: String
    @Published var consent: Bool
    @Published var banner = ""
    @Published var ended = false
    let media: CallMedia

    nonisolated let id: String
    var onEnded: (() -> Void)?

    private let api: APIClient
    private let user: Account
    private let signaling: SignalingClient
    private let transcription = CallTranscription()
    private var pollTask: Task<Void, Never>?
    private var leaving = false
    private var unsavedSpeech: [TranscriptLine] = []
    let connectedAt = Date()
    @Published var momentFlagged = false

    var selfName: String { user.name }
    var userId: String { user.uid }

    var elapsedStart: Date {
        if let raw = call.startedAt, let date = Self.clockDate(raw) { return date }
        return connectedAt
    }

    init(call: CallRecord, user: Account, api: APIClient) {
        id = call.id
        self.call = call
        self.user = user
        self.api = api
        consent = call.transcriptConsent?.granted == true
        status = call.status == "ringing" ? "Ringing" : "Connecting"
        let signaling = SignalingClient()
        self.signaling = signaling
        media = CallMedia { type, recipient, payload in
            signaling.send(type: type, to: recipient, payload: payload)
        }
        signaling.onState = { [weak self] label in
            Task { @MainActor in self?.status = label }
        }
        signaling.onMessage = { [weak self] message in
            Task { @MainActor in
                guard let self else { return }
                self.media.receive(message)
                if message["type"] as? String == "error", let text = message["message"] as? String {
                    self.banner = text
                }
                if message["type"] as? String == "closed" {
                    await self.hangUp(tellServer: false)
                }
            }
        }
    }

    func start() async {
        let allowed = await withCheckedContinuation { continuation in
            AVAudioSession.sharedInstance().requestRecordPermission { continuation.resume(returning: $0) }
        }
        if !allowed { banner = "The microphone is off, so other people will not hear you." }
        do {
            if participantRole == "translator" && call.translatorId != user.uid {
                call = try await api.claimTranslator(id: call.id)
            }
            try await api.joinParticipant(callId: call.id, role: participantRole, displayName: user.name)
            let servers = try await api.iceServers()
            media.start(localId: user.uid, iceServers: servers)
            signaling.connect(baseURL: api.baseURL, token: api.token ?? "", callId: call.id)
            transcription.onStatus = { [weak self] text in
                Task { @MainActor in self?.transcriptStatus = text }
            }
            transcription.onSpeech = { [weak self] heard in
                Task { @MainActor in await self?.rememberSpeech(heard) }
            }
            transcription.start(baseURL: api.baseURL, token: api.token ?? "", callId: call.id)
            let micWarning = allowed ? "" : banner
            if call.transcriptConsent?.granted != true {
                await setConsent(true)
            }
            if !micWarning.isEmpty { banner = micWarning }
            await refresh()
            pollTask = Task { [weak self] in
                while !Task.isCancelled {
                    try? await Task.sleep(nanoseconds: 2_000_000_000)
                    guard let self else { return }
                    await self.refresh()
                }
            }
        } catch {
            banner = error.localizedDescription
        }
    }

    func availableInterpreters() async -> [Interpreter] {
        (try? await api.discover(language: call.language, availableNow: true, search: "")) ?? []
    }

    func hangUp(tellServer: Bool = true) async {
        guard !leaving else { return }
        leaving = true
        pollTask?.cancel()
        let finishForEveryone = people.count <= 1
        transcription.stop()
        media.stop()
        signaling.close()
        if tellServer {
            if finishForEveryone { _ = try? await api.updateCallState(id: call.id, state: "ended") }
            try? await api.leaveCall(id: call.id)
        }
        ended = true
        onEnded?()
    }

    func setConsent(_ granted: Bool) async {
        do {
            call = try await api.callExperience(id: call.id, action: "set-transcript-consent", extra: ["granted": granted])
            consent = call.transcriptConsent?.granted == true
            if consent { await flushSpeech() }
        } catch {
            banner = error.localizedDescription
        }
    }

    private func rememberSpeech(_ heard: CallTranscription.Heard) async {
        let lineId = "\(user.uid)-\(heard.generation)-\(heard.sequence)"
        guard !transcripts.contains(where: { $0.id == lineId }) else { return }
        let line = TranscriptLine(
            id: lineId,
            text: heard.text,
            speakerId: user.uid,
            speakerName: user.name,
            speakerRole: participantRole,
            createdAt: ISO8601DateFormatter().string(from: Date()),
            localOnly: !consent
        )
        transcripts.append(line)
        if consent {
            await store(line)
        } else {
            unsavedSpeech.append(line)
        }
    }

    func flagMoment() async {
        let latest = transcripts.last
        let elapsed = Int(Date().timeIntervalSince(elapsedStart))
        let label = String(format: "%d:%02d", elapsed / 60, elapsed % 60)
        do {
            call = try await api.callExperience(id: call.id, action: "flag-moment", extra: [
                "id": "moment-\(Int(Date().timeIntervalSince1970 * 1000))",
                "elapsedLabel": label,
                "transcriptId": latest?.id ?? "",
                "speakerName": latest?.speakerName ?? "",
                "text": latest?.text ?? "",
            ])
            momentFlagged = true
        } catch {
            banner = error.localizedDescription
        }
    }

    private func flushSpeech() async {
        let waiting = unsavedSpeech
        unsavedSpeech = []
        for line in waiting {
            await store(line)
        }
    }

    private func store(_ line: TranscriptLine) async {
        do {
            if let saved = try await api.saveTranscript(callId: call.id, id: line.id, text: line.text) {
                if let index = transcripts.firstIndex(where: { $0.id == line.id }) { transcripts[index] = saved }
            }
        } catch {
            banner = error.localizedDescription
        }
    }

    func saveNote(_ text: String) async {
        do {
            call = try await api.callExperience(id: call.id, action: "save-notes", extra: ["text": text])
        } catch {
            banner = error.localizedDescription
        }
    }

    func invite(_ interpreter: Interpreter) async {
        do {
            call = try await api.requestTranslator(callId: call.id, translatorId: interpreter.id)
            banner = "Asked \(interpreter.name) to join."
        } catch {
            banner = error.localizedDescription
        }
    }

    private var participantRole: String {
        let guest = call.guestIds?.contains(user.uid) == true
        if user.role == "translator" && !guest && call.purpose != "translator_chat" { return "translator" }
        if user.uid == call.callerId { return "caller" }
        if user.uid == call.receiverId { return "receiver" }
        return "guest"
    }

    private func refresh() async {
        guard !leaving else { return }
        do {
            let latest = try await api.call(id: call.id)
            call = latest
            consent = latest.transcriptConsent?.granted == true
            let roster = (try? await api.participants(callId: call.id)) ?? []
            let stillHere = roster.filter { ($0.leftAt ?? "").isEmpty }
            if roster.contains(where: { $0.uid == user.uid && !($0.leftAt ?? "").isEmpty }) || !latest.isLive {
                status = latest.status == "declined" ? "Declined" : "Call ended"
                await hangUp(tellServer: false)
                return
            }
            let ids = stillHere.isEmpty ? remoteIds(in: latest) : stillHere.compactMap(\.uid).filter { !$0.isEmpty && $0 != user.uid }
            media.sync(remoteIds: ids)
            media.publishRemoteVideo()
            let serverLines = try await api.transcripts(callId: call.id)
            var merged = serverLines
            for line in transcripts where line.localOnly && !merged.contains(where: { $0.id == line.id }) {
                merged.append(line)
            }
            transcripts = merged.sorted { ($0.createdAt ?? "") < ($1.createdAt ?? "") }
            people = ids.map { id in
                let listed = stillHere.first { $0.uid == id }
                CallPerson(
                    id: id,
                    name: listed?.displayName?.isEmpty == false ? listed!.displayName! : name(for: id, in: latest),
                    role: role(for: id, in: latest),
                    state: media.peerState[id] ?? "Waiting"
                )
            }
            if people.contains(where: { $0.state == "Connected" }) { status = "Connected" }
            else if latest.status == "ringing" { status = "Ringing" }
            else if people.isEmpty { status = "Waiting for the other person" }
        } catch {
            if banner.isEmpty { banner = error.localizedDescription }
        }
    }

    private func remoteIds(in call: CallRecord) -> [String] {
        var ids: [String] = []
        for id in [call.callerId, call.receiverId, call.translatorId] {
            guard let id, !id.isEmpty, id != user.uid, !ids.contains(id) else { continue }
            ids.append(id)
        }
        for id in call.guestIds ?? [] where id != user.uid && !ids.contains(id) { ids.append(id) }
        return ids
    }

    private func name(for id: String, in call: CallRecord) -> String {
        if id == call.callerId { return call.callerName ?? "Caller" }
        if id == call.receiverId { return call.receiverName ?? "Receiver" }
        if id == call.translatorId { return call.translatorName ?? "Interpreter" }
        return "Guest"
    }

    private static func clockDate(_ raw: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: raw) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: raw)
    }

    private func role(for id: String, in call: CallRecord) -> String {
        if id == call.callerId { return "Caller" }
        if id == call.receiverId { return call.purpose == "translator_chat" ? "Interpreter" : "Receiver" }
        if id == call.translatorId { return "Interpreter" }
        return "Guest"
    }
}
