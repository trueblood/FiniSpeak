import SwiftUI
import WebRTC

struct CallView: View {
    @ObservedObject var session: CallSession
    @ObservedObject var media: CallMedia
    @State private var inviting = false
    @State private var interpreters: [Interpreter] = []
    @State private var note = ""
    @State private var noteReady = false
    @State private var noteSave: Task<Void, Never>?
    @State private var category = "Education"
    @State private var booking = false

    init(session: CallSession) {
        self.session = session
        media = session.media
    }

    private var showVideo: Bool { media.cameraOn || !media.remoteVideo.isEmpty }

    var body: some View {
        Group {
            if session.ended {
                SessionSummaryView(session: session)
            } else if showVideo {
                videoCall
            } else {
                audioCall
            }
        }
        .sheet(isPresented: $inviting) { inviteSheet }
        .sheet(isPresented: $booking) { bookingSheet }
    }

    private var audioCall: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                ConceptGlobe(size: 32)
                Text("FiniSpeak").font(.system(size: 22, weight: .bold)).foregroundStyle(FiniTheme.ink)
                Spacer()
            }
            .padding(.horizontal, 18)
            .padding(.top, 8)
            faces
            TimelineView(.periodic(from: session.elapsedStart, by: 1)) { context in
                Text(elapsedLabel(since: session.elapsedStart, now: context.date))
                    .font(.system(size: 44, weight: .heavy))
                    .foregroundStyle(FiniTheme.ink)
                    .monospacedDigit()
            }
            .padding(.top, 14)
            .padding(.bottom, 6)
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    audioControls
                        .frame(maxWidth: .infinity)
                        .padding(.bottom, 16)
                    Text("Live transcription")
                        .font(.system(size: 20, weight: .bold))
                        .foregroundStyle(FiniTheme.ink)
                        .padding(.bottom, 10)
                    if session.transcripts.isEmpty {
                        Text("Live transcription appears here as people speak.")
                            .font(.subheadline)
                            .foregroundStyle(FiniTheme.muted)
                    } else {
                        VStack(alignment: .leading, spacing: 10) {
                            ForEach(session.transcripts) { line in
                                audioLine(line)
                            }
                        }
                    }
                    if !session.banner.isEmpty {
                        Text(session.banner).font(.footnote).foregroundStyle(FiniTheme.muted).padding(.top, 8)
                    }
                    HStack(spacing: 8) {
                        TextField("Add a note...", text: $note)
                            .textFieldStyle(.plain)
                            .foregroundStyle(FiniTheme.ink)
                        Button("Flag Key Moment") { Task { await session.flagMoment() } }
                            .font(.subheadline.weight(.bold))
                            .foregroundStyle(session.momentFlagged ? Color(red: 180 / 255, green: 83 / 255, blue: 9 / 255) : FiniTheme.blue)
                            .layoutPriority(1)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 4)
                    .background(Color.white, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(FiniTheme.line, lineWidth: 1))
                    .padding(.top, 14)
                    Button("Book Now") { booking = true }
                        .buttonStyle(.plain)
                        .font(.system(size: 17, weight: .heavy))
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity, minHeight: 52)
                        .background(FiniTheme.blue, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .padding(.top, 12)
                }
                .padding(.horizontal, 18)
                .padding(.bottom, 12)
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
        .onAppear {
            guard !noteReady else { return }
            note = session.call.callNotes ?? ""
            noteReady = true
        }
        .onChange(of: note) { _, value in
            guard noteReady else { return }
            noteSave?.cancel()
            noteSave = Task {
                try? await Task.sleep(nanoseconds: 400_000_000)
                guard !Task.isCancelled else { return }
                await session.saveNote(value)
            }
        }
    }

    private var faces: some View {
        let others = session.people.isEmpty ? [CallPerson(id: "waiting", name: "Waiting", role: "", state: "")] : session.people
        let mine = CallPerson(id: session.userId, name: session.selfName, role: "", state: "")
        return HStack(spacing: 28) {
            ForEach(others + [mine]) { person in
                VStack(spacing: 8) {
                    Text(FiniTheme.initials(person.name))
                        .font(.system(size: person.name == "Waiting" ? 22 : 28, weight: .bold))
                        .foregroundStyle(FiniTheme.avatarInk)
                        .frame(width: others.count > 1 ? 72 : 104, height: others.count > 1 ? 72 : 104)
                        .background(FiniTheme.avatarFill, in: Circle())
                    Text(person.name)
                        .font(.system(size: 18, weight: .bold))
                        .foregroundStyle(FiniTheme.blue)
                        .lineLimit(2)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
            }
        }
        .padding(.horizontal, 18)
        .padding(.top, 12)
    }

    private var audioControls: some View {
        HStack(spacing: 22) {
            Button {
                media.setMicrophone(on: !media.microphoneOn)
            } label: {
                Image(systemName: media.microphoneOn ? "mic.fill" : "mic.slash.fill")
                    .font(.system(size: 24, weight: .semibold))
                    .foregroundStyle(media.microphoneOn ? FiniTheme.ink : Color.white)
                    .frame(width: 62, height: 62)
                    .background(media.microphoneOn ? FiniTheme.soft : FiniTheme.ink, in: Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(media.microphoneOn ? "Mute microphone" : "Unmute microphone")
            Button { Task { await session.hangUp() } } label: {
                Image(systemName: "phone.down.fill")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(width: 74, height: 74)
                    .background(Color(red: 1, green: 45 / 255, blue: 45 / 255), in: Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("End call")
            Button { media.setCamera(on: true) } label: {
                Image(systemName: "video.fill")
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundStyle(FiniTheme.ink)
                    .frame(width: 62, height: 62)
                    .background(FiniTheme.soft, in: Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Turn camera on")
        }
    }

    private func audioLine(_ line: TranscriptLine) -> some View {
        let speaker = firstName(line.speakerName ?? "Speaker")
        return HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text(speaker)
                .font(.system(size: 13, weight: .heavy))
                .foregroundStyle(.white)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .frame(minWidth: 52)
                .background(FiniTheme.blue, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            if let stamp = spokenTime(line.createdAt) {
                Text(stamp).font(.caption).foregroundStyle(FiniTheme.muted)
            }
            Text(line.text)
                .font(.subheadline)
                .foregroundStyle(Color(red: 51 / 255, green: 65 / 255, blue: 85 / 255))
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var videoCall: some View {
        ZStack {
            Color(red: 17 / 255, green: 24 / 255, blue: 39 / 255).ignoresSafeArea()
            VStack(spacing: 16) {
                VStack(spacing: 4) {
                    Text(session.status).font(.headline).foregroundStyle(.white)
                    Text(session.people.map(\.name).joined(separator: ", "))
                        .font(.subheadline)
                        .foregroundStyle(.white.opacity(0.75))
                        .multilineTextAlignment(.center)
                }
                .padding(.top, 12)
                videoStage
                if !session.banner.isEmpty {
                    Text(session.banner).font(.footnote).foregroundStyle(.white).padding(.horizontal)
                }
                videoControls
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 12)
        }
    }

    private var videoStage: some View {
        ZStack(alignment: .bottomTrailing) {
            let remotes = Array(media.remoteVideo)
            if remotes.isEmpty {
                VStack(spacing: 10) {
                    Image(systemName: "person.wave.2").font(.system(size: 42)).foregroundStyle(.white)
                    Text(session.people.first?.name ?? "Waiting")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(.white)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if remotes.count == 1, let track = remotes.first?.value {
                VideoScreen(track: track)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
            } else {
                HStack(spacing: 8) {
                    ForEach(remotes, id: \.key) { item in
                        VideoScreen(track: item.value)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                    }
                }
            }
            if let local = media.localVideo, media.cameraOn {
                VideoScreen(track: local)
                    .frame(width: 104, height: 146)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Color.white.opacity(0.85), lineWidth: 1))
                    .scaleEffect(x: -1, y: 1)
                    .padding(10)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
    }

    private var videoControls: some View {
        HStack(spacing: 18) {
            callButton(media.microphoneOn ? "mic.fill" : "mic.slash.fill", label: media.microphoneOn ? "Mute" : "Unmute") {
                media.setMicrophone(on: !media.microphoneOn)
            }
            callButton(media.cameraOn ? "video.fill" : "video.slash.fill", label: "Camera") {
                media.setCamera(on: !media.cameraOn)
            }
            callButton(session.momentFlagged ? "flag.fill" : "flag", label: "Flag", tint: session.momentFlagged ? .orange : .white) {
                Task { await session.flagMoment() }
            }
            callButton("person.badge.plus", label: "Interpreter") { inviting = true }
            callButton("phone.down.fill", label: "End", danger: true) { Task { await session.hangUp() } }
        }
    }

    private func callButton(_ system: String, label: String, danger: Bool = false, tint: Color = .white, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 6) {
                Image(systemName: system).font(.title3)
                    .frame(width: 52, height: 52)
                    .background(danger ? Color.red : Color.white.opacity(0.14), in: Circle())
                Text(label).font(.caption2)
            }
            .foregroundStyle(danger ? Color.white : tint)
        }
        .buttonStyle(.plain)
    }

    private var inviteSheet: some View {
        NavigationStack {
            List(interpreters) { profile in
                Button {
                    Task {
                        await session.invite(profile)
                        inviting = false
                    }
                } label: {
                    VStack(alignment: .leading) {
                        Text(profile.name).foregroundStyle(FiniTheme.ink)
                        Text(profile.headline).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Invite an interpreter")
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { inviting = false } } }
            .overlay { if interpreters.isEmpty { Text("No available interpreters.").foregroundStyle(.secondary) } }
            .task { interpreters = await session.availableInterpreters() }
        }
    }

    private var bookingSheet: some View {
        NavigationStack {
            BookSessionSheet(otherName: session.people.first?.name ?? "your interpreter")
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { booking = false } } }
        }
    }

    private func elapsedLabel(since start: Date, now: Date) -> String {
        let elapsed = max(0, Int(now.timeIntervalSince(start)))
        return String(format: "%02d:%02d", elapsed / 60, elapsed % 60)
    }

    private func firstName(_ name: String) -> String {
        let part = name.split(separator: " ").first.map(String.init) ?? name
        return part.isEmpty ? "Speaker" : part
    }

    private func spokenTime(_ raw: String?) -> String? {
        guard let raw, let date = CallView.parseClock(raw) else { return nil }
        return CallView.spokenClock.string(from: date)
    }

    private static let spokenClock: DateFormatter = {
        let formatter = DateFormatter()
        formatter.timeStyle = .medium
        formatter.dateStyle = .none
        return formatter
    }()

    private static func parseClock(_ raw: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: raw) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: raw)
    }
}

private struct BookSessionSheet: View {
    let otherName: String
    @State private var kind = "Audio"
    @State private var minutes = 60
    @State private var status = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Schedule a Session").font(.title2.weight(.bold)).foregroundStyle(FiniTheme.ink)
                Text(otherName).foregroundStyle(FiniTheme.blue).font(.headline)
                Picker("Session type", selection: $kind) {
                    Text("Audio").tag("Audio")
                    Text("Video").tag("Video")
                }
                .pickerStyle(.segmented)
                Text("Select a Duration").font(.subheadline.weight(.semibold)).foregroundStyle(FiniTheme.muted)
                HStack(spacing: 8) {
                    ForEach([30, 60, 90], id: \.self) { value in
                        Button("\(value) min") { minutes = value }
                            .buttonStyle(.plain)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(minutes == value ? Color.white : FiniTheme.ink)
                            .frame(maxWidth: .infinity, minHeight: 40)
                            .background(minutes == value ? FiniTheme.blue : FiniTheme.chip, in: Capsule())
                    }
                }
                Button("Schedule a Session") {
                    status = "\(kind) session held for \(minutes) min. Request an instant call when everyone is ready."
                }
                .buttonStyle(.plain)
                .font(.headline)
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, minHeight: 52)
                .background(FiniTheme.blue, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                if !status.isEmpty {
                    Text(status).font(.footnote).foregroundStyle(FiniTheme.muted)
                }
            }
            .padding(20)
        }
        .background(Color.white)
        .navigationTitle("Book Now")
        .navigationBarTitleDisplayMode(.inline)
    }
}

private struct VideoScreen: UIViewRepresentable {
    let track: RTCVideoTrack

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> RTCMTLVideoView {
        let view = RTCMTLVideoView(frame: .zero)
        view.videoContentMode = .scaleAspectFill
        track.add(view)
        context.coordinator.track = track
        return view
    }

    func updateUIView(_ view: RTCMTLVideoView, context: Context) {
        guard context.coordinator.track !== track else { return }
        context.coordinator.track?.remove(view)
        track.add(view)
        context.coordinator.track = track
    }

    static func dismantleUIView(_ view: RTCMTLVideoView, coordinator: Coordinator) {
        coordinator.track?.remove(view)
    }

    final class Coordinator { var track: RTCVideoTrack? }
}
