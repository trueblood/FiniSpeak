import SwiftUI
import WebRTC

struct CallView: View {
    @ObservedObject var session: CallSession
    @ObservedObject var media: CallMedia
    @State private var line = ""
    @State private var inviting = false
    @State private var interpreters: [Interpreter] = []

    init(session: CallSession) {
        self.session = session
        media = session.media
    }

    var body: some View {
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
                transcript
                let note = session.banner.isEmpty ? media.cameraMessage : session.banner
                if !note.isEmpty {
                    Text(note).font(.footnote).foregroundStyle(.white).padding(.horizontal)
                }
                controls
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 12)
        }
        .sheet(isPresented: $inviting) { inviteSheet }
    }

    private var videoStage: some View {
        ZStack(alignment: .bottomTrailing) {
            if media.remoteVideo.isEmpty {
                VStack(spacing: 10) {
                    Image(systemName: "person.wave.2").font(.system(size: 42)).foregroundStyle(.white)
                    Text(session.people.first?.name ?? "Waiting")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(.white)
                    Text(session.people.first?.state ?? "The other person will appear here when they join.")
                        .font(.footnote)
                        .foregroundStyle(.white.opacity(0.7))
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                GeometryReader { proxy in
                    let tracks = Array(media.remoteVideo)
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                        ForEach(tracks, id: \.key) { item in
                            VideoScreen(track: item.value)
                                .frame(height: tracks.count == 1 ? proxy.size.height : proxy.size.height / 2)
                                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                        }
                    }
                }
            }
            if let local = media.localVideo, media.cameraOn {
                VideoScreen(track: local)
                    .frame(width: 110, height: 150)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .padding(8)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 24, style: .continuous))
    }

    private var transcript: some View {
        VStack(alignment: .leading, spacing: 8) {
            Toggle(isOn: Binding(get: { session.consent }, set: { value in Task { await session.setConsent(value) } })) {
                Text("Save transcript").foregroundStyle(.white)
            }
            .tint(FiniTheme.blue)
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    if session.transcripts.isEmpty {
                        Text("Transcript lines appear here as they are saved.").font(.footnote).foregroundStyle(.white.opacity(0.7))
                    }
                    ForEach(session.transcripts) { line in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(line.speakerName ?? "Speaker").font(.caption.weight(.semibold)).foregroundStyle(.white.opacity(0.7))
                            Text(line.text).foregroundStyle(.white)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(height: 140)
            HStack {
                TextField("Add a transcript line", text: $line)
                    .textFieldStyle(.roundedBorder)
                Button("Add") {
                    let text = line
                    line = ""
                    Task { await session.addLine(text) }
                }
                .foregroundStyle(.white)
            }
        }
    }

    private var controls: some View {
        HStack(spacing: 18) {
            callButton(media.microphoneOn ? "mic.fill" : "mic.slash.fill", label: media.microphoneOn ? "Mute" : "Unmute") {
                media.setMicrophone(on: !media.microphoneOn)
            }
            callButton(media.cameraOn ? "video.fill" : "video.slash.fill", label: "Camera") {
                media.setCamera(on: !media.cameraOn)
            }
            callButton("person.badge.plus", label: "Interpreter") { inviting = true }
            callButton("phone.down.fill", label: "End", danger: true) { Task { await session.hangUp() } }
        }
    }

    private func callButton(_ system: String, label: String, danger: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 6) {
                Image(systemName: system).font(.title3)
                    .frame(width: 56, height: 56)
                    .background(danger ? Color.red : Color.white.opacity(0.14), in: Circle())
                Text(label).font(.caption2)
            }
            .foregroundStyle(.white)
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
