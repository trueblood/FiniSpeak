import AVFoundation
import Foundation

/// Sends microphone audio to `/ws/transcription` and reports each finished line.
/// This is the same socket the website uses. Raw audio is not stored.
final class CallTranscription: NSObject, URLSessionWebSocketDelegate {
    struct Heard {
        var text: String
        var sequence: Int
        var generation: Int
        var language: String?
    }

    var onSpeech: ((Heard) -> Void)?
    var onStatus: ((String) -> Void)?

    private var task: URLSessionWebSocketTask?
    private var session: URLSession?
    private var engine: AVAudioEngine?
    private let sendQueue = DispatchQueue(label: "com.finispeak.transcription")
    private var stopped = true
    private var ready = false
    private var generation = 0
    private var buffered: [Data] = []
    private var pendingStart: [String: Any]?

    func start(baseURL: URL, token: String, callId: String) {
        stop()
        stopped = false
        ready = false
        generation = Int(Date().timeIntervalSince1970 * 1000)
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
        components?.scheme = components?.scheme == "https" ? "wss" : "ws"
        components?.path = "/ws/transcription"
        components?.query = nil
        guard let url = components?.url else { return }
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let session = URLSession(configuration: .ephemeral, delegate: self, delegateQueue: nil)
        let task = session.webSocketTask(with: request)
        self.session = session
        self.task = task
        self.pendingStart = [
            "type": "start",
            "callId": callId,
            "sampleRate": 16000,
            "processingMode": "streaming",
            "generation": generation,
        ]
        task.resume()
        onStatus?("Connecting the transcript…")
        captureMicrophone()
    }

    func stop() {
        stopped = true
        ready = false
        pendingStart = nil
        engine?.inputNode.removeTap(onBus: 0)
        engine?.stop()
        engine = nil
        buffered.removeAll()
        task?.cancel(with: .goingAway, reason: nil)
        session?.invalidateAndCancel()
        task = nil
        session = nil
    }

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didOpenWithProtocol _: String?) {
        if let pendingStart {
            sendJSON(pendingStart)
            self.pendingStart = nil
        }
        receive()
    }

    private func captureMicrophone() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .allowBluetoothHFP, .mixWithOthers])
        try? session.setActive(true)
        let engine = AVAudioEngine()
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else {
            onStatus?("The transcript is waiting for the microphone.")
            retryCapture()
            return
        }
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 2048, format: format) { [weak self] buffer, _ in
            guard let self, !self.stopped else { return }
            let pcm = Self.pcm16(from: buffer)
            guard !pcm.isEmpty else { return }
            self.sendQueue.async { self.sendAudio(pcm) }
        }
        engine.prepare()
        do {
            try engine.start()
            self.engine = engine
        } catch {
            input.removeTap(onBus: 0)
            onStatus?("The transcript could not hear the microphone.")
            retryCapture()
        }
    }

    private func retryCapture() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in
            guard let self, !self.stopped, self.engine == nil else { return }
            self.captureMicrophone()
        }
    }

    private func sendAudio(_ pcm: Data) {
        guard !stopped else { return }
        if ready {
            task?.send(.data(pcm)) { _ in }
        } else {
            buffered.append(pcm)
            let limit = 16000 * 2 * 20
            var total = buffered.reduce(0) { $0 + $1.count }
            while total > limit, !buffered.isEmpty {
                total -= buffered.removeFirst().count
            }
        }
    }

    private func flushAudio() {
        let chunks = buffered
        buffered.removeAll()
        for chunk in chunks {
            task?.send(.data(chunk)) { _ in }
        }
    }

    private func sendJSON(_ body: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: body), let text = String(data: data, encoding: .utf8) else { return }
        task?.send(.string(text)) { _ in }
    }

    private func receive() {
        task?.receive { [weak self] result in
            guard let self, !self.stopped else { return }
            if case .success(let message) = result {
                let text: String?
                switch message {
                case .string(let value): text = value
                case .data(let value): text = String(data: value, encoding: .utf8)
                @unknown default: text = nil
                }
                if let text, let data = text.data(using: .utf8),
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    self.handle(json)
                }
                self.receive()
            }
        }
    }

    private func handle(_ message: [String: Any]) {
        if let messageGeneration = Self.intValue(message["generation"]), messageGeneration != generation { return }
        switch message["type"] as? String {
        case "ready":
            ready = true
            sendQueue.async { self.flushAudio() }
            onStatus?("Listening")
        case "listening":
            onStatus?("Listening")
        case "capture", "processing":
            onStatus?("Hearing speech…")
        case "final":
            let text = (message["text"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            guard !text.isEmpty else { return }
            let sequence = Self.intValue(message["sequence"]) ?? 0
            let language = message["language"] as? String
            onSpeech?(Heard(text: text, sequence: sequence, generation: generation, language: language))
            onStatus?("Listening")
        case "error":
            onStatus?(message["message"] as? String ?? "Transcript unavailable.")
        default:
            break
        }
    }

    private static func intValue(_ value: Any?) -> Int? {
        if let number = value as? Int { return number }
        if let number = value as? NSNumber { return Int(number.int64Value) }
        return nil
    }

    private static func pcm16(from buffer: AVAudioPCMBuffer) -> Data {
        let frames = Int(buffer.frameLength)
        guard frames > 0 else { return Data() }
        let rate = buffer.format.sampleRate
        let channels = Int(buffer.format.channelCount)
        guard rate > 0, channels > 0 else { return Data() }
        let ratio = rate / 16000
        let count = max(1, Int(Double(frames) / ratio))
        var data = Data(count: count * 2)
        data.withUnsafeMutableBytes { raw in
            guard let out = raw.baseAddress?.assumingMemoryBound(to: Int16.self) else { return }
            if let channel = buffer.floatChannelData?[0] {
                for index in 0..<count {
                    let start = min(frames - 1, Int(Double(index) * ratio))
                    let end = min(frames, Int(Double(index + 1) * ratio))
                    var sum: Float = 0
                    let span = max(1, end - start)
                    for sample in start..<start + span { sum += channel[sample] }
                    let value = max(-1, min(1, sum / Float(span)))
                    out[index] = Int16(value < 0 ? value * 32768 : value * 32767)
                }
            } else if let channel = buffer.int16ChannelData?[0] {
                for index in 0..<count {
                    let start = min(frames - 1, Int(Double(index) * ratio))
                    out[index] = channel[start]
                }
            }
        }
        return data
    }
}
