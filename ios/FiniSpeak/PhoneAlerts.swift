import AVFoundation
import CallKit
import Foundation
import UserNotifications
import WebRTC

/// Incoming calls use the iPhone call screen. Messages use a banner and a short chime.
final class PhoneAlerts: NSObject, CXProviderDelegate, UNUserNotificationCenterDelegate {
    static let shared = PhoneAlerts()

    var onAnswer: ((String) -> Void)?
    var onDecline: ((String) -> Void)?
    var onHangUp: ((String) -> Void)?
    var onOpenMessages: (() -> Void)?

    private let provider: CXProvider
    private let queue = DispatchQueue(label: "com.finispeak.alerts")
    private var callUUIDs: [String: UUID] = [:]
    private var callIDs: [UUID: String] = [:]
    private var answered: Set<UUID> = []
    private var ending: Set<UUID> = []
    private var fallbackRing: AVAudioPlayer?
    private var dingPlayer: AVAudioPlayer?

    private override init() {
        let config = CXProviderConfiguration()
        config.supportsVideo = false
        config.maximumCallGroups = 1
        config.maximumCallsPerCallGroup = 1
        config.supportedHandleTypes = [.generic]
        config.includesCallsInRecents = true
        config.ringtoneSound = "call-ring.wav"
        provider = CXProvider(configuration: config)
        super.init()
        provider.setDelegate(self, queue: queue)
        UNUserNotificationCenter.current().delegate = self
    }

    func requestPermission() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in }
    }

    func ring(callId: String, caller: String, completion: @escaping (Bool) -> Void) {
        queue.async {
            if self.callUUIDs[callId] != nil {
                DispatchQueue.main.async { completion(true) }
                return
            }
            let uuid = UUID()
            self.callUUIDs[callId] = uuid
            self.callIDs[uuid] = callId
            let update = CXCallUpdate()
            update.remoteHandle = CXHandle(type: .generic, value: caller)
            update.localizedCallerName = caller
            update.hasVideo = false
            update.supportsHolding = false
            update.supportsGrouping = false
            update.supportsUngrouping = false
            update.supportsDTMF = false
            self.provider.reportNewIncomingCall(with: uuid, update: update) { error in
                self.queue.async {
                    if error != nil {
                        self.callUUIDs[callId] = nil
                        self.callIDs[uuid] = nil
                    }
                    DispatchQueue.main.async {
                        if error == nil {
                            self.stopFallbackRing()
                            completion(true)
                        } else {
                            self.startFallbackRing()
                            completion(false)
                        }
                    }
                }
            }
        }
    }

    func stopRingingTone() {
        DispatchQueue.main.async { self.stopFallbackRing() }
    }

    func end(callId: String, reason: CXCallEndedReason) {
        stopFallbackRing()
        queue.async {
            guard let uuid = self.callUUIDs.removeValue(forKey: callId) else { return }
            self.ending.insert(uuid)
            self.provider.reportCall(with: uuid, endedAt: Date(), reason: reason)
        }
    }

    func ding(from name: String, text: String) {
        let content = UNMutableNotificationContent()
        content.title = name.isEmpty ? "FiniSpeak" : name
        content.body = text.isEmpty ? "New message" : text
        content.sound = UNNotificationSound(named: UNNotificationSoundName("message-ding.wav"))
        content.threadIdentifier = "finispeak-messages"
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            let allowed = settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional
            if allowed {
                UNUserNotificationCenter.current().add(request)
            } else {
                self.playDing()
            }
        }
    }

    func setBadge(_ count: Int) {
        let value = max(0, count)
        Task { try? await UNUserNotificationCenter.current().setBadgeCount(value) }
    }

    func providerDidReset(_ provider: CXProvider) {
        callUUIDs.removeAll()
        callIDs.removeAll()
        answered.removeAll()
        ending.removeAll()
        DispatchQueue.main.async { self.stopFallbackRing() }
    }

    func provider(_ provider: CXProvider, perform action: CXAnswerCallAction) {
        answered.insert(action.callUUID)
        action.fulfill()
        let callId = callIDs[action.callUUID]
        DispatchQueue.main.async {
            self.stopFallbackRing()
            if let callId { self.onAnswer?(callId) }
        }
    }

    func provider(_ provider: CXProvider, perform action: CXEndCallAction) {
        let uuid = action.callUUID
        action.fulfill()
        if ending.contains(uuid) {
            ending.remove(uuid)
            callIDs[uuid] = nil
            return
        }
        let callId = callIDs.removeValue(forKey: uuid)
        if let callId { callUUIDs[callId] = nil }
        let wasAnswered = answered.contains(uuid)
        answered.remove(uuid)
        DispatchQueue.main.async {
            self.stopFallbackRing()
            guard let callId else { return }
            if wasAnswered { self.onHangUp?(callId) } else { self.onDecline?(callId) }
        }
    }

    func provider(_ provider: CXProvider, didActivate audioSession: AVAudioSession) {
        let session = RTCAudioSession.sharedInstance()
        session.audioSessionDidActivate(audioSession)
        session.isAudioEnabled = true
    }

    func provider(_ provider: CXProvider, didDeactivate audioSession: AVAudioSession) {
        RTCAudioSession.sharedInstance().audioSessionDidDeactivate(audioSession)
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .sound, .list, .badge]
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        if response.notification.request.content.threadIdentifier == "finispeak-messages" {
            onOpenMessages?()
        }
    }

    private func playDing() {
        guard let url = Bundle.main.url(forResource: "message-ding", withExtension: "wav") else { return }
        DispatchQueue.main.async {
            self.play(url: url, loops: false)
        }
    }

    private func startFallbackRing() {
        guard let url = Bundle.main.url(forResource: "call-ring", withExtension: "wav") else { return }
        play(url: url, loops: true)
    }

    private func stopFallbackRing() {
        fallbackRing?.stop()
        fallbackRing = nil
    }

    private func play(url: URL, loops: Bool) {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playback, mode: .default, options: [.mixWithOthers])
        try? session.setActive(true)
        guard let player = try? AVAudioPlayer(contentsOf: url) else { return }
        player.numberOfLoops = loops ? -1 : 0
        player.prepareToPlay()
        player.play()
        if loops { fallbackRing = player } else { dingPlayer = player }
    }
}
