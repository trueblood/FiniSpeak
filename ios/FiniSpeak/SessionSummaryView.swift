import SwiftUI

struct SessionSummaryView: View {
    @ObservedObject var session: CallSession
    @EnvironmentObject private var app: AppModel
    @Environment(\.openURL) private var openURL
    @State private var rating = 0
    @State private var quality = 0
    @State private var logging = 0
    @State private var ratingNote = ""
    @State private var category = "Education"
    @State private var showingTranscript = false

    var body: some View {
        VStack(spacing: 0) {
            ConceptHeader(
                onSearch: { leave(to: .discover) },
                onAccount: { leave(to: .settings) },
                accountSymbol: "gearshape"
            )
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Button { session.closeSummary() } label: {
                        Label("Back", systemImage: "chevron.left")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(FiniTheme.ink)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(FiniTheme.soft, in: Capsule())
                    }
                    .buttonStyle(.plain)
                    Text("Session Summary")
                        .font(.system(size: 32, weight: .bold))
                        .foregroundStyle(FiniTheme.ink)
                        .padding(.top, 16)
                    people
                        .frame(maxWidth: .infinity)
                        .padding(.top, 8)
                    Text(whenLabel)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(FiniTheme.ink)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 8)
                        .padding(.bottom, 16)
                    Button { showingTranscript = true } label: {
                        HStack(spacing: 8) {
                            Image(systemName: "doc.text")
                            Text("View Transcription")
                        }
                        .font(.system(size: 17, weight: .heavy))
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity, minHeight: 52)
                        .background(FiniTheme.blue, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    }
                    .buttonStyle(.plain)
                    .padding(.top, 4)
                    Button("Send via Email") { sendEmail() }
                        .buttonStyle(.plain)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(FiniTheme.blue)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                    if session.canRate {
                        Text("Rate the translation")
                            .font(.title3.weight(.bold))
                            .foregroundStyle(FiniTheme.ink)
                            .frame(maxWidth: .infinity)
                        starRow(selected: rating) { star in
                            rating = star
                            Task { ratingNote = await session.rate(star) }
                        }
                        if !ratingNote.isEmpty {
                            Text(ratingNote)
                                .font(.footnote)
                                .foregroundStyle(FiniTheme.muted)
                                .frame(maxWidth: .infinity)
                                .padding(.top, 4)
                        }
                    } else {
                        Text("Rate call quality")
                            .font(.title3.weight(.bold))
                            .foregroundStyle(FiniTheme.ink)
                            .frame(maxWidth: .infinity)
                        starRow(selected: quality) { star in
                            quality = star
                            Task { await session.rateSession(quality: quality, logging: logging) }
                        }
                        Text("Rate audio logging")
                            .font(.title3.weight(.bold))
                            .foregroundStyle(FiniTheme.ink)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 14)
                        starRow(selected: logging) { star in
                            logging = star
                            Task { await session.rateSession(quality: quality, logging: logging) }
                        }
                    }
                    Button("Book Again") { leave(to: .discover) }
                        .buttonStyle(.plain)
                        .font(.system(size: 17, weight: .heavy))
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity, minHeight: 52)
                        .background(FiniTheme.blue, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .padding(.top, 16)
                    Text("Flagged moments")
                        .font(.title3.weight(.bold))
                        .foregroundStyle(FiniTheme.ink)
                        .padding(.top, 22)
                    flaggedMoments
                        .padding(.top, 8)
                }
                .padding(.horizontal, 18)
                .padding(.bottom, 16)
            }
            HStack(spacing: 8) {
                ForEach(["Business", "Education", "Personal"], id: \.self) { name in
                    Button(name) { category = name }
                        .buttonStyle(.plain)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(category == name ? Color.white : FiniTheme.ink)
                        .frame(maxWidth: .infinity, minHeight: 40)
                        .background(category == name ? FiniTheme.blue : FiniTheme.chip, in: Capsule())
                }
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 8)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(Color.white)
        .environment(\.goHome) { session.closeSummary() }
        .sheet(isPresented: $showingTranscript) { transcriptSheet }
    }

    private func starRow(selected: Int, choose: @escaping (Int) -> Void) -> some View {
        HStack(spacing: 8) {
            ForEach(1...5, id: \.self) { star in
                Button { choose(star) } label: {
                    Text("★")
                        .font(.system(size: 38))
                        .foregroundStyle(star <= selected ? Color(red: 217 / 255, green: 119 / 255, blue: 6 / 255) : FiniTheme.star)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("\(star) star")
            }
        }
        .frame(maxWidth: .infinity)
    }

    private var people: some View {
        let other = session.people.first?.name ?? session.call.otherName(than: session.userId)
        return HStack(spacing: 36) {
            person(other)
            person(session.selfName)
        }
    }

    private func person(_ name: String) -> some View {
        VStack(spacing: 8) {
            Text(FiniTheme.initials(name))
                .font(.system(size: 28, weight: .bold))
                .foregroundStyle(FiniTheme.avatarInk)
                .frame(width: 104, height: 104)
                .background(FiniTheme.avatarFill, in: Circle())
            Text(name)
                .font(.system(size: 18, weight: .bold))
                .foregroundStyle(FiniTheme.blue)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private var flaggedMoments: some View {
        let moments = session.call.keyMoments ?? []
        if moments.isEmpty {
            Text("Flagged moments show up here for follow-up.")
                .font(.subheadline)
                .foregroundStyle(FiniTheme.muted)
        } else {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(moments) { moment in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(momentTitle(moment))
                            .font(.subheadline.weight(.bold))
                            .foregroundStyle(FiniTheme.ink)
                        Text(momentLine(moment))
                            .font(.subheadline)
                            .foregroundStyle(FiniTheme.muted)
                        if moment.followUp == false {
                            Text("Resolved").font(.caption.weight(.semibold)).foregroundStyle(FiniTheme.muted)
                        } else {
                            Button("Done") { Task { await session.resolveMoment(moment.id) } }
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(FiniTheme.blue)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
    }

    private var transcriptSheet: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if session.transcripts.isEmpty {
                        Text("No transcription was saved for this call.")
                            .foregroundStyle(FiniTheme.muted)
                    }
                    ForEach(session.transcripts) { line in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(line.speakerName ?? "Speaker")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(FiniTheme.blue)
                            Text(line.text).foregroundStyle(FiniTheme.ink)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(20)
            }
            .background(Color.white)
            .navigationTitle("Transcription")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { showingTranscript = false } } }
        }
    }

    private var whenLabel: String {
        let end = session.endedAt ?? Date()
        return "\(Self.clock.string(from: session.elapsedStart)) – \(Self.clock.string(from: end))"
    }

    private func leave(to section: FiniSection) {
        app.pendingSection = section
        session.closeSummary()
    }

    private func sendEmail() {
        let lines = session.transcripts.map { "\($0.speakerName ?? "Speaker"): \($0.text)" }
        let body = lines.isEmpty ? "FiniSpeak session summary" : lines.joined(separator: "\n")
        var parts = URLComponents()
        parts.scheme = "mailto"
        parts.queryItems = [
            URLQueryItem(name: "subject", value: "FiniSpeak session summary"),
            URLQueryItem(name: "body", value: body),
        ]
        if let url = parts.url { openURL(url) }
    }

    private func momentTitle(_ moment: KeyMoment) -> String {
        let when = moment.elapsedLabel?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return when.isEmpty ? "Flagged moment" : when
    }

    private func momentLine(_ moment: KeyMoment) -> String {
        let line = [moment.speakerName, moment.text].compactMap { value -> String? in
            let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return trimmed.isEmpty ? nil : trimmed
        }
        return line.isEmpty ? "Marked for follow-up." : line.joined(separator: ": ")
    }

    private static let clock: DateFormatter = {
        let formatter = DateFormatter()
        formatter.timeStyle = .short
        formatter.dateStyle = .none
        return formatter
    }()
}
