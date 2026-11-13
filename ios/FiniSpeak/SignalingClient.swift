import Foundation

/// WebSocket client for `/ws/signaling`. The browser uses the same join, offer, answer, ice, and hangup messages.
final class SignalingClient: NSObject, URLSessionWebSocketDelegate {
    var onMessage: (([String: Any]) -> Void)?
    var onState: ((String) -> Void)?

    private var task: URLSessionWebSocketTask?
    private var session: URLSession?
    private var token = ""
    private var callId = ""
    private var cursor = 0
    private var socketURL: URL?
    private var stopped = false
    private var reconnecting = false

    func connect(baseURL: URL, token: String, callId: String, after: Int = 0) {
        stopped = false
        self.token = token
        self.callId = callId
        cursor = after
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
        components?.scheme = components?.scheme == "https" ? "wss" : "ws"
        components?.path = "/ws/signaling"
        components?.query = nil
        socketURL = components?.url
        openSocket()
    }

    func send(type: String, to recipient: String, payload: [String: Any]) {
        sendJSON([
            "type": type,
            "to": recipient,
            "payload": payload,
            "clientEventId": UUID().uuidString,
        ])
    }

    func close() {
        stopped = true
        task?.cancel(with: .goingAway, reason: nil)
        session?.invalidateAndCancel()
        task = nil
        session = nil
    }

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didOpenWithProtocol _: String?) {
        guard webSocketTask === task else { return }
        reconnecting = false
        sendJSON(["type": "join", "callId": callId, "after": cursor])
        receive()
        onState?("Joined the call")
    }

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
        guard webSocketTask === task, !stopped, !reconnecting else { return }
        reconnecting = true
        onState?("Reconnecting")
        DispatchQueue.global().asyncAfter(deadline: .now() + 1) { [weak self] in
            guard let self, !self.stopped else { return }
            self.openSocket()
        }
    }

    private func openSocket() {
        guard let socketURL else { return }
        reconnecting = false
        let previous = task
        task = nil
        previous?.cancel(with: .goingAway, reason: nil)
        session?.invalidateAndCancel()
        var request = URLRequest(url: socketURL)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let session = URLSession(configuration: .ephemeral, delegate: self, delegateQueue: nil)
        let task = session.webSocketTask(with: request)
        self.session = session
        self.task = task
        task.resume()
    }

    private func receive() {
        task?.receive { [weak self] result in
            guard let self, !self.stopped else { return }
            switch result {
            case .success(let message):
                if case .string(let text) = message { self.handle(text) }
                self.receive()
            case .failure:
                if !self.stopped { self.onState?("Reconnecting") }
            }
        }
    }

    private func handle(_ text: String) {
        guard let data = text.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        if let eventId = json["eventId"] as? Int { cursor = max(cursor, eventId) }
        else if let eventId = json["eventId"] as? NSNumber { cursor = max(cursor, eventId.intValue) }
        onMessage?(json)
    }

    private func sendJSON(_ body: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: body), let text = String(data: data, encoding: .utf8) else { return }
        task?.send(.string(text)) { _ in }
    }
}
