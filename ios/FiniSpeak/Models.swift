import Foundation

struct Account: Codable, Identifiable, Equatable {
    var uid: String
    var email: String?
    var displayName: String?
    var phone: String?
    var role: String?
    var status: String?

    var id: String { uid }
    var name: String { displayName?.isEmpty == false ? displayName! : (email ?? "FiniSpeak") }
    var isInterpreter: Bool { role == "translator" || role == "translator_applicant" }

    var roleLabel: String {
        switch role {
        case "translator": return "Interpreter"
        case "translator_applicant": return "Interpreter applicant"
        case "admin": return "Administrator"
        default: return "Customer"
        }
    }
}

struct AuthSession: Decodable {
    var user: Account
    var accessToken: String?
    var expiresAt: String?
    var message: String?
}

struct AccountEnvelope: Decodable {
    var account: Account
}

struct Interpreter: Decodable, Identifiable, Equatable {
    var id: String
    var displayName: String
    var bio: String
    var languages: [String]
    var dialects: [String]
    var specialties: [String]
    var yearsExperience: Int
    var rating: Double
    var ratingCount: Int
    var verificationStatus: String
    var photoUrl: String?
    var availability: InterpreterAvailability
    var serviceOptions: ServiceOptions
    var serviceLocation: ServiceLocation?
    var recentReviews: [InterpreterReview]

    var name: String { displayName.isEmpty ? "Interpreter" : displayName }
    var availableNow: Bool { availability.availableNow }
    var headline: String {
        let language = (languages + dialects).prefix(2).joined(separator: " · ")
        let specialty = specialties.first ?? ""
        return [language, specialty].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let resolved = container.flexString(.id) ?? container.flexString(.uid) ?? ""
        if resolved.isEmpty { throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "Interpreter is missing an id.")) }
        id = resolved
        displayName = container.flexString(.displayName) ?? ""
        bio = container.flexString(.bio) ?? ""
        languages = container.flexStrings(.languages)
        dialects = container.flexStrings(.dialects)
        specialties = container.flexStrings(.specialties)
        yearsExperience = container.flexInt(.yearsExperience) ?? 0
        rating = container.flexDouble(.rating) ?? 0
        ratingCount = container.flexInt(.ratingCount) ?? 0
        verificationStatus = container.flexString(.verificationStatus) ?? ""
        photoUrl = container.flexString(.photoUrl)
        availability = (try? container.decode(InterpreterAvailability.self, forKey: .availability)) ?? InterpreterAvailability()
        serviceOptions = (try? container.decode(ServiceOptions.self, forKey: .serviceOptions)) ?? ServiceOptions()
        serviceLocation = try? container.decode(ServiceLocation.self, forKey: .serviceLocation)
        recentReviews = (try? container.decode([InterpreterReview].self, forKey: .recentReviews)) ?? []
    }

    private enum CodingKeys: String, CodingKey {
        case id, uid, displayName, bio, languages, dialects, specialties, yearsExperience, rating, ratingCount
        case verificationStatus, photoUrl, availability, serviceOptions, serviceLocation, recentReviews
    }
}

struct InterpreterAvailability: Decodable, Equatable {
    var availableNow = false
    var days: [String] = []
    var start = ""
    var end = ""

    init() {}

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        availableNow = container.flexBool(.availableNow) ?? false
        days = container.flexStrings(.days)
        start = container.flexString(.start) ?? ""
        end = container.flexString(.end) ?? ""
    }

    private enum CodingKeys: String, CodingKey { case availableNow, days, start, end }
}

struct ServiceOptions: Decodable, Equatable {
    var inPerson = false
    var remote = true
    var radiusMiles = 25

    init() {}

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        inPerson = container.flexBool(.inPerson) ?? false
        remote = container.flexBool(.remote) ?? true
        radiusMiles = container.flexInt(.radiusMiles) ?? 25
    }

    private enum CodingKeys: String, CodingKey { case inPerson, remote, radiusMiles }
}

struct ServiceLocation: Decodable, Equatable {
    var city: String?
    var state: String?
    var country: String?
    var latitude: Double?
    var longitude: Double?
    var showOnMap = false

    var label: String {
        [city, state, country].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: ", ")
    }

    var coordinate: (latitude: Double, longitude: Double)? {
        guard showOnMap, let latitude, let longitude else { return nil }
        guard abs(latitude) <= 90, abs(longitude) <= 180, !(latitude == 0 && longitude == 0) else { return nil }
        return (latitude, longitude)
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        city = container.flexString(.city)
        state = container.flexString(.state)
        country = container.flexString(.country)
        latitude = container.flexDouble(.latitude)
        longitude = container.flexDouble(.longitude)
        showOnMap = container.flexBool(.showOnMap) ?? false
    }

    private enum CodingKeys: String, CodingKey { case city, state, country, latitude, longitude, showOnMap }
}

struct InterpreterReview: Decodable, Identifiable, Equatable {
    var id: String
    var authorName: String
    var rating: Int
    var text: String
    var createdAt: String?

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = container.flexString(.id) ?? UUID().uuidString
        authorName = container.flexString(.authorName) ?? "FiniSpeak customer"
        rating = container.flexInt(.rating) ?? 0
        text = container.flexString(.text) ?? ""
        createdAt = container.flexString(.createdAt)
    }

    private enum CodingKeys: String, CodingKey { case id, authorName, rating, text, createdAt }
}

struct DiscoveryPage: Decodable {
    var interpreters: [Interpreter]
}

struct CallRecord: Decodable, Identifiable, Equatable {
    var id: String
    var callerId: String?
    var callerName: String?
    var receiverId: String?
    var receiverName: String?
    var translatorId: String?
    var translatorName: String?
    var invitedTranslatorId: String?
    var invitedTranslatorName: String?
    var status: String?
    var translationStatus: String?
    var purpose: String?
    var language: String?
    var specialty: String?
    var createdAt: String?
    var startedAt: String?
    var guestIds: [String]?
    var transcriptConsent: TranscriptConsent?
    var callNotes: String?

    var isLive: Bool {
        guard let status else { return false }
        return !["ended", "declined", "cancelled"].contains(status)
    }

    func otherName(than uid: String) -> String {
        if callerId == uid { return receiverName ?? "FiniSpeak user" }
        if receiverId == uid { return callerName ?? "FiniSpeak user" }
        return callerName ?? receiverName ?? "FiniSpeak call"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = container.flexString(.id) ?? UUID().uuidString
        callerId = container.flexString(.callerId)
        callerName = container.flexString(.callerName)
        receiverId = container.flexString(.receiverId)
        receiverName = container.flexString(.receiverName)
        translatorId = container.flexString(.translatorId)
        translatorName = container.flexString(.translatorName)
        invitedTranslatorId = container.flexString(.invitedTranslatorId)
        invitedTranslatorName = container.flexString(.invitedTranslatorName)
        status = container.flexString(.status)
        translationStatus = container.flexString(.translationStatus)
        purpose = container.flexString(.purpose)
        language = container.flexString(.language)
        specialty = container.flexString(.specialty)
        createdAt = container.flexString(.createdAt)
        startedAt = container.flexString(.startedAt)
        guestIds = container.flexStrings(.guestIds)
        transcriptConsent = try? container.decode(TranscriptConsent.self, forKey: .transcriptConsent)
        callNotes = container.flexString(.callNotes)
    }

    private enum CodingKeys: String, CodingKey {
        case id, callerId, callerName, receiverId, receiverName, translatorId, translatorName
        case invitedTranslatorId, invitedTranslatorName, status, translationStatus, purpose
        case language, specialty, createdAt, startedAt, guestIds, transcriptConsent, callNotes
    }
}

struct TranscriptConsent: Decodable, Equatable {
    var granted: Bool?

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        granted = container.flexBool(.granted)
    }

    private enum CodingKeys: String, CodingKey { case granted }
}

struct CallCreated: Decodable {
    var callId: String
    var call: CallRecord
}

struct CallEnvelope: Decodable {
    var call: CallRecord
}

struct CallList: Decodable {
    var calls: [CallRecord]?
    var sessions: [CallRecord]?
    var records: [CallRecord] { calls ?? sessions ?? [] }
}

struct TranscriptLine: Identifiable, Equatable {
    var id: String
    var text: String
    var speakerId: String?
    var speakerName: String?
    var speakerRole: String?
    var createdAt: String?
    var isFinal: Bool
    var localOnly: Bool

    init(id: String, text: String, speakerId: String? = nil, speakerName: String? = nil, speakerRole: String? = nil, createdAt: String? = nil, isFinal: Bool = true, localOnly: Bool = false) {
        self.id = id
        self.text = text
        self.speakerId = speakerId
        self.speakerName = speakerName
        self.speakerRole = speakerRole
        self.createdAt = createdAt
        self.isFinal = isFinal
        self.localOnly = localOnly
    }
}

struct TranscriptList: Decodable {
    var transcripts: [TranscriptPayload]
}

struct TranscriptPayload: Decodable {
    var id: String?
    var text: String?
    var speakerId: String?
    var speakerName: String?
    var speakerRole: String?
    var createdAt: String?
    var isFinal: Bool?

    func line() -> TranscriptLine? {
        guard let id, let text, !text.isEmpty else { return nil }
        return TranscriptLine(id: id, text: text, speakerId: speakerId, speakerName: speakerName, speakerRole: speakerRole, createdAt: createdAt, isFinal: isFinal ?? true)
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = container.flexString(.id)
        text = container.flexString(.text)
        speakerId = container.flexString(.speakerId)
        speakerName = container.flexString(.speakerName)
        speakerRole = container.flexString(.speakerRole)
        createdAt = container.flexString(.createdAt)
        isFinal = container.flexBool(.isFinal)
    }

    private enum CodingKeys: String, CodingKey {
        case id, text, speakerId, speakerName, speakerRole, createdAt, isFinal
    }
}

struct TranscriptSaved: Decodable {
    var transcript: TranscriptPayload?
}

struct Friend: Decodable, Identifiable, Equatable {
    var uid: String
    var displayName: String?
    var email: String?
    var phone: String?
    var nickname: String?
    var savedPhone: String?
    var online: Bool?

    var id: String { uid }
    var name: String {
        if let nickname, !nickname.isEmpty { return nickname }
        if let displayName, !displayName.isEmpty { return displayName }
        return email ?? "Friend"
    }
}

struct FriendList: Decodable { var friends: [Friend] }
struct FriendEnvelope: Decodable { var friend: Friend }

struct Conversation: Decodable, Identifiable, Equatable {
    var id: String
    var kind: String?
    var title: String?
    var unreadCount: Int?
    var memberCount: Int?
    var members: [ConversationMember]?
    var lastMessage: MessagePreview?
    var updatedAt: String?

    var name: String { title?.isEmpty == false ? title! : "Conversation" }
}

struct ConversationMember: Decodable, Identifiable, Equatable {
    var uid: String
    var displayName: String?
    var role: String?
    var online: Bool?
    var id: String { uid }
}

struct MessagePreview: Decodable, Equatable {
    var body: String?
    var senderName: String?
    var createdAt: String?
    var mine: Bool?
}

struct ConversationList: Decodable { var conversations: [Conversation] }
struct ConversationEnvelope: Decodable { var conversation: Conversation }

struct ChatMessage: Decodable, Identifiable, Equatable {
    var id: String
    var senderId: String?
    var senderName: String?
    var body: String?
    var createdAt: String?
    var mine: Bool?
}

struct ConversationDetail: Decodable {
    var conversation: Conversation
    var messages: [ChatMessage]
}

struct MessageEnvelope: Decodable { var message: ChatMessage }

struct ParticipantRecord: Decodable, Identifiable {
    var uid: String?
    var displayName: String?
    var role: String?
    var leftAt: String?
    var id: String { uid ?? UUID().uuidString }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        uid = container.flexString(.uid)
        displayName = container.flexString(.displayName)
        role = container.flexString(.role)
        leftAt = container.flexString(.leftAt)
    }

    private enum CodingKeys: String, CodingKey { case uid, displayName, role, leftAt }
}

struct ParticipantList: Decodable { var participants: [ParticipantRecord] }

struct IceServerConfig: Equatable {
    var urls: [String]
    var username: String?
    var credential: String?
}

struct ServerMessage: Decodable { var message: String?; var error: String? }

extension KeyedDecodingContainer {
    func flexString(_ key: Key) -> String? {
        if let value = try? decode(String.self, forKey: key) { return value }
        if let value = try? decode(Int.self, forKey: key) { return String(value) }
        if let value = try? decode(Double.self, forKey: key) { return String(value) }
        return nil
    }

    func flexInt(_ key: Key) -> Int? {
        if let value = try? decode(Int.self, forKey: key) { return value }
        if let value = try? decode(Double.self, forKey: key) { return Int(value) }
        if let value = try? decode(String.self, forKey: key) { return Int(value) }
        return nil
    }

    func flexDouble(_ key: Key) -> Double? {
        if let value = try? decode(Double.self, forKey: key) { return value }
        if let value = try? decode(Int.self, forKey: key) { return Double(value) }
        if let value = try? decode(String.self, forKey: key) { return Double(value) }
        return nil
    }

    func flexBool(_ key: Key) -> Bool? {
        if let value = try? decode(Bool.self, forKey: key) { return value }
        if let value = try? decode(Int.self, forKey: key) { return value != 0 }
        if let value = try? decode(String.self, forKey: key) { return ["1", "true", "yes"].contains(value.lowercased()) }
        return nil
    }

    func flexStrings(_ key: Key) -> [String] {
        if let value = try? decode([String].self, forKey: key) { return value }
        if let value = try? decode(String.self, forKey: key), !value.isEmpty { return [value] }
        return []
    }
}

enum FiniTime {
    static func label(_ value: String?) -> String {
        guard let value, !value.isEmpty else { return "" }
        let parsed = parse(value)
        guard let parsed else { return value }
        let formatter = DateFormatter()
        formatter.locale = Locale.current
        formatter.timeZone = TimeZone.current
        formatter.dateStyle = Calendar.current.isDateInToday(parsed) ? .none : .medium
        formatter.timeStyle = .short
        return formatter.string(from: parsed)
    }

    private static func parse(_ value: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: value) { return date }
        let basic = ISO8601DateFormatter()
        basic.formatOptions = [.withInternetDateTime]
        if let date = basic.date(from: value) { return date }
        return nil
    }
}
