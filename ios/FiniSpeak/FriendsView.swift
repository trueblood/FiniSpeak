import SwiftUI

struct FriendsView: View {
    @EnvironmentObject private var app: AppModel
    var embedded = false
    @State private var friends: [Friend] = []
    @State private var email = ""
    @State private var nickname = ""
    @State private var status = ""

    var body: some View {
        ScrollView {
        VStack(alignment: .leading, spacing: 14) {
            Text("Your contacts").font(.subheadline.weight(.heavy)).foregroundStyle(FiniTheme.blue)
            ConceptTitle(text: "Friends")
            Text("Save FiniSpeak contacts and see who is recently online.").foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 10) {
                Text("Add a friend").font(.headline)
                ConceptField(title: "FiniSpeak email", text: $email, keyboard: .emailAddress, contentType: .emailAddress)
                ConceptField(title: "Nickname", text: $nickname, contentType: .nickname)
                Button("Add friend") { Task { await add() } }
                    .buttonStyle(ConceptFilledButtonStyle())
                if !status.isEmpty { Text(status).font(.footnote).foregroundStyle(FiniTheme.ink) }
            }
            .padding(16)
            .background(Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(FiniTheme.line))
            Text("Friends list").font(.headline)
            if friends.isEmpty {
                Text("Friends you add can be called from Home.").foregroundStyle(.secondary)
            } else {
                ForEach(friends) { friend in
                    FriendRow(friend: friend) { await reload() }
                        .padding(12)
                        .background(Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(FiniTheme.line))
                }
            }
        }
        .padding(.horizontal, 18)
        .padding(.bottom, 12)
        }
        .navigationTitle(embedded ? "" : "Friends")
        .task { await reload() }
    }

    private func reload() async {
        do {
            friends = try await app.api.friends()
            status = ""
        } catch {
            status = error.localizedDescription
        }
    }

    private func add() async {
        do {
            _ = try await app.api.addFriend(email: email.trimmingCharacters(in: .whitespacesAndNewlines), nickname: nickname.trimmingCharacters(in: .whitespacesAndNewlines))
            email = ""
            nickname = ""
            status = "Friend added."
            await reload()
        } catch {
            status = error.localizedDescription
        }
    }
}

private struct FriendRow: View {
    @EnvironmentObject private var app: AppModel
    let friend: Friend
    var changed: () async -> Void
    @State private var nickname = ""
    @State private var phone = ""
    @State private var status = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Circle().fill(friend.online == true ? Color.green : Color.gray.opacity(0.4)).frame(width: 10, height: 10)
                Text(friend.name).font(.headline)
                Spacer()
                Text(friend.online == true ? "Online" : "Offline").font(.caption).foregroundStyle(.secondary)
            }
            Text(friend.email ?? "").font(.caption).foregroundStyle(.secondary)
            TextField("Nickname", text: $nickname)
            TextField("Saved number", text: $phone).keyboardType(.phonePad)
            HStack {
                Button("Save") { Task { await save() } }
                Button("Call") { Task { await call() } }
                Button("Message") { Task { await message() } }
                Button("Remove", role: .destructive) { Task { await remove() } }
            }
            .font(.subheadline)
            if !status.isEmpty { Text(status).font(.caption) }
        }
        .padding(.vertical, 4)
        .onAppear {
            nickname = friend.nickname ?? ""
            phone = friend.savedPhone ?? friend.phone ?? ""
        }
    }

    private func save() async {
        do {
            _ = try await app.api.updateFriend(id: friend.uid, nickname: nickname, savedPhone: phone)
            status = "Saved."
            await changed()
        } catch { status = error.localizedDescription }
    }

    private func call() async {
        do { try await app.placeCall(receiverId: friend.uid) }
        catch { status = error.localizedDescription }
    }

    private func message() async {
        do { _ = try await app.api.openDirect(userId: friend.uid); status = "Conversation opened in Messages." }
        catch { status = error.localizedDescription }
    }

    private func remove() async {
        do { try await app.api.removeFriend(id: friend.uid); await changed() }
        catch { status = error.localizedDescription }
    }
}
