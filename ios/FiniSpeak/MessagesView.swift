import SwiftUI

struct MessagesView: View {
    @EnvironmentObject private var app: AppModel
    var embedded = false
    @State private var conversations: [Conversation] = []
    @State private var status = "Loading messages…"
    @State private var compose = false

    var body: some View {
        ScrollView {
        VStack(alignment: .leading, spacing: 12) {
            Text("Chats").font(.subheadline.weight(.heavy)).foregroundStyle(FiniTheme.blue)
            ConceptTitle(text: "Messages")
            Text("Message another FiniSpeak user. Calls stay on Home.").foregroundStyle(.secondary)
            Button("Start a chat") { compose = true }
                .buttonStyle(ConceptFilledButtonStyle())
            if conversations.isEmpty {
                Text(status).foregroundStyle(.secondary)
            } else {
                ForEach(conversations) { conversation in
                    NavigationLink {
                        ConversationView(conversationId: conversation.id, title: conversation.name)
                    } label: {
                        HStack(spacing: 12) {
                            AvatarView(name: conversation.name, size: 48)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(conversation.name).font(.headline).foregroundStyle(FiniTheme.ink)
                                Text(conversation.lastMessage?.body ?? "No messages yet")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                            Spacer()
                            if let unread = conversation.unreadCount, unread > 0 {
                                Text("\(unread)").font(.caption.weight(.bold)).padding(.horizontal, 8).padding(.vertical, 2).background(FiniTheme.blue, in: Capsule()).foregroundStyle(.white)
                            }
                        }
                        .padding(12)
                        .background(Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(FiniTheme.line))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.horizontal, 18)
        .padding(.bottom, 12)
        }
        .navigationTitle(embedded ? "" : "Messages")
        .sheet(isPresented: $compose, onDismiss: { Task { await load() } }) { NewMessageView() }
        .task { await load() }
    }

    private func load() async {
        do {
            conversations = try await app.api.conversations()
            status = conversations.isEmpty ? "No conversations yet." : ""
        } catch {
            status = error.localizedDescription
        }
    }
}

struct NewMessageView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var email = ""
    @State private var status = ""

    var body: some View {
        NavigationStack {
            Form {
                TextField("Their FiniSpeak email", text: $email)
                    .textInputAutocapitalization(.never)
                    .keyboardType(.emailAddress)
                    .autocorrectionDisabled()
                if !status.isEmpty { Text(status) }
                Button("Start conversation") { Task { await open() } }
            }
            .navigationTitle("New message")
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } } }
        }
    }

    private func open() async {
        do {
            _ = try await app.api.openDirect(email: email.trimmingCharacters(in: .whitespacesAndNewlines))
            dismiss()
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
                    LazyVStack(alignment: .leading, spacing: 10) {
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
            if !status.isEmpty { Text(status).font(.footnote).padding(.horizontal) }
            HStack {
                TextField("Message", text: $draft, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                Button("Send") { Task { await send() } }
                    .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding(12)
        }
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .task { await refreshLoop() }
    }

    private func bubble(_ message: ChatMessage) -> some View {
        let mine = message.mine == true
        return HStack {
            if mine { Spacer(minLength: 48) }
            VStack(alignment: .leading, spacing: 2) {
                if !mine { Text(message.senderName ?? "").font(.caption).foregroundStyle(.secondary) }
                Text(message.body ?? "")
                Text(FiniTime.label(message.createdAt)).font(.caption2).foregroundStyle(.secondary)
            }
            .padding(12)
            .background(mine ? FiniTheme.blue.opacity(0.15) : Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
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
