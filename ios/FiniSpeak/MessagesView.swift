import Contacts
import SwiftUI

private struct OpenChat: Identifiable, Hashable {
    var id: String
    var title: String
}

struct MessagesView: View {
    @EnvironmentObject private var app: AppModel
    var embedded = false
    @State private var conversations: [Conversation] = []
    @State private var friends: [Friend] = []
    @State private var status = ""
    @State private var query = ""
    @State private var filter: ChatFilter = .all
    @State private var compose = false
    @State private var openChat: OpenChat?
    @State private var pendingChat: OpenChat?
    @State private var contactsLimited = false
    @State private var contactsDenied = false

    private var shown: [Conversation] {
        conversations.filter { conversation in
            switch filter {
            case .all: break
            case .unread: if (conversation.unreadCount ?? 0) < 1 { return false }
            case .groups: if conversation.kind != "group" { return false }
            }
            let needle = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard !needle.isEmpty else { return true }
            let preview = conversation.lastMessage?.body ?? ""
            return conversation.name.lowercased().contains(needle) || preview.lowercased().contains(needle)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                Text("Chats")
                    .font(.system(size: 34, weight: .bold))
                    .foregroundStyle(FiniTheme.ink)
                Spacer()
                Button { compose = true } label: {
                    Image(systemName: "plus")
                        .font(.system(size: 18, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(width: 36, height: 36)
                        .background(FiniTheme.blue, in: Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("New chat")
            }
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundStyle(FiniTheme.muted)
                TextField("Search", text: $query)
                    .textFieldStyle(.plain)
                    .foregroundStyle(FiniTheme.ink)
            }
            .padding(.horizontal, 12)
            .frame(minHeight: 40)
            .background(FiniTheme.search, in: Capsule())
            HStack(spacing: 8) {
                ForEach(ChatFilter.allCases) { item in
                    Button(item.title) { filter = item }
                        .buttonStyle(.plain)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(filter == item ? Color.white : FiniTheme.ink)
                        .padding(.horizontal, 14)
                        .frame(minHeight: 34)
                        .background(filter == item ? FiniTheme.blue : FiniTheme.chip, in: Capsule())
                }
                Spacer()
            }
            if contactsDenied {
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: "person.crop.circle.badge.exclamationmark")
                        .font(.title3)
                        .foregroundStyle(FiniTheme.blue)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Allow contact access")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(FiniTheme.ink)
                        Text("Start new chats with people saved on this iPhone.")
                            .font(.caption)
                            .foregroundStyle(FiniTheme.muted)
                    }
                    Spacer(minLength: 8)
                    Button("Settings") { openContactSettings() }
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(FiniTheme.blue)
                }
                .padding(12)
                .background(FiniTheme.field, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            } else if contactsLimited {
                Text("Some names may not appear because FiniSpeak does not have full contact access.")
                    .font(.footnote)
                    .foregroundStyle(FiniTheme.muted)
            }
            if shown.isEmpty {
                Text(status.isEmpty ? (query.isEmpty ? "No conversations yet." : "No chats match that search.") : status)
                    .foregroundStyle(FiniTheme.muted)
                    .padding(.top, 12)
                Spacer()
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(shown) { conversation in
                            Button { openChat = OpenChat(id: conversation.id, title: conversation.name) } label: {
                                chatRow(conversation)
                            }
                            .buttonStyle(.plain)
                            Divider().overlay(FiniTheme.line)
                        }
                    }
                }
            }
        }
        .padding(.horizontal, 18)
        .padding(.top, 4)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(Color.white)
        .navigationTitle(embedded ? "" : "Chats")
        .navigationDestination(item: $openChat) { chat in
            ConversationView(conversationId: chat.id, title: chat.title)
        }
        .sheet(isPresented: $compose, onDismiss: {
            if let pendingChat {
                openChat = pendingChat
                self.pendingChat = nil
            }
            Task { await load() }
        }) {
            NewChatSheet(friends: friends, conversations: conversations) { conversation in
                pendingChat = OpenChat(id: conversation.id, title: conversation.name)
                compose = false
            }
        }
        .task {
            while !Task.isCancelled {
                await load()
                try? await Task.sleep(nanoseconds: 5_000_000_000)
            }
        }
    }

    private func chatRow(_ conversation: Conversation) -> some View {
        HStack(spacing: 12) {
            AvatarView(name: conversation.name, size: 52)
            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text(conversation.name)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(FiniTheme.ink)
                        .lineLimit(1)
                    Spacer(minLength: 8)
                    Text(FiniTime.label(conversation.lastMessage?.createdAt ?? conversation.updatedAt))
                        .font(.caption)
                        .foregroundStyle(FiniTheme.muted)
                }
                HStack(alignment: .center) {
                    Text(conversation.lastMessage?.body ?? "No messages yet")
                        .font(.subheadline)
                        .foregroundStyle(FiniTheme.muted)
                        .lineLimit(1)
                    Spacer(minLength: 8)
                    if let unread = conversation.unreadCount, unread > 0 {
                        Text(unread > 99 ? "99+" : "\(unread)")
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(FiniTheme.blue, in: Capsule())
                    }
                }
            }
        }
        .padding(.vertical, 10)
    }

    private func openContactSettings() {
        if let url = URL(string: UIApplication.openSettingsURLString) {
            UIApplication.shared.open(url)
        }
    }

    private func load() async {
        do {
            conversations = try await app.api.conversations()
            friends = (try? await app.api.friends()) ?? friends
            app.unreadChats = conversations.reduce(0) { $0 + max($1.unreadCount ?? 0, 0) }
            status = ""
            let access = CNContactStore.authorizationStatus(for: .contacts)
            contactsDenied = access == .denied || access == .restricted
            if #available(iOS 18.0, *) {
                contactsLimited = access == .limited
            } else {
                contactsLimited = false
            }
        } catch {
            if conversations.isEmpty { status = error.localizedDescription }
        }
    }
}

private enum ChatFilter: String, CaseIterable, Identifiable {
    case all, unread, groups
    var id: String { rawValue }
    var title: String {
        switch self {
        case .all: return "All"
        case .unread: return "Unread"
        case .groups: return "Groups"
        }
    }
}

private struct NewChatSheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let friends: [Friend]
    let conversations: [Conversation]
    var onOpen: (Conversation) -> Void

    @State private var query = ""
    @State private var directory: [Friend] = []
    @State private var phoneContacts: [PhoneContact] = []
    @State private var access: ContactAccess = .unknown
    @State private var status = ""
    @State private var busy = false
    @State private var makingGroup = false
    @State private var makingContact = false

    private var frequent: [Friend] {
        let mine = app.account?.uid
        var ordered: [String] = []
        for conversation in conversations {
            for member in conversation.members ?? [] where member.uid != mine && !ordered.contains(member.uid) {
                ordered.append(member.uid)
            }
        }
        var byId: [String: Friend] = [:]
        for friend in listed { byId[friend.uid] = friend }
        return ordered.compactMap { byId[$0] }.prefix(6).map { $0 }
    }

    private var filteredFriends: [Friend] {
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !needle.isEmpty else { return listed.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending } }
        return listed.filter {
            $0.name.lowercased().contains(needle) || ($0.email ?? "").lowercased().contains(needle) || ($0.phone ?? "").contains(needle) || ($0.savedPhone ?? "").contains(needle)
        }.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    private var filteredContacts: [PhoneContact] {
        var known = Set<String>()
        for friend in listed {
            for value in [phoneKey(friend.phone), phoneKey(friend.savedPhone), (friend.email ?? "").lowercased()] where !value.isEmpty {
                known.insert(value)
            }
        }
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return phoneContacts.filter { contact in
            let phone = phoneKey(contact.phone)
            let email = contact.email.lowercased()
            if !phone.isEmpty, known.contains(phone) { return false }
            if !email.isEmpty, known.contains(email) { return false }
            guard !needle.isEmpty else { return true }
            return contact.name.lowercased().contains(needle) || contact.phone.contains(needle) || email.contains(needle)
        }
    }

    private var sections: [(String, [PhoneContact])] {
        let grouped = Dictionary(grouping: filteredContacts) { contact -> String in
            let letter = contact.name.first.map { String($0).uppercased() } ?? "#"
            return letter.range(of: "[A-Z]", options: .regularExpression) == nil ? "#" : letter
        }
        return grouped.keys.sorted().map { ($0, grouped[$0]!.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }) }
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass").foregroundStyle(FiniTheme.muted)
                    TextField("Name, number, or email", text: $query)
                        .textFieldStyle(.plain)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .foregroundStyle(FiniTheme.ink)
                }
                .padding(.horizontal, 12)
                .frame(minHeight: 42)
                .background(FiniTheme.search, in: Capsule())
                .padding(.horizontal, 16)
                .padding(.bottom, 8)
                ScrollViewReader { proxy in
                    HStack(alignment: .top, spacing: 0) {
                        ScrollView {
                            VStack(alignment: .leading, spacing: 0) {
                                actionRow("person.2", "New group") { makingGroup = true }
                                actionRow("person.badge.plus", "New contact") { makingContact = true }
                                if query.isEmpty, !frequent.isEmpty {
                                    sectionTitle("Frequently contacted")
                                    ForEach(frequent) { friend in
                                        personRow(friend.name, detail: friend.online == true ? "Online" : "FiniSpeak") { Task { await openFriend(friend) } }
                                    }
                                }
                                sectionTitle("Contacts on FiniSpeak")
                                if filteredFriends.isEmpty {
                                    Text(listed.isEmpty ? "Add a FiniSpeak friend to message them here." : "No friends match that search.")
                                        .font(.subheadline)
                                        .foregroundStyle(FiniTheme.muted)
                                        .padding(.horizontal, 16)
                                        .padding(.vertical, 8)
                                }
                                ForEach(filteredFriends) { friend in
                                    personRow(friend.name, detail: friend.phone ?? friend.email ?? "FiniSpeak") { Task { await openFriend(friend) } }
                                }
                                if access == .denied {
                                    accessCard
                                } else if !sections.isEmpty {
                                    sectionTitle("Contacts")
                                    ForEach(sections, id: \.0) { letter, people in
                                        Text(letter)
                                            .font(.footnote.weight(.bold))
                                            .foregroundStyle(FiniTheme.muted)
                                            .padding(.horizontal, 16)
                                            .padding(.top, 10)
                                            .id(letter)
                                        ForEach(people) { contact in
                                            personRow(contact.name, detail: contact.phone.isEmpty ? contact.email : contact.phone) {
                                                Task { await openPhone(contact) }
                                            }
                                        }
                                    }
                                }
                                if !status.isEmpty {
                                    Text(status).font(.footnote).foregroundStyle(FiniTheme.ink).padding(16)
                                }
                            }
                            .padding(.bottom, 24)
                        }
                        if query.isEmpty, sections.count > 1 {
                            VStack(spacing: 1) {
                                ForEach(sections.map(\.0), id: \.self) { letter in
                                    Button(letter) { proxy.scrollTo(letter, anchor: .top) }
                                        .buttonStyle(.plain)
                                        .font(.system(size: 11, weight: .bold))
                                        .foregroundStyle(FiniTheme.blue)
                                }
                            }
                            .padding(.trailing, 4)
                            .padding(.top, 8)
                        }
                    }
                }
            }
            .background(Color.white)
            .navigationTitle("New chat")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button { dismiss() } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundStyle(FiniTheme.ink)
                            .frame(width: 32, height: 32)
                            .background(FiniTheme.soft, in: Circle())
                    }
                }
            }
            .sheet(isPresented: $makingGroup) {
                NewGroupSheet(friends: listed) { conversation in
                    makingGroup = false
                    onOpen(conversation)
                }
            }
            .sheet(isPresented: $makingContact) {
                NewContactSheet { conversation in
                    makingContact = false
                    onOpen(conversation)
                }
            }
            .task {
                if let fresh = try? await app.api.friends() { directory = fresh }
                await loadContacts()
            }
        }
    }

    private var accessCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Allow contact access")
                .font(.headline)
                .foregroundStyle(FiniTheme.ink)
            Text("Full access lets you start a chat with people saved on this iPhone.")
                .font(.subheadline)
                .foregroundStyle(FiniTheme.muted)
            Button("Open Settings") {
                if let url = URL(string: UIApplication.openSettingsURLString) {
                    UIApplication.shared.open(url)
                }
            }
            .buttonStyle(ConceptFilledButtonStyle())
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(FiniTheme.field, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .padding(16)
    }

    private func sectionTitle(_ title: String) -> some View {
        Text(title)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(FiniTheme.muted)
            .padding(.horizontal, 16)
            .padding(.top, 18)
            .padding(.bottom, 6)
    }

    private func actionRow(_ symbol: String, _ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Image(systemName: symbol)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(FiniTheme.blue)
                    .frame(width: 36, height: 36)
                    .background(FiniTheme.avatarFill, in: Circle())
                Text(title).font(.body.weight(.semibold)).foregroundStyle(FiniTheme.ink)
                Spacer()
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
        }
        .buttonStyle(.plain)
    }

    private func personRow(_ name: String, detail: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 12) {
                AvatarView(name: name, size: 44)
                VStack(alignment: .leading, spacing: 2) {
                    Text(name).font(.body.weight(.semibold)).foregroundStyle(FiniTheme.ink)
                    if !detail.isEmpty {
                        Text(detail).font(.caption).foregroundStyle(FiniTheme.muted).lineLimit(1)
                    }
                }
                Spacer()
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 7)
        }
        .buttonStyle(.plain)
        .disabled(busy)
    }

    private func openFriend(_ friend: Friend) async {
        await start { try await app.api.openDirect(userId: friend.uid) }
    }

    private var listed: [Friend] { directory.isEmpty ? friends : directory }

    private func openPhone(_ contact: PhoneContact) async {
        await start {
            if !contact.email.isEmpty {
                do { return try await app.api.openDirect(email: contact.email) } catch {
                    if contact.phone.isEmpty { throw error }
                }
            }
            return try await app.api.openDirect(phone: contact.phone)
        }
    }

    private func start(_ work: () async throws -> Conversation) async {
        busy = true
        defer { busy = false }
        do {
            let conversation = try await work()
            onOpen(conversation)
        } catch {
            status = error.localizedDescription
        }
    }

    private func loadContacts() async {
        let store = CNContactStore()
        let granted = await withCheckedContinuation { continuation in
            store.requestAccess(for: .contacts) { ok, _ in continuation.resume(returning: ok) }
        }
        let current = CNContactStore.authorizationStatus(for: .contacts)
        if #available(iOS 18.0, *), current == .limited {
            access = .limited
        } else {
            access = granted || current == .authorized ? .granted : .denied
        }
        guard access == .granted || access == .limited else { return }
        let keys = [CNContactGivenNameKey, CNContactFamilyNameKey, CNContactPhoneNumbersKey, CNContactEmailAddressesKey] as [CNKeyDescriptor]
        let request = CNContactFetchRequest(keysToFetch: keys)
        var found: [PhoneContact] = []
        try? store.enumerateContacts(with: request) { contact, _ in
            let name = [contact.givenName, contact.familyName].filter { !$0.isEmpty }.joined(separator: " ")
            let phone = contact.phoneNumbers.first?.value.stringValue ?? ""
            let email = (contact.emailAddresses.first?.value as String?) ?? ""
            guard !name.isEmpty, !phone.isEmpty || !email.isEmpty else { return }
            found.append(PhoneContact(id: contact.identifier, name: name, phone: phone, email: email))
        }
        phoneContacts = found.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    private func phoneKey(_ value: String?) -> String {
        let numbers = value?.filter(\.isNumber) ?? ""
        return numbers.count >= 10 ? String(numbers.suffix(10)) : numbers
    }
}

private enum ContactAccess { case unknown, granted, limited, denied }

private struct PhoneContact: Identifiable {
    var id: String
    var name: String
    var phone: String
    var email: String
}

private struct NewGroupSheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let friends: [Friend]
    var onOpen: (Conversation) -> Void
    @State private var title = ""
    @State private var selected: Set<String> = []
    @State private var status = ""

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 12) {
                TextField("Group name", text: $title)
                    .textFieldStyle(.roundedBorder)
                    .padding(.horizontal, 16)
                ScrollView {
                    VStack(spacing: 0) {
                        ForEach(friends) { friend in
                            Button {
                                if selected.contains(friend.uid) { selected.remove(friend.uid) } else { selected.insert(friend.uid) }
                            } label: {
                                HStack(spacing: 12) {
                                    AvatarView(name: friend.name, size: 40)
                                    Text(friend.name).foregroundStyle(FiniTheme.ink)
                                    Spacer()
                                    Image(systemName: selected.contains(friend.uid) ? "checkmark.circle.fill" : "circle")
                                        .foregroundStyle(selected.contains(friend.uid) ? FiniTheme.blue : FiniTheme.muted)
                                }
                                .padding(.horizontal, 16)
                                .padding(.vertical, 8)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                if !status.isEmpty { Text(status).font(.footnote).foregroundStyle(FiniTheme.ink).padding(.horizontal, 16) }
                Button("Create group") { Task { await create() } }
                    .buttonStyle(ConceptFilledButtonStyle())
                    .padding(.horizontal, 16)
                    .disabled(title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || selected.isEmpty)
            }
            .padding(.top, 12)
            .background(Color.white)
            .navigationTitle("New group")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } } }
        }
    }

    private func create() async {
        do {
            let conversation = try await app.api.createGroup(title: title.trimmingCharacters(in: .whitespacesAndNewlines), memberIds: Array(selected))
            onOpen(conversation)
        } catch {
            status = error.localizedDescription
        }
    }
}

private struct NewContactSheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    var onOpen: (Conversation) -> Void
    @State private var email = ""
    @State private var phone = ""
    @State private var nickname = ""
    @State private var status = ""

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 12) {
                Text("Add someone who already has FiniSpeak, then open the chat.")
                    .font(.subheadline)
                    .foregroundStyle(FiniTheme.muted)
                TextField("FiniSpeak email", text: $email)
                    .textFieldStyle(.roundedBorder)
                    .textInputAutocapitalization(.never)
                    .keyboardType(.emailAddress)
                    .autocorrectionDisabled()
                TextField("Or phone number", text: $phone)
                    .textFieldStyle(.roundedBorder)
                    .keyboardType(.phonePad)
                TextField("Nickname", text: $nickname)
                    .textFieldStyle(.roundedBorder)
                if !status.isEmpty { Text(status).font(.footnote).foregroundStyle(FiniTheme.ink) }
                Button("Save and message") { Task { await save() } }
                    .buttonStyle(ConceptFilledButtonStyle())
                Spacer()
            }
            .padding(16)
            .background(Color.white)
            .navigationTitle("New contact")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } } }
        }
    }

    private func save() async {
        let trimmedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedPhone = phone.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            _ = try? await app.api.addFriend(email: trimmedEmail, phone: trimmedPhone, nickname: nickname.trimmingCharacters(in: .whitespacesAndNewlines))
            let conversation = try await app.api.openDirect(email: trimmedEmail.isEmpty ? nil : trimmedEmail, phone: trimmedPhone.isEmpty ? nil : trimmedPhone)
            onOpen(conversation)
        } catch {
            status = error.localizedDescription
        }
    }
}

struct ConversationView: View {
    @EnvironmentObject private var app: AppModel
    let conversationId: String
    let title: String
    @State private var messages: [ChatMessage] = []
    @State private var draft = ""
    @State private var status = ""

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(messages) { message in
                            bubble(message).id(message.id)
                        }
                    }
                    .padding(16)
                }
                .onChange(of: messages.count) {
                    if let last = messages.last { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
            if !status.isEmpty { Text(status).font(.footnote).foregroundStyle(FiniTheme.muted).padding(.horizontal) }
            HStack(spacing: 8) {
                TextField("Message", text: $draft, axis: .vertical)
                    .textFieldStyle(.plain)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(FiniTheme.search, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                Button { Task { await send() } } label: {
                    Image(systemName: "paperplane.fill")
                        .font(.system(size: 16, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(width: 36, height: 36)
                        .background(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? FiniTheme.muted : FiniTheme.blue, in: Circle())
                }
                .buttonStyle(.plain)
                .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding(12)
            .background(Color.white)
        }
        .background(FiniTheme.field)
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .toolbarBackground(Color.white, for: .navigationBar)
        .task { await refreshLoop() }
    }

    private func bubble(_ message: ChatMessage) -> some View {
        let mine = message.mine == true
        return HStack {
            if mine { Spacer(minLength: 48) }
            VStack(alignment: mine ? .trailing : .leading, spacing: 2) {
                if !mine, let name = message.senderName, !name.isEmpty {
                    Text(name).font(.caption.weight(.semibold)).foregroundStyle(FiniTheme.muted)
                }
                Text(message.body ?? "")
                    .foregroundStyle(mine ? Color.white : FiniTheme.ink)
                Text(FiniTime.label(message.createdAt))
                    .font(.caption2)
                    .foregroundStyle(mine ? Color.white.opacity(0.8) : FiniTheme.muted)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(mine ? FiniTheme.blue : Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            if !mine { Spacer(minLength: 48) }
        }
    }

    private func refreshLoop() async {
        while !Task.isCancelled {
            await load()
            try? await Task.sleep(nanoseconds: 4_000_000_000)
        }
    }

    private func load() async {
        do {
            messages = try await app.api.conversation(id: conversationId).messages
            status = ""
        } catch {
            status = error.localizedDescription
        }
    }

    private func send() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        draft = ""
        do {
            let saved = try await app.api.sendMessage(conversationId: conversationId, body: text)
            messages.append(saved)
        } catch {
            draft = text
            status = error.localizedDescription
        }
    }
}
