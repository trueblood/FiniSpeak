const AVATARS = [
    { id: "amara", name: "Amara", skin: "#8d5524", hair: "#24160f", accent: "#f5a65b", style: "bob" },
    { id: "jules", name: "Jules", skin: "#c68642", hair: "#3b2414", accent: "#7eb6ff", style: "short" },
    { id: "nova", name: "Nova", skin: "#efd0b4", hair: "#60a5fa", accent: "#38bdf8", style: "ai" },
    { id: "sol", name: "Sol", skin: "#f1c27d", hair: "#111827", accent: "#f59e0b", style: "curly" },
    { id: "mina", name: "Mina", skin: "#f3d5c0", hair: "#6d28d9", accent: "#c4b5fd", style: "long" },
    { id: "kai", name: "Kai", skin: "#d4a574", hair: "#0f172a", accent: "#34d399", style: "crop" }
];

const LANGUAGE_OPTIONS = [
    ["en", "English"], ["es", "Spanish"], ["fr", "French"], ["de", "German"], ["pt", "Portuguese"],
    ["it", "Italian"], ["zh", "Mandarin Chinese"], ["ja", "Japanese"], ["ko", "Korean"], ["ar", "Arabic"],
    ["hi", "Hindi"], ["ru", "Russian"], ["vi", "Vietnamese"], ["so", "Somali"]
];

export function createCallExperience(deps) {
    const state = {
        mediaMode: localStorage.getItem("finispeak.mediaMode") || "camera",
        avatarId: localStorage.getItem("finispeak.avatarId") || "amara",
        viewerLanguage: localStorage.getItem("finispeak.viewerLanguage") || "es",
        subtitleMode: localStorage.getItem("finispeak.subtitleMode") || "both",
        screenTrack: null,
        avatarTrack: null,
        avatarStream: null,
        analyser: null,
        audioContext: null,
        level: 0,
        speaking: false,
        interpreterSpeaking: false,
        partial: "",
        call: null,
        participants: [],
        rows: [],
        documentsOpen: false,
        activeDocumentId: null,
        documentDirty: false,
        summary: null,
        spoken: new Set(),
        translationRequests: new Set(),
        raf: 0,
        clock: 0,
        joinedAt: 0,
        reducedMotion: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    };

    const avatarById = (id) => AVATARS.find(avatar => avatar.id === id) || AVATARS[0];
    const languageName = (code) => LANGUAGE_OPTIONS.find(([value]) => value === code)?.[1] || deps.languageLabel?.(code) || code || "Unknown";

    function fillLanguageSelect(select, selected) {
        if (!select || select.dataset.ready === "true") {
            if (select && selected) select.value = selected;
            return;
        }
        select.innerHTML = "";
        for (const [value, label] of LANGUAGE_OPTIONS) {
            const option = document.createElement("option");
            option.value = value;
            option.textContent = label;
            select.appendChild(option);
        }
        select.dataset.ready = "true";
        select.value = selected || "en";
    }

    function bind() {
        fillLanguageSelect(deps.$("viewerLanguage"), state.viewerLanguage);
        fillLanguageSelect(deps.$("aiSourceLang"), "en");
        fillLanguageSelect(deps.$("aiTargetLang"), state.viewerLanguage);
        fillLanguageSelect(deps.$("documentSourceLang"), "en");
        fillLanguageSelect(deps.$("documentTargetLang"), state.viewerLanguage);
        deps.$("subtitleMode").value = state.subtitleMode;
        applySubtitleMode(state.subtitleMode);
        renderAvatarChoices(deps.$("avatarStudioGrid"), state.avatarId, (id) => chooseAvatar(id));
        renderAvatarChoices(deps.$("aiAvatarGrid"), "nova", (id) => { state.pendingAiAvatar = id; });
        state.pendingAiAvatar = "nova";
        loadVoices();
        window.speechSynthesis?.addEventListener?.("voiceschanged", loadVoices);

        deps.$("avatarButton").onclick = () => deps.openModal("avatarStudioModal");
        deps.$("closeAvatarStudio").onclick = () => deps.closeModal("avatarStudioModal");
        deps.$("useLiveCamera").onclick = () => useCamera();
        if (deps.$("closeAiInterpreter")) deps.$("closeAiInterpreter").onclick = () => deps.closeModal("aiInterpreterModal");
        if (deps.$("cancelAiInterpreter")) deps.$("cancelAiInterpreter").onclick = () => deps.closeModal("aiInterpreterModal");
        if (deps.$("confirmAiInterpreter")) deps.$("confirmAiInterpreter").onclick = confirmInterpreter;
        deps.$("inviteParticipantButton").onclick = () => deps.openModal("inviteParticipantModal");
        deps.$("closeInviteParticipant").onclick = () => deps.closeModal("inviteParticipantModal");
        deps.$("cancelInviteParticipant").onclick = () => deps.closeModal("inviteParticipantModal");
        deps.$("inviteParticipantForm").onsubmit = inviteParticipant;
        deps.$("documentsButton").onclick = () => state.documentsOpen ? closeDocuments() : openDocuments();
        deps.$("closeDocuments").onclick = closeDocuments;
        deps.$("subtitleButton").onclick = cycleSubtitles;
        deps.$("subtitleMode").onchange = () => applySubtitleMode(deps.$("subtitleMode").value);
        deps.$("viewerLanguage").onchange = () => {
            state.viewerLanguage = deps.$("viewerLanguage").value;
            localStorage.setItem("finispeak.viewerLanguage", state.viewerLanguage);
            state.translationRequests.clear();
            updateSubtitles(state.rows);
            deps.renderTranscript?.(state.rows);
        };
        deps.$("collapseTranscript").onclick = () => setTranscriptCollapsed(true);
        deps.$("expandTranscript").onclick = () => setTranscriptCollapsed(false);
        deps.$("screenShareButton").onclick = () => toggleScreenShare().catch(showCallError);
        deps.$("summarizeButton").onclick = summarize;
        deps.$("copySummary").onclick = copySummary;
        deps.$("saveSummary").onclick = saveSummary;
        deps.$("uploadDocument").onclick = () => deps.$("documentFile").click();
        deps.$("documentFile").onchange = uploadDocument;
        deps.$("translateDocument").onclick = translateDocument;
        deps.$("explainSelection").onclick = explainSelection;
        deps.$("documentPermission").onchange = () => scheduleDocumentSave();
        deps.$("documentTitle").oninput = () => scheduleDocumentSave();
        deps.$("documentOriginal").oninput = () => scheduleDocumentSave();
        deps.$("documentTranslated").oninput = () => scheduleDocumentSave();
        deps.$("collaboratorForm").onsubmit = inviteCollaborator;
        document.querySelectorAll("[data-call-pane]").forEach(button => {
            button.onclick = () => setPane(button.dataset.callPane);
        });
        window.addEventListener("resize", resizeCanvases);
        startLoop();
    }

    function onJoined(call) {
        state.joinedAt = Date.now();
        state.call = call;
        const name = deps.getProfile()?.displayName || "You";
        deps.$("localParticipantName").textContent = name;
        deps.$("localVideoName").textContent = name;
        if (state.mediaMode === "avatar") useAvatar(state.avatarId, false);
        else markCameraMode(true);
        startLoop();
    }

    function sync(call, participants) {
        state.call = call;
        state.participants = participants || [];
        const interpreter = call?.aiInterpreter;
        document.querySelector('.video-card[data-role="ai"]')?.remove();
        deps.$("translationIndicator").textContent = "Translation ready";
        if (interpreter) state.call = { ...call, aiInterpreter: null };
        applyParticipantPresence(participants || []);
        renderDocuments(call?.documents || []);
        if (!state.summary && call?.savedSummaries?.length) showSummary(call.savedSummaries[call.savedSummaries.length - 1], "Saved with this call.");
        updateClock(call);
    }

    function updateClock(call) {
        const started = Date.parse(call?.startedAt || "") || state.joinedAt || Date.now();
        const elapsed = Math.max(0, Date.now() - started);
        const minutes = String(Math.floor(elapsed / 60000)).padStart(2, "0");
        const seconds = String(Math.floor(elapsed / 1000) % 60).padStart(2, "0");
        deps.$("callDuration").textContent = `${minutes}:${seconds}`;
    }

    function updateSubtitles(rows) {
        state.rows = rows || [];
        const latest = new Map();
        for (const row of state.rows) if (row.speakerId) latest.set(row.speakerId, row);
        document.querySelectorAll("#callView .video-card[data-speaker]").forEach(card => {
            const subtitle = card.querySelector(".tile-subtitle");
            if (!subtitle) return;
            const row = latest.get(card.dataset.speaker);
            const partial = card.dataset.role === "local" ? state.partial : "";
            const text = partial || subtitleText(row);
            subtitle.hidden = !text;
            subtitle.textContent = text ? `${partial ? "You" : row?.speakerName || "Speaker"}: ${text}` : "";
        });
        const ai = document.querySelector('[data-role="ai"] .tile-subtitle');
        if (ai) {
            const row = [...state.rows].reverse().find(item => item.speakerId !== deps.getUser()?.uid) || state.rows.at(-1);
            const text = subtitleText(row);
            ai.hidden = !text;
            ai.textContent = text ? `AI: ${text}` : "";
        }
    }

    function subtitleText(row) {
        if (!row) return "";
        const translated = row.translations?.[state.viewerLanguage]?.text;
        if (translated) return translated;
        const source = String(row.language || "").toLowerCase();
        if (!source || source === state.viewerLanguage) return row.text || "";
        return "";
    }

    function onPartial(text) {
        state.partial = text || "";
        const partial = deps.$("partialTranscript");
        if (partial) {
            partial.textContent = state.partial ? `Partial · ${state.partial}` : "";
            partial.classList.toggle("hidden", !state.partial);
        }
        updateSubtitles(state.rows);
    }

    function viewerLanguage() { return state.viewerLanguage; }
    function outgoingVideoTrack() {
        if (state.screenTrack?.readyState === "live") return state.screenTrack;
        if (state.mediaMode === "avatar" && state.avatarTrack) return state.avatarTrack;
        return deps.getLocalStream()?.getVideoTracks?.()[0] || null;
    }

    function noteConnection(connectionState) {
        const label = connectionState === "connected" ? "Connected" : connectionState === "failed" ? "Reconnecting" : "Connecting";
        deps.$("callConnection").textContent = label;
        deps.$("localConnection").textContent = label;
    }

    function attachLocalStream(stream) {
        if (!stream) return;
        try {
            state.audioContext = state.audioContext || new (window.AudioContext || window.webkitAudioContext)();
            state.analyser = state.audioContext.createAnalyser();
            state.analyser.fftSize = 256;
            const source = state.audioContext.createMediaStreamSource(new MediaStream(stream.getAudioTracks()));
            source.connect(state.analyser);
        } catch (error) {
            console.warn("Call audio meter unavailable", error);
        }
    }

    async function postExperience(action, extra = {}) {
        const callId = deps.getCallId();
        if (!callId) throw new Error("Join a call before using this control.");
        return deps.apiFetch(`/api/calls/${encodeURIComponent(callId)}/experience`, {
            method: "POST",
            body: JSON.stringify({ action, ...extra })
        });
    }

    async function persistPresence(extra = {}) {
        const audio = deps.getLocalStream()?.getAudioTracks?.()[0];
        const camera = deps.getLocalStream()?.getVideoTracks?.()[0];
        await postExperience("set-media", {
            mediaMode: state.mediaMode,
            avatarId: state.avatarId,
            microphoneEnabled: audio ? audio.enabled : true,
            cameraEnabled: state.mediaMode === "camera" && camera ? camera.enabled : false,
            ...extra
        });
    }

    function markCameraMode(cameraOn) {
        const card = document.querySelector('.video-card[data-role="local"]');
        card?.classList.toggle("is-camera-on", cameraOn && state.mediaMode === "camera" && !state.screenTrack);
        card?.classList.toggle("is-avatar", state.mediaMode === "avatar" && !state.screenTrack);
        deps.$("localMediaLabel").textContent = state.screenTrack ? "Screen" : state.mediaMode === "avatar" ? "Avatar" : cameraOn ? "Camera" : "Camera off";
        deps.$("localAvatarCanvas").classList.toggle("is-hidden", state.mediaMode !== "avatar" || Boolean(state.screenTrack));
        deps.$("localVideo").classList.toggle("is-hidden", state.mediaMode === "avatar" && !state.screenTrack);
    }

    async function useCamera() {
        state.mediaMode = "camera";
        localStorage.setItem("finispeak.mediaMode", "camera");
        stopScreenShare(false);
        const stream = deps.getLocalStream();
        let track = stream?.getVideoTracks?.()[0];
        if (!track || track.readyState === "ended") {
            const fresh = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
            track = fresh.getVideoTracks()[0];
            stream?.addTrack(track);
        }
        track.enabled = true;
        deps.$("localVideo").srcObject = stream;
        deps.replaceOutgoingVideo(track);
        markCameraMode(true);
        deps.$("cameraButton").setAttribute("aria-pressed", "false");
        deps.$("cameraButton").querySelector(".tool-label").textContent = "Camera";
        deps.closeModal("avatarStudioModal");
        persistPresence().catch(showCallError);
    }

    async function chooseAvatar(avatarId) {
        state.avatarId = avatarId;
        localStorage.setItem("finispeak.avatarId", avatarId);
        await useAvatar(avatarId, true);
        deps.closeModal("avatarStudioModal");
    }

    async function useAvatar(avatarId, persist) {
        state.mediaMode = "avatar";
        state.avatarId = avatarId || state.avatarId;
        localStorage.setItem("finispeak.mediaMode", "avatar");
        stopScreenShare(false);
        const canvas = deps.$("localAvatarCanvas");
        if (!state.avatarStream) {
            state.avatarStream = canvas.captureStream(24);
            state.avatarTrack = state.avatarStream.getVideoTracks()[0];
        }
        const camera = deps.getLocalStream()?.getVideoTracks?.()[0];
        if (camera) camera.enabled = false;
        deps.replaceOutgoingVideo(state.avatarTrack);
        markCameraMode(false);
        deps.$("cameraButton").setAttribute("aria-pressed", "true");
        deps.$("cameraButton").querySelector(".tool-label").textContent = "Camera off";
        if (persist) persistPresence().catch(showCallError);
    }

    async function toggleScreenShare() {
        if (state.screenTrack) {
            stopScreenShare(true);
            return;
        }
        const display = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
        state.screenTrack = display.getVideoTracks()[0];
        state.screenTrack.onended = () => stopScreenShare(true);
        deps.$("localVideo").srcObject = display;
        deps.$("localVideo").classList.remove("is-hidden");
        deps.$("localAvatarCanvas").classList.add("is-hidden");
        deps.replaceOutgoingVideo(state.screenTrack);
        deps.$("screenShareButton").setAttribute("aria-pressed", "true");
        deps.$("screenShareButton").textContent = "Stop sharing";
        markCameraMode(false);
    }

    function stopScreenShare(restore) {
        if (state.screenTrack) {
            state.screenTrack.onended = null;
            state.screenTrack.stop();
            state.screenTrack = null;
        }
        deps.$("screenShareButton").setAttribute("aria-pressed", "false");
        deps.$("screenShareButton").textContent = "Share";
        if (!restore) return;
        if (state.mediaMode === "avatar") useAvatar(state.avatarId, false);
        else useCamera();
    }

    async function confirmInterpreter() {
        const status = deps.$("aiInterpreterStatus");
        status.textContent = "Adding the interpreter…";
        try {
            await postExperience("set-interpreter", {
                interpreter: {
                    active: true,
                    paused: false,
                    avatarId: state.pendingAiAvatar || "nova",
                    sourceLanguage: deps.$("aiSourceLang").value,
                    targetLanguage: deps.$("aiTargetLang").value,
                    voiceURI: deps.$("aiVoice").value
                }
            });
            status.textContent = "";
            deps.closeModal("aiInterpreterModal");
        } catch (error) {
            status.textContent = error.message;
        }
    }

    async function toggleInterpreterPause() {
        const paused = !state.call?.aiInterpreter?.paused;
        await postExperience("set-interpreter-paused", { paused });
    }

    async function inviteParticipant(event) {
        event.preventDefault();
        const status = deps.$("inviteStatus");
        status.textContent = "Sending invitation…";
        try {
            await postExperience("invite", { contact: deps.$("inviteEmail").value.trim() });
            status.textContent = "Invitation sent. They can join this call from their dashboard.";
            deps.$("inviteEmail").value = "";
        } catch (error) {
            status.textContent = error.message;
        }
    }

    function setPane(pane) {
        deps.$("callShell").dataset.pane = pane;
        document.querySelectorAll("[data-call-pane]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.callPane === pane)));
        if (pane === "documents") showDocuments();
        else if (pane !== "documents" && window.matchMedia("(max-width: 900px)").matches) {
            state.documentsOpen = false;
            deps.$("documentsPanel").hidden = true;
            deps.$("documentsButton").setAttribute("aria-pressed", "false");
        }
    }

    function showDocuments() {
        state.documentsOpen = true;
        deps.$("documentsPanel").hidden = false;
        deps.$("documentsButton").setAttribute("aria-pressed", "true");
        if (!state.activeDocumentId) createDocument();
    }

    function openDocuments() {
        showDocuments();
        if (window.matchMedia("(max-width: 900px)").matches) {
            deps.$("callShell").dataset.pane = "documents";
            document.querySelectorAll("[data-call-pane]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.callPane === "documents")));
        }
    }

    function closeDocuments() {
        state.documentsOpen = false;
        deps.$("documentsPanel").hidden = true;
        deps.$("documentsButton").setAttribute("aria-pressed", "false");
        if (deps.$("callShell").dataset.pane === "documents") {
            deps.$("callShell").dataset.pane = "video";
            document.querySelectorAll("[data-call-pane]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.callPane === "video")));
        }
    }

    function applySubtitleMode(mode) {
        state.subtitleMode = ["both", "floating", "transcript", "hidden"].includes(mode) ? mode : "both";
        localStorage.setItem("finispeak.subtitleMode", state.subtitleMode);
        const shell = deps.$("callShell");
        shell.classList.remove("subs-both", "subs-floating", "subs-transcript", "subs-hidden");
        shell.classList.add(`subs-${state.subtitleMode}`);
        deps.$("subtitleMode").value = state.subtitleMode;
        const visible = state.subtitleMode === "both" || state.subtitleMode === "floating";
        deps.$("subtitleButton").setAttribute("aria-pressed", String(visible));
    }

    function cycleSubtitles() {
        const order = ["both", "floating", "transcript", "hidden"];
        const next = order[(order.indexOf(state.subtitleMode) + 1) % order.length];
        applySubtitleMode(next);
    }

    function setTranscriptCollapsed(collapsed) {
        deps.$("callShell").classList.toggle("is-transcript-collapsed", collapsed);
        deps.$("collapseTranscript").setAttribute("aria-expanded", String(!collapsed));
        deps.$("expandTranscript").hidden = !collapsed;
    }

    function renderAvatarChoices(container, selected, onSelect) {
        if (!container) return;
        container.innerHTML = "";
        for (const avatar of AVATARS) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "avatar-choice";
            button.setAttribute("aria-pressed", String(avatar.id === selected));
            const canvas = document.createElement("canvas");
            canvas.width = 96;
            canvas.height = 96;
            drawAvatar(canvas, avatar, { mouth: 0.15, blink: 1, breath: 0, head: 0 });
            const name = document.createElement("span");
            name.textContent = avatar.name;
            button.append(canvas, name);
            button.onclick = () => {
                container.querySelectorAll(".avatar-choice").forEach(choice => choice.setAttribute("aria-pressed", "false"));
                button.setAttribute("aria-pressed", "true");
                onSelect(avatar.id);
            };
            container.appendChild(button);
        }
    }

    function loadVoices() {
        const select = deps.$("aiVoice");
        if (!select || !window.speechSynthesis) return;
        const voices = speechSynthesis.getVoices();
        const current = select.value;
        select.innerHTML = "";
        const fallback = document.createElement("option");
        fallback.value = "";
        fallback.textContent = "Default voice for the target language";
        select.appendChild(fallback);
        for (const voice of voices) {
            const option = document.createElement("option");
            option.value = voice.voiceURI;
            option.textContent = `${voice.name} (${voice.lang})`;
            option.dataset.lang = voice.lang;
            select.appendChild(option);
        }
        if (current) select.value = current;
    }

    function renderAiTile(interpreter) {
        let card = document.querySelector('.video-card[data-role="ai"]');
        if (!interpreter?.active) {
            card?.remove();
            layout();
            return;
        }
        if (!card) {
            card = document.createElement("article");
            card.className = "video-card is-avatar";
            card.dataset.role = "ai";
            card.dataset.speaker = "ai-interpreter";
            card.innerHTML = '<canvas class="avatar-canvas" aria-hidden="true"></canvas><span class="ai-badge">AI</span><span class="speaking-indicator" aria-hidden="true"></span><div class="video-label"><span class="video-role">AI</span><span class="video-label-separator" aria-hidden="true">·</span><span class="video-name"></span></div><p class="tile-subtitle" hidden></p>';
            deps.$("videoGrid").appendChild(card);
        }
        card.querySelector(".video-name").textContent = interpreter.displayName || "AI interpreter";
        card.classList.toggle("is-speaking", state.interpreterSpeaking && !interpreter.paused);
        layout();
    }

    function applyParticipantPresence(participants) {
        for (const participant of participants) {
            const card = document.querySelector(`[data-peer="${participant.id}"]`);
            if (!card) continue;
            card.classList.toggle("is-avatar", participant.mediaMode === "avatar");
            card.classList.toggle("is-camera-on", participant.mediaMode !== "avatar" && participant.cameraEnabled !== false);
            let muted = card.querySelector(".muted-pill");
            if (participant.microphoneEnabled === false) {
                if (!muted) {
                    muted = document.createElement("span");
                    muted.className = "connection-pill muted-pill";
                    muted.textContent = "Muted";
                    card.querySelector(".video-label")?.appendChild(muted);
                }
            } else muted?.remove();
        }
    }

    function layout() {
        const cards = [...document.querySelectorAll("#callView .video-card")];
        const stage = deps.$("videoGrid");
        const film = deps.$("videoFilmstrip");
        if (!stage || !film || !cards.length) return;
        const speaking = cards.find(card => card.classList.contains("is-speaking") && card.dataset.role !== "local");
        const active = speaking || cards.find(card => card.dataset.role !== "local") || cards[0];
        for (const card of cards) {
            card.classList.toggle("is-stage", card === active);
            (card === active ? stage : film).appendChild(card);
        }
        film.hidden = cards.length < 2;
    }

    function maybeSpeak() {}

    async function requestTranslations(callId, transcriptId, source) {
        const targets = new Set([state.viewerLanguage]);
        if (state.call?.aiInterpreter?.targetLanguage) targets.add(state.call.aiInterpreter.targetLanguage);
        for (const target of targets) {
            const key = `${transcriptId}:${target}`;
            if (state.translationRequests.has(key)) continue;
            state.translationRequests.add(key);
            try {
                await deps.apiFetch(`/api/calls/${encodeURIComponent(callId)}/transcripts/${encodeURIComponent(transcriptId)}/translation`, {
                    method: "POST",
                    body: JSON.stringify({ targetLanguage: target, sourceLanguage: source })
                });
            } catch (error) {
                state.translationRequests.delete(key);
                console.warn("Translation unavailable", error);
            }
        }
    }

    function ensureTranslation(row) {
        const callId = deps.getCallId();
        if (!callId || !row?.id || !row.language || String(row.language).toLowerCase() === state.viewerLanguage) return;
        if (row.translations?.[state.viewerLanguage]) return;
        requestTranslations(callId, row.id, row.language);
    }

    async function summarize() {
        const status = deps.$("summaryStatus");
        status.textContent = "Summarizing finalized lines…";
        try {
            const lines = state.rows.filter(row => row.isFinal !== false).map(row => ({ speaker: row.speakerName || "Participant", text: row.text || "" }));
            const result = await deps.apiFetch(`/api/calls/${encodeURIComponent(deps.getCallId())}/summary`, {
                method: "POST",
                body: JSON.stringify({ lines })
            });
            state.summary = result.summary;
            showSummary(result.summary, result.summary?.text ? "Summary ready. Save only if you want it kept with the call." : "There is not enough finalized conversation yet.");
        } catch (error) {
            status.textContent = error.message;
        }
    }

    function showSummary(summary, message) {
        state.summary = summary;
        deps.$("summaryText").textContent = summary?.text || "Summarize the finalized conversation to see key points. Nothing is stored until you confirm Save.";
        fillList(deps.$("summaryPoints"), summary?.points || []);
        fillList(deps.$("summaryActions"), summary?.actions || []);
        deps.$("summaryStatus").textContent = message || "";
    }

    function fillList(list, values) {
        list.innerHTML = "";
        for (const value of values) {
            const item = document.createElement("li");
            item.textContent = value;
            list.appendChild(item);
        }
    }

    async function copySummary() {
        const text = summaryPlainText();
        if (!text) {
            deps.$("summaryStatus").textContent = "Summarize the conversation before copying it.";
            return;
        }
        await navigator.clipboard.writeText(text);
        deps.$("summaryStatus").textContent = "Summary copied. It was not saved to the call.";
    }

    async function saveSummary() {
        if (!deps.$("summaryConsent").checked) {
            deps.$("summaryStatus").textContent = "Confirm the checkbox before saving this summary with the call.";
            return;
        }
        const lines = state.rows.filter(row => row.isFinal !== false).map(row => ({ speaker: row.speakerName || "Participant", text: row.text || "" }));
        try {
            await postExperience("save-summary", { consent: true, lines });
            deps.$("summaryStatus").textContent = "Summary saved with this call for participants.";
        } catch (error) {
            deps.$("summaryStatus").textContent = error.message;
        }
    }

    function summaryPlainText() {
        if (!state.summary?.text) return "";
        return [state.summary.text, "", "Key points:", ...(state.summary.points || []), "", "Action items:", ...(state.summary.actions || [])].join("\n");
    }

    function currentDocuments() {
        return Array.isArray(state.call?.documents) ? state.call.documents : [];
    }

    function createDocument(text = "") {
        const documentId = `doc-${crypto.randomUUID()}`;
        state.activeDocumentId = documentId;
        state.documentDirty = true;
        const documentRecord = {
            id: documentId,
            title: "Untitled document",
            originalText: text,
            translatedText: "",
            sourceLanguage: deps.$("documentSourceLang").value,
            targetLanguage: deps.$("documentTargetLang").value,
            permission: "edit",
            collaboratorIds: [],
            collaboratorEmails: []
        };
        deps.$("documentTitle").value = documentRecord.title;
        deps.$("documentOriginal").value = text;
        deps.$("documentTranslated").value = "";
        return postExperience("upsert-document", { document: documentRecord }).catch(showDocumentError);
    }

    async function uploadDocument(event) {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (!file) return;
        if (file.size > 8 * 1024 * 1024) {
            showDocumentError(new Error("Upload a document under 8 MB."));
            return;
        }
        const extension = file.name.split(".").pop()?.toLowerCase();
        let text = "";
        let title = file.name.replace(/\.[^.]+$/, "");
        try {
            if (["pdf", "doc", "docx"].includes(extension)) {
                const body = new FormData();
                body.append("file", file);
                const result = await deps.apiFetch(`/api/calls/${encodeURIComponent(deps.getCallId())}/documents/extract`, { method: "POST", body });
                text = result.text || "";
                title = result.title || title;
                if (result.truncated) deps.$("documentStatus").textContent = "Only the first part of that document was imported.";
            } else {
                text = await file.text();
            }
        } catch (error) {
            showDocumentError(error);
            return;
        }
        await createDocument(text);
        deps.$("documentTitle").value = title;
        scheduleDocumentSave();
    }

    function scheduleDocumentSave() {
        state.documentDirty = true;
        window.clearTimeout(state.saveTimer);
        state.saveTimer = window.setTimeout(saveActiveDocument, 700);
    }

    async function saveActiveDocument() {
        if (!state.activeDocumentId) return;
        const existing = currentDocuments().find(document => document.id === state.activeDocumentId) || {};
        const documentRecord = {
            ...existing,
            id: state.activeDocumentId,
            title: deps.$("documentTitle").value,
            originalText: deps.$("documentOriginal").value,
            translatedText: deps.$("documentTranslated").value,
            sourceLanguage: deps.$("documentSourceLang").value,
            targetLanguage: deps.$("documentTargetLang").value,
            permission: deps.$("documentPermission").value
        };
        try {
            await postExperience("upsert-document", { document: documentRecord });
            state.documentDirty = false;
            deps.$("documentStatus").textContent = "Document saved for everyone on the call.";
        } catch (error) {
            showDocumentError(error);
        }
    }

    function renderDocuments(documents) {
        const list = deps.$("documentList");
        list.innerHTML = "";
        for (const documentRecord of documents) {
            const item = document.createElement("li");
            const button = document.createElement("button");
            button.type = "button";
            button.className = "secondary";
            button.textContent = documentRecord.title || "Untitled document";
            button.onclick = () => selectDocument(documentRecord.id);
            item.appendChild(button);
            list.appendChild(item);
        }
        if (!state.documentDirty) {
            const active = documents.find(documentRecord => documentRecord.id === state.activeDocumentId) || documents[0];
            if (active) populateDocument(active);
        }
    }

    function selectDocument(id) {
        state.documentDirty = false;
        const documentRecord = currentDocuments().find(item => item.id === id);
        if (documentRecord) populateDocument(documentRecord);
    }

    function populateDocument(documentRecord) {
        state.activeDocumentId = documentRecord.id;
        if (document.activeElement === deps.$("documentOriginal") || document.activeElement === deps.$("documentTranslated") || document.activeElement === deps.$("documentTitle")) return;
        deps.$("documentTitle").value = documentRecord.title || "";
        deps.$("documentOriginal").value = documentRecord.originalText || "";
        deps.$("documentTranslated").value = documentRecord.translatedText || "";
        deps.$("documentSourceLang").value = documentRecord.sourceLanguage || "en";
        deps.$("documentTargetLang").value = documentRecord.targetLanguage || state.viewerLanguage;
        deps.$("documentPermission").value = documentRecord.permission || "edit";
        const collaborators = deps.$("collaboratorList");
        collaborators.innerHTML = "";
        for (const email of documentRecord.collaboratorEmails || []) {
            const item = document.createElement("li");
            item.textContent = email;
            collaborators.appendChild(item);
        }
        const versions = deps.$("documentVersions");
        versions.innerHTML = "";
        for (const version of documentRecord.versions || []) {
            const item = document.createElement("li");
            const button = document.createElement("button");
            button.type = "button";
            button.className = "secondary";
            button.textContent = `Restore ${new Date(version.savedAt).toLocaleString()}`;
            button.onclick = () => {
                deps.$("documentOriginal").value = version.originalText || "";
                deps.$("documentTranslated").value = version.translatedText || "";
                scheduleDocumentSave();
            };
            item.appendChild(button);
            versions.appendChild(item);
        }
        const editable = documentRecord.permission !== "view" || documentRecord.ownerId === deps.getUser()?.uid;
        deps.$("documentOriginal").disabled = !editable;
        deps.$("documentTranslated").disabled = !editable;
    }

    async function translateDocument() {
        if (!state.activeDocumentId) await createDocument(deps.$("documentOriginal").value);
        deps.$("documentStatus").textContent = "Translating document…";
        try {
            const result = await deps.apiFetch(`/api/calls/${encodeURIComponent(deps.getCallId())}/translate`, {
                method: "POST",
                body: JSON.stringify({
                    text: deps.$("documentOriginal").value,
                    source: deps.$("documentSourceLang").value,
                    target: deps.$("documentTargetLang").value
                })
            });
            deps.$("documentTranslated").value = result.text || "";
            deps.$("documentStatus").textContent = result.status === "translated" ? "Translation updated." : "No glossary or provider translation was available for that text.";
            scheduleDocumentSave();
        } catch (error) {
            showDocumentError(error);
        }
    }

    async function explainSelection() {
        const field = deps.$("documentOriginal");
        const selected = field.value.slice(field.selectionStart || 0, field.selectionEnd || 0).trim();
        if (!selected) {
            deps.$("termExplanation").textContent = "Select a word in the original document first.";
            return;
        }
        try {
            const result = await deps.apiFetch(`/api/calls/${encodeURIComponent(deps.getCallId())}/terminology`, {
                method: "POST",
                body: JSON.stringify({ term: selected, source: deps.$("documentSourceLang").value, target: deps.$("documentTargetLang").value })
            });
            deps.$("termExplanation").textContent = `${result.term}: ${result.translation}. ${result.definition}`;
        } catch (error) {
            deps.$("termExplanation").textContent = error.message;
        }
    }

    async function inviteCollaborator(event) {
        event.preventDefault();
        const email = deps.$("collaboratorEmail").value.trim();
        if (!state.activeDocumentId) await createDocument();
        try {
            await postExperience("invite", { email });
        } catch (error) {
            if (!/already/i.test(error.message)) {
                showDocumentError(error);
                return;
            }
        }
        const existing = currentDocuments().find(documentRecord => documentRecord.id === state.activeDocumentId) || {};
        const emails = [...new Set([...(existing.collaboratorEmails || []), email.toLowerCase()])];
        await postExperience("upsert-document", { document: { ...existing, id: state.activeDocumentId, collaboratorEmails: emails, title: deps.$("documentTitle").value, originalText: deps.$("documentOriginal").value, translatedText: deps.$("documentTranslated").value } });
        deps.$("collaboratorEmail").value = "";
        deps.$("documentStatus").textContent = "Collaborator invited. They can open the document after joining the call.";
    }

    function showCallError(error) { deps.setCallStatus?.(error.message); }
    function showDocumentError(error) { deps.$("documentStatus").textContent = error.message; }

    function resizeCanvases() {
        for (const canvas of document.querySelectorAll("#callView .video-card canvas")) {
            const rect = canvas.parentElement.getBoundingClientRect();
            const width = Math.max(1, Math.round(rect.width));
            const height = Math.max(1, Math.round(rect.height));
            if (canvas.width !== width || canvas.height !== height) {
                canvas.width = width;
                canvas.height = height;
            }
        }
    }

    function startLoop() {
        cancelAnimationFrame(state.raf);
        const samples = new Uint8Array(128);
        const tick = (time) => {
            state.raf = requestAnimationFrame(tick);
            if (state.analyser) {
                state.analyser.getByteTimeDomainData(samples);
                let energy = 0;
                for (const value of samples) {
                    const normalized = (value - 128) / 128;
                    energy += normalized * normalized;
                }
                state.level = Math.min(1, Math.sqrt(energy / samples.length) * 4);
            } else state.level = 0;
            const wasSpeaking = state.speaking;
            state.speaking = state.level > 0.08;
            const local = document.querySelector('.video-card[data-role="local"]');
            local?.classList.toggle("is-speaking", state.speaking);
            if (wasSpeaking !== state.speaking) layout();
            const pose = {
                mouth: state.speaking ? Math.min(1, state.level * 2.4) : 0.08,
                blink: state.reducedMotion ? 1 : (Math.sin(time / 1800) > 0.97 ? 0.1 : 1),
                breath: state.reducedMotion ? 0 : Math.sin(time / 900) * 2,
                head: state.reducedMotion ? 0 : Math.sin(time / 1400) * 0.08
            };
            if (state.mediaMode === "avatar" && !state.screenTrack) drawAvatar(deps.$("localAvatarCanvas"), avatarById(state.avatarId), pose);
            if (state.call) updateClock(state.call);
        };
        state.raf = requestAnimationFrame(tick);
    }

    function cleanup() {
        cancelAnimationFrame(state.raf);
        window.speechSynthesis?.cancel();
        stopScreenShare(false);
        state.avatarTrack?.stop();
        state.avatarStream = null;
        state.avatarTrack = null;
        state.audioContext?.close().catch(() => {});
        state.audioContext = null;
        state.analyser = null;
        state.partial = "";
        state.spoken.clear();
        state.translationRequests.clear();
        state.call = null;
        document.querySelector('.video-card[data-role="ai"]')?.remove();
        const local = document.querySelector('.video-card[data-role="local"]');
        if (local && deps.$("videoGrid")) deps.$("videoGrid").appendChild(local);
        deps.$("documentsPanel").hidden = true;
        deps.$("videoFilmstrip").hidden = true;
        setTranscriptCollapsed(false);
    }

    return {
        bind, onJoined, sync, updateSubtitles, onPartial, viewerLanguage, outgoingVideoTrack,
        noteConnection, attachLocalStream, requestTranslations, ensureTranslation, maybeSpeak, layout, cleanup, persistPresence,
        isAvatar: () => state.mediaMode === "avatar" && !state.screenTrack,
        activateCamera: useCamera,
        markCamera: markCameraMode
    };
}

function shadeColor(hex, amount) {
    const value = String(hex || "#888888").replace("#", "");
    const color = parseInt(value.length === 3 ? value.split("").map(part => part + part).join("") : value, 16);
    const channel = (shift) => Math.max(0, Math.min(255, ((color >> shift) & 255) + amount));
    return `rgb(${channel(16)}, ${channel(8)}, ${channel(0)})`;
}

function drawEye(context, x, y, blink) {
    context.save();
    context.translate(x, y);
    context.scale(1, Math.max(0.08, blink));
    context.fillStyle = "#f8fafc";
    context.beginPath();
    context.ellipse(0, 0, 9, 6.2, 0, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = "#1e293b";
    context.beginPath();
    context.arc(1, 0.5, 3.8, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = "#ffffff";
    context.beginPath();
    context.arc(-0.6, -1.2, 1.3, 0, Math.PI * 2);
    context.fill();
    context.restore();
}

function drawHair(context, avatar) {
    context.fillStyle = avatar.hair;
    context.beginPath();
    if (avatar.style === "long") {
        context.moveTo(-80, -70);
        context.quadraticCurveTo(-90, -112, 0, -112);
        context.quadraticCurveTo(90, -112, 80, -70);
        context.lineTo(76, 128);
        context.lineTo(54, 128);
        context.lineTo(60, 8);
        context.lineTo(-60, 8);
        context.lineTo(-54, 128);
        context.lineTo(-76, 128);
        context.closePath();
    } else if (avatar.style === "bob") {
        context.moveTo(-78, -8);
        context.quadraticCurveTo(-86, -106, 0, -106);
        context.quadraticCurveTo(86, -106, 78, -8);
        context.lineTo(72, 52);
        context.quadraticCurveTo(48, 28, 0, 24);
        context.quadraticCurveTo(-48, 28, -72, 52);
        context.closePath();
    } else if (avatar.style === "curly") {
        for (const [x, y, radius] of [[0, -78, 30], [-34, -70, 22], [34, -70, 22], [-72, -16, 22], [72, -16, 22], [-58, 24, 18], [58, 24, 18]]) {
            context.moveTo(x + radius, y);
            context.arc(x, y, radius, 0, Math.PI * 2);
        }
    } else if (avatar.style === "ai") {
        context.ellipse(0, -42, 78, 54, 0, Math.PI, Math.PI * 2);
    } else if (avatar.style === "crop" || avatar.style === "short") {
        context.ellipse(0, -58, 74, 46, 0, Math.PI, Math.PI * 2);
    } else {
        context.ellipse(0, -50, 80, 58, 0, Math.PI, Math.PI * 2);
    }
    context.fill();
    if (avatar.style === "ai") {
        context.fillStyle = avatar.accent;
        context.fillRect(-16, -96, 32, 6);
    }
}

function drawAvatar(canvas, avatar, pose) {
    if (!canvas || !avatar) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const width = canvas.width || 180;
    const height = canvas.height || 180;
    const mouth = Math.max(0, Math.min(1, pose?.mouth || 0));
    const blink = pose?.blink == null ? 1 : pose.blink;
    context.clearRect(0, 0, width, height);
    const backdrop = context.createLinearGradient(0, 0, 0, height);
    backdrop.addColorStop(0, "#314053");
    backdrop.addColorStop(1, "#121820");
    context.fillStyle = backdrop;
    context.fillRect(0, 0, width, height);
    const glow = context.createRadialGradient(width * 0.5, height * 0.36, width * 0.04, width * 0.5, height * 0.4, width * 0.46);
    glow.addColorStop(0, shadeColor(avatar.accent, 40).replace("rgb", "rgba").replace(")", ", 0.28)"));
    glow.addColorStop(1, "rgba(0,0,0,0)");
    context.fillStyle = glow;
    context.fillRect(0, 0, width, height);

    context.save();
    context.translate(width / 2 + (pose?.head || 0) * width * 0.02, height * 0.56 + (pose?.breath || 0));
    context.scale(Math.min(width / 300, height / 360), Math.min(width / 300, height / 360));

    context.fillStyle = shadeColor(avatar.accent, -24);
    context.beginPath();
    context.ellipse(0, 128, 138, 86, 0, Math.PI, 0, true);
    context.lineTo(138, 210);
    context.lineTo(-138, 210);
    context.closePath();
    context.fill();
    context.fillStyle = avatar.accent;
    context.beginPath();
    context.moveTo(-26, 72);
    context.quadraticCurveTo(0, 112, 26, 72);
    context.lineTo(16, 168);
    context.quadraticCurveTo(0, 146, -16, 168);
    context.closePath();
    context.fill();

    context.fillStyle = shadeColor(avatar.skin, -16);
    context.beginPath();
    if (context.roundRect) context.roundRect(-20, 48, 40, 42, 12);
    else context.rect(-20, 48, 40, 42);
    context.fill();
    drawHair(context, avatar);
    context.fillStyle = avatar.skin;
    context.beginPath();
    context.ellipse(-62, -4, 11, 16, 0, 0, Math.PI * 2);
    context.ellipse(62, -4, 11, 16, 0, 0, Math.PI * 2);
    context.fill();
    context.beginPath();
    context.ellipse(0, -10, 66, 78, 0, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = avatar.hair;
    context.beginPath();
    context.ellipse(0, -52, 70, avatar.style === "crop" ? 34 : 46, 0, Math.PI, Math.PI * 2);
    context.fill();

    context.strokeStyle = shadeColor(avatar.hair, 20);
    context.lineWidth = 3.2;
    context.lineCap = "round";
    context.beginPath();
    context.moveTo(-36, -30);
    context.quadraticCurveTo(-22, -38, -10, -30);
    context.moveTo(10, -30);
    context.quadraticCurveTo(22, -38, 36, -30);
    context.stroke();
    drawEye(context, -20, -6, blink);
    drawEye(context, 20, -6, blink);
    context.strokeStyle = shadeColor(avatar.skin, -35);
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(2, -2);
    context.quadraticCurveTo(8, 12, 1, 16);
    context.stroke();
    context.fillStyle = "#7a3038";
    context.beginPath();
    context.ellipse(0, 34, 16, 3.2 + mouth * 9, 0, 0, Math.PI * 2);
    context.fill();
    if (mouth > 0.2) {
        context.fillStyle = "#3c1519";
        context.beginPath();
        context.ellipse(0, 36, 9, mouth * 7, 0, 0, Math.PI * 2);
        context.fill();
    }
    context.restore();
}

function drawWave(canvas, level, time) {
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const width = canvas.width;
    const height = canvas.height;
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#10151d";
    context.fillRect(0, 0, width, height);
    const bars = 28;
    for (let index = 0; index < bars; index += 1) {
        const wave = Math.abs(Math.sin(time / 180 + index * 0.45));
        const bar = Math.max(4, (0.15 + level) * wave * (height - 12));
        context.fillStyle = index % 4 === 0 ? "#f5a65b" : "#7eb6ff";
        context.fillRect(8 + index * ((width - 16) / bars), (height - bar) / 2, 6, bar);
    }
}
