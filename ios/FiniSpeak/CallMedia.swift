import AVFoundation
import Foundation
import WebRTC

/// One mesh peer. The lower user id offers first, matching `views/static/js/webrtc-mesh.js`.
final class CallMedia: NSObject, ObservableObject {
    @Published var remoteVideo: [String: RTCVideoTrack] = [:]
    @Published var localVideo: RTCVideoTrack?
    @Published var microphoneOn = true
    @Published var cameraOn = false
    @Published var cameraMessage = ""
    @Published var peerState: [String: String] = [:]

    private static let factory: RTCPeerConnectionFactory = {
        RTCInitializeSSL()
        return RTCPeerConnectionFactory(encoderFactory: RTCDefaultVideoEncoderFactory(), decoderFactory: RTCDefaultVideoDecoderFactory())
    }()
    private var peers: [String: PeerLink] = [:]
    private var audioTrack: RTCAudioTrack?
    private var videoTrack: RTCVideoTrack?
    private var videoCapturer: RTCCameraVideoCapturer?
    private var iceServers: [IceServerConfig] = []
    private var localId = ""
    private let sendSignal: (String, String, [String: Any]) -> Void
    private let lock = NSLock()
    private var chains: [String: Task<Void, Never>] = [:]
    private var stopped = false

    init(send: @escaping (String, String, [String: Any]) -> Void) {
        sendSignal = send
        super.init()
    }

    func start(localId: String, iceServers: [IceServerConfig]) {
        self.localId = localId
        self.iceServers = iceServers
        let audio = RTCAudioSession.sharedInstance()
        audio.useManualAudio = true
        configureAudioSession()
        let source = Self.factory.audioSource(with: RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: nil))
        let track = Self.factory.audioTrack(with: source, trackId: "audio0")
        audioTrack = track
        audio.isAudioEnabled = true
    }

    func sync(remoteIds: [String]) {
        guard !stopped else { return }
        let existing = currentPeerIds()
        for remoteId in remoteIds where !existing.contains(remoteId) {
            openPeer(remoteId)
        }
        for remoteId in existing where !remoteIds.contains(remoteId) {
            closePeer(remoteId, notify: false)
        }
    }

    func receive(_ message: [String: Any]) {
        guard let type = message["type"] as? String, let from = message["from"] as? String, from != localId else { return }
        if peer(from) == nil && ["offer", "answer", "ice", "reconnect"].contains(type) {
            openPeer(from)
        }
        guard let peer = peer(from) else { return }
        enqueue(from) { [weak self, weak peer] in
            guard let self, let peer else { return }
            await self.apply(type, message: message, peer: peer)
        }
    }

    func setMicrophone(on: Bool) {
        audioTrack?.isEnabled = on
        DispatchQueue.main.async { self.microphoneOn = on }
    }

    func setCamera(on: Bool) {
        if on { enableCamera() } else { disableCamera() }
    }

    func stop() {
        stopped = true
        let ids = currentPeerIds()
        for id in ids { closePeer(id, notify: true) }
        videoCapturer?.stopCapture()
        audioTrack?.isEnabled = false
        RTCAudioSession.sharedInstance().isAudioEnabled = false
        DispatchQueue.main.async {
            self.remoteVideo = [:]
            self.localVideo = nil
            self.cameraOn = false
            self.peerState = [:]
        }
    }

    private func openPeer(_ remoteId: String) {
        guard peer(remoteId) == nil, let audioTrack else { return }
        let configuration = RTCConfiguration()
        configuration.sdpSemantics = .unifiedPlan
        configuration.continualGatheringPolicy = .gatherContinually
        configuration.iceServers = iceServers.compactMap { server in
            let urls = server.urls.filter { !$0.isEmpty }
            guard !urls.isEmpty else { return nil }
            if let username = server.username, let credential = server.credential, !username.isEmpty {
                return RTCIceServer(urlStrings: urls, username: username, credential: credential)
            }
            return RTCIceServer(urlStrings: urls)
        }
        let constraints = RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: ["DtlsSrtpKeyAgreement": kRTCMediaConstraintsValueTrue])
        guard let connection = Self.factory.peerConnection(with: configuration, constraints: constraints, delegate: nil) else { return }
        let peer = PeerLink(remoteId: remoteId, connection: connection, offerer: localId < remoteId)
        connection.delegate = peer
        peer.media = self
        store(peer)
        connection.add(audioTrack, streamIds: ["finispeak"])
        if let videoTrack {
            connection.add(videoTrack, streamIds: ["finispeak"])
        }
        peer.suppressOffer = false
        publishState(remoteId, "Calling")
        if peer.offerer {
            sendOffer(peer)
        } else {
            DispatchQueue.global().asyncAfter(deadline: .now() + 4) { [weak self, weak peer] in
                guard let self, let peer, self.peer(peer.remoteId) === peer else { return }
                if peer.connection.signalingState == .stable && peer.connection.remoteDescription == nil {
                    self.sendOffer(peer)
                }
            }
        }
    }

    private func closePeer(_ remoteId: String, notify: Bool) {
        guard let peer = removePeer(remoteId) else { return }
        if notify { sendSignal("hangup", remoteId, [:]) }
        peer.connection.close()
        DispatchQueue.main.async {
            self.remoteVideo.removeValue(forKey: remoteId)
            self.peerState.removeValue(forKey: remoteId)
        }
    }

    fileprivate func sendOffer(_ peer: PeerLink) {
        enqueue(peer.remoteId) { [weak self, weak peer] in
            guard let self, let peer, !peer.makingOffer, peer.connection.signalingState == .stable else { return }
            peer.makingOffer = true
            defer { peer.makingOffer = false }
            guard let offer = await self.requestOffer(on: peer.connection) else { return }
            guard peer.connection.signalingState == .stable else { return }
            guard await self.setLocal(offer, on: peer.connection), let local = peer.connection.localDescription else { return }
            self.sendSignal("offer", peer.remoteId, ["type": self.name(for: local.type), "sdp": local.sdp])
        }
    }

    private func apply(_ type: String, message: [String: Any], peer: PeerLink) async {
        let payload = message["payload"] as? [String: Any] ?? [:]
        switch type {
        case "offer":
            await answer(payload, peer: peer)
        case "answer":
            guard peer.connection.signalingState == .haveLocalOffer, let description = sessionDescription(payload) else { return }
            await setRemote(description, on: peer)
        case "ice":
            await addIce(payload, peer: peer)
        case "hangup":
            closePeer(peer.remoteId, notify: false)
        case "reconnect":
            if peer.offerer && peer.connection.signalingState == .stable {
                sendOffer(peer)
            }
        default:
            break
        }
    }

    private func answer(_ payload: [String: Any], peer: PeerLink) async {
        guard let description = sessionDescription(payload) else { return }
        let state = peer.connection.signalingState
        if peer.offerer && (peer.makingOffer || state == .haveLocalOffer) { return }
        if state == .haveLocalOffer || state == .haveLocalPrAnswer {
            let rollback = RTCSessionDescription(type: .rollback, sdp: "")
            guard await setLocal(rollback, on: peer.connection), peer.connection.signalingState == .stable else { return }
        } else if state != .stable && state != .haveRemoteOffer {
            return
        }
        guard await setRemote(description, on: peer) else { return }
        guard let answer = await requestAnswer(on: peer.connection) else { return }
        guard await setLocal(answer, on: peer.connection), let local = peer.connection.localDescription else { return }
        sendSignal("answer", peer.remoteId, ["type": name(for: local.type), "sdp": local.sdp])
        publishVideo(peer)
    }

    private func addIce(_ payload: [String: Any], peer: PeerLink) async {
        guard let candidate = iceCandidate(payload) else { return }
        if peer.connection.remoteDescription == nil {
            peer.pendingIce.append(payload)
            return
        }
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            peer.connection.add(candidate) { _ in continuation.resume() }
        }
    }

    private func setRemote(_ description: RTCSessionDescription, on peer: PeerLink) async -> Bool {
        let ok = await withCheckedContinuation { (continuation: CheckedContinuation<Bool, Never>) in
            peer.connection.setRemoteDescription(description) { error in continuation.resume(returning: error == nil) }
        }
        guard ok else { return false }
        let queued = peer.pendingIce
        peer.pendingIce = []
        for payload in queued {
            if let candidate = iceCandidate(payload) {
                await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
                    peer.connection.add(candidate) { _ in continuation.resume() }
                }
            }
        }
        publishVideo(peer)
        publishState(peer.remoteId, "Connecting")
        return true
    }

    private func setLocal(_ description: RTCSessionDescription, on connection: RTCPeerConnection) async -> Bool {
        await withCheckedContinuation { continuation in
            connection.setLocalDescription(description) { error in continuation.resume(returning: error == nil) }
        }
    }

    private func requestOffer(on connection: RTCPeerConnection) async -> RTCSessionDescription? {
        let constraints = mediaConstraints()
        return await withCheckedContinuation { continuation in
            connection.offer(for: constraints) { description, _ in continuation.resume(returning: description) }
        }
    }

    private func requestAnswer(on connection: RTCPeerConnection) async -> RTCSessionDescription? {
        let constraints = mediaConstraints()
        return await withCheckedContinuation { continuation in
            connection.answer(for: constraints) { description, _ in continuation.resume(returning: description) }
        }
    }

    private func publishVideo(_ peer: PeerLink) {
        let track = peer.connection.transceivers.compactMap { $0.receiver.track as? RTCVideoTrack }.first
        guard let track else { return }
        DispatchQueue.main.async { self.remoteVideo[peer.remoteId] = track }
    }

    fileprivate func noteIce(_ peer: PeerLink, state: RTCIceConnectionState) {
        let label: String
        switch state {
        case .connected, .completed: label = "Connected"
        case .checking, .new: label = "Connecting"
        case .disconnected: label = "Reconnecting"
        case .failed, .closed: label = "Unavailable"
        default: label = "Connecting"
        }
        publishState(peer.remoteId, label)
        if state == .connected || state == .completed { publishVideo(peer) }
    }

    fileprivate func noteCandidate(_ candidate: RTCIceCandidate, peer: PeerLink) {
        var payload: [String: Any] = ["candidate": candidate.sdp, "sdpMLineIndex": candidate.sdpMLineIndex]
        if let mid = candidate.sdpMid { payload["sdpMid"] = mid }
        sendSignal("ice", peer.remoteId, payload)
    }

    private func enableCamera() {
#if targetEnvironment(simulator)
        DispatchQueue.main.async { self.cameraMessage = "The simulator has no camera. The microphone still connects." }
#else
        if videoTrack == nil {
            let source = Self.factory.videoSource()
            let capturer = RTCCameraVideoCapturer(delegate: source)
            videoCapturer = capturer
            let track = Self.factory.videoTrack(with: source, trackId: "video0")
            track.isEnabled = false
            videoTrack = track
            for peer in allPeers() {
                peer.connection.add(track, streamIds: ["finispeak"])
                sendOffer(peer)
            }
        }
        guard let capturer = videoCapturer, let device = RTCCameraVideoCapturer.captureDevices().first(where: { $0.position == .front }) ?? RTCCameraVideoCapturer.captureDevices().first else {
            DispatchQueue.main.async { self.cameraMessage = "This iPhone has no available camera." }
            return
        }
        let formats = RTCCameraVideoCapturer.supportedFormats(for: device).sorted {
            CMVideoFormatDescriptionGetDimensions($0.formatDescription).width < CMVideoFormatDescriptionGetDimensions($1.formatDescription).width
        }
        guard let format = formats.last, let fps = format.videoSupportedFrameRateRanges.max(by: { $0.maxFrameRate < $1.maxFrameRate }) else { return }
        capturer.startCapture(with: device, format: format, fps: min(30, Int(fps.maxFrameRate)))
        videoTrack?.isEnabled = true
        DispatchQueue.main.async {
            self.localVideo = self.videoTrack
            self.cameraOn = true
            self.cameraMessage = ""
        }
#endif
    }

    private func disableCamera() {
        videoCapturer?.stopCapture()
        videoTrack?.isEnabled = false
        DispatchQueue.main.async {
            self.cameraOn = false
            self.localVideo = nil
        }
    }

    private func configureAudioSession() {
        let audio = RTCAudioSession.sharedInstance()
        audio.lockForConfiguration()
        do {
            try audio.setCategory(AVAudioSession.Category.playAndRecord)
            try audio.setMode(AVAudioSession.Mode.voiceChat)
            try audio.overrideOutputAudioPort(.speaker)
            if !audio.isActive {
                try audio.setActive(true)
            }
        } catch {
            DispatchQueue.main.async { self.cameraMessage = "The microphone could not start." }
        }
        audio.unlockForConfiguration()
    }

    private func mediaConstraints() -> RTCMediaConstraints {
        RTCMediaConstraints(
            mandatoryConstraints: [
                kRTCMediaConstraintsOfferToReceiveAudio: kRTCMediaConstraintsValueTrue,
                kRTCMediaConstraintsOfferToReceiveVideo: kRTCMediaConstraintsValueTrue,
            ],
            optionalConstraints: nil
        )
    }

    private func sessionDescription(_ payload: [String: Any]) -> RTCSessionDescription? {
        guard let sdp = payload["sdp"] as? String, let raw = payload["type"] as? String, let type = sdpType(raw) else { return nil }
        return RTCSessionDescription(type: type, sdp: sdp)
    }

    private func iceCandidate(_ payload: [String: Any]) -> RTCIceCandidate? {
        guard let sdp = payload["candidate"] as? String else { return nil }
        let index: Int32
        if let number = payload["sdpMLineIndex"] as? Int { index = Int32(number) }
        else if let number = payload["sdpMLineIndex"] as? NSNumber { index = number.int32Value }
        else { index = 0 }
        return RTCIceCandidate(sdp: sdp, sdpMLineIndex: index, sdpMid: payload["sdpMid"] as? String)
    }

    private func sdpType(_ raw: String) -> RTCSdpType? {
        switch raw {
        case "offer": return .offer
        case "answer": return .answer
        case "pranswer": return .prAnswer
        case "rollback": return .rollback
        default: return nil
        }
    }

    private func name(for type: RTCSdpType) -> String {
        switch type {
        case .offer: return "offer"
        case .answer: return "answer"
        case .prAnswer: return "pranswer"
        case .rollback: return "rollback"
        @unknown default: return "offer"
        }
    }

    private func publishState(_ remoteId: String, _ label: String) {
        DispatchQueue.main.async { self.peerState[remoteId] = label }
    }

    private func peer(_ id: String) -> PeerLink? {
        lock.lock()
        defer { lock.unlock() }
        return peers[id]
    }

    private func currentPeerIds() -> [String] {
        lock.lock()
        defer { lock.unlock() }
        return Array(peers.keys)
    }

    private func allPeers() -> [PeerLink] {
        lock.lock()
        defer { lock.unlock() }
        return Array(peers.values)
    }

    private func store(_ peer: PeerLink) {
        lock.lock()
        peers[peer.remoteId] = peer
        lock.unlock()
    }

    private func removePeer(_ id: String) -> PeerLink? {
        lock.lock()
        defer { lock.unlock() }
        return peers.removeValue(forKey: id)
    }

    private func enqueue(_ peerId: String, _ work: @escaping () async -> Void) {
        lock.lock()
        let previous = chains[peerId]
        let task = Task {
            await previous?.value
            await work()
        }
        chains[peerId] = task
        lock.unlock()
    }
}

private final class PeerLink: NSObject, RTCPeerConnectionDelegate {
    let remoteId: String
    let connection: RTCPeerConnection
    var offerer: Bool
    var makingOffer = false
    var suppressOffer = true
    var pendingIce: [[String: Any]] = []
    weak var media: CallMedia?

    init(remoteId: String, connection: RTCPeerConnection, offerer: Bool) {
        self.remoteId = remoteId
        self.connection = connection
        self.offerer = offerer
    }

    func peerConnection(_ peerConnection: RTCPeerConnection, didChange stateChanged: RTCSignalingState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didAdd stream: RTCMediaStream) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didRemove stream: RTCMediaStream) {}
    func peerConnectionShouldNegotiate(_ peerConnection: RTCPeerConnection) {
        guard !suppressOffer, offerer else { return }
        media?.sendOffer(self)
    }
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceConnectionState) {
        media?.noteIce(self, state: newState)
    }
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceGatheringState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didGenerate candidate: RTCIceCandidate) {
        media?.noteCandidate(candidate, peer: self)
    }
    func peerConnection(_ peerConnection: RTCPeerConnection, didRemove candidates: [RTCIceCandidate]) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didOpen dataChannel: RTCDataChannel) {}
}
