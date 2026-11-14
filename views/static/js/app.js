import { createCallExperience } from "./call-experience.js?v=20261107-video-phone";
import { createCameraRelay } from "./camera-relay.js?v=20261018-membership-refresh";
import { applyMeshSignal, attachMeshHandlers, isOfferer, liveReceiver, normalizeIceConfiguration, resendLocalOffer, sendOffer, shouldForceRelay, shouldSendOffer } from "./webrtc-mesh.js?v=20261018-turn-failover";

const $ = (id) => document.getElementById(id);
let callExperience;
const views = ["heroView", "authView", "dashboardView", "profileView", "callView"];
const show = (id) => {
    views.forEach(v => $(v)?.classList.toggle("hidden", v !== id));
    document.body.classList.toggle("dashboard-mode", id === "dashboardView");
    document.body.classList.toggle("profile-mode", id === "profileView");
    document.body.classList.toggle("in-call", id === "callView");
    document.body.classList.toggle("landing-mode", id === "heroView" || id === "authView");
    if (id === "heroView") document.querySelector(".landing-phone-scroll")?.scrollTo({ top: 0 });
    updateReturnToCall();
};
let currentUser, currentProfile, currentInterpreterProfile, signupMode = false;
let authActionToken = null;
let openDialAfterSignIn = false;
let localStream = null, activeCallId = null, callUnsubs = [], peerConnections = new Map(), peerProfiles = new Map(), peerDebug = new Map(), peerJobs = new Map(), rosterParticipants = [], rosterTranscripts = [];
let cameraRelay = null, cameraRelayOpen = false, cameraRestart = null, lastCameraRestart = 0, suppressCameraRestart = false;
let signalingSocket = null, signalingReady = null, pendingIceCandidates = new Map();
let pendingSignals = new Map(), signalingCursor = 0;
let callMembershipKey = "";
let captionBroadcastTimer = null, pendingCaptionText = "", lastCaptionText = "";
let rtcConfiguration = normalizeIceConfiguration(null);
let transcriptionSocket = null, transcriptionAudioContext = null, transcriptionSource = null, transcriptionNode = null, transcriptionGain = null, transcriptionCaptureRate = 16000, currentCallRole = null;
let selectedProcessingMode = "streaming", processingModesEnabled = false, transcriptionGeneration = Date.now();
let transcriptionSwitching = false, transcriptionBufferedAudio = [], transcriptionBufferedBytes = 0, transcriptionStopResolver = null, browserSpeechRecognition = null;
let dashboardUnsubs = [], pendingIncomingCall = null, historyCalls = new Map();
let directoryProfiles = [], activeDirectoryProfile = null, selectedInterpreterProfile = null;
let directoryMap = null, directoryMarkerLayer = null, directoryUserMarker = null;
let directoryOrigin = null, directoryView = "list", directoryMarkers = new Map(), filteredDirectoryProfiles = [];
let featuredProfilesData = [];
let callAttemptSequence = 0;
let routedLanguageCalls = new Set();
let pendingCredentialRemovalPaths = new Set();
let currentInterpreterWizardStep = 0;
let languageConfirmationPending = false;
let confirmedDetectedLanguage = null;
let activeTranslatorConnected = false;
let interpreterMatchesByLanguage = new Map();
let invitedTranslatorId = null;
let invitingTranslatorId = null;
let requestMatchProfiles = [];
let requestMatchView = "list";
let requestMatchMap = null;
let requestMatchMarkerLayer = null;
let detectedCallLanguages = new Map();
let selectedRequestLanguages = new Set();
let activeModal = null, modalReturnFocus = null;
let reviewCall = null;
let transcriptConsentGranted = false;
let historyTranscriptCall = null;
let lastCallRecord = null;
let activeCallRecord = null;
const interpreterProfileCache = new Map();
const isInterpreterRole = role => role === "translator" || role === "translator_applicant";
const taxonomy = { languages: [], dialects: [], specialties: [] };
const selectedTags = { languages: [], dialects: [], specialties: [] };
const taxonomySuggestionIndex = { languages: -1, dialects: -1, specialties: -1 };
const taxonomyUI = {
    languages: { input: "interpreterLanguages", tags: "interpreterLanguagesTags", options: "languagesOptions" },
    dialects: { input: "interpreterDialects", tags: "interpreterDialectsTags", options: "dialectsOptions" },
    specialties: { input: "interpreterSpecialties", tags: "interpreterSpecialtiesTags", options: "specialtiesOptions" }
};
const taxonomyCollections = {
    languages: "reference_languages",
    dialects: "reference_dialects",
    specialties: "reference_specialties"
};
const defaultTaxonomy = {
    languages: ["English", "Spanish", "French", "German", "Italian", "Portuguese", "Mandarin Chinese", "Cantonese", "Arabic", "Hindi", "Bengali", "Urdu", "Punjabi", "Russian", "Ukrainian", "Japanese", "Korean", "Vietnamese", "Tagalog", "Haitian Creole", "American Sign Language"],
    dialects: ["Mexican Spanish", "Caribbean Spanish", "Castilian Spanish", "Latin American Spanish", "Brazilian Portuguese", "European Portuguese", "Modern Standard Arabic", "Egyptian Arabic", "Levantine Arabic", "Gulf Arabic", "Mandarin", "Cantonese"],
    specialties: ["Medical", "Education", "Legal", "Business", "Financial", "Government", "Social Services", "Mental Health", "Immigration", "Community", "Technical", "Conference"]
};
const detectedLanguageNames = {
    ar: "Arabic", bn: "Bengali", de: "German", en: "English", es: "Spanish", fr: "French",
    hi: "Hindi", it: "Italian", ja: "Japanese", ko: "Korean", pt: "Portuguese", ru: "Russian",
    so: "Somali", tl: "Tagalog", uk: "Ukrainian", ur: "Urdu", vi: "Vietnamese", zh: "Mandarin Chinese"
};
const phoneCountries = [
    ["US", "United States", "+1"], ["CA", "Canada", "+1"], ["DO", "Dominican Republic", "+1"], ["JM", "Jamaica", "+1"],
    ["MX", "Mexico", "+52"], ["BR", "Brazil", "+55"], ["AR", "Argentina", "+54"], ["CO", "Colombia", "+57"], ["HT", "Haiti", "+509"],
    ["GB", "United Kingdom", "+44"], ["IE", "Ireland", "+353"], ["FR", "France", "+33"], ["ES", "Spain", "+34"],
    ["PT", "Portugal", "+351"], ["DE", "Germany", "+49"], ["IT", "Italy", "+39"], ["NL", "Netherlands", "+31"],
    ["BE", "Belgium", "+32"], ["CH", "Switzerland", "+41"], ["AT", "Austria", "+43"], ["SE", "Sweden", "+46"],
    ["NO", "Norway", "+47"], ["DK", "Denmark", "+45"], ["PL", "Poland", "+48"], ["UA", "Ukraine", "+380"],
    ["RU", "Russia", "+7"], ["TR", "Türkiye", "+90"], ["RO", "Romania", "+40"], ["GR", "Greece", "+30"],
    ["MA", "Morocco", "+212"], ["DZ", "Algeria", "+213"], ["EG", "Egypt", "+20"], ["NG", "Nigeria", "+234"],
    ["GH", "Ghana", "+233"], ["KE", "Kenya", "+254"], ["ET", "Ethiopia", "+251"], ["SO", "Somalia", "+252"],
    ["ZA", "South Africa", "+27"], ["SA", "Saudi Arabia", "+966"], ["AE", "United Arab Emirates", "+971"],
    ["QA", "Qatar", "+974"], ["KW", "Kuwait", "+965"], ["OM", "Oman", "+968"], ["IL", "Israel", "+972"],
    ["JO", "Jordan", "+962"], ["LB", "Lebanon", "+961"], ["IQ", "Iraq", "+964"], ["IR", "Iran", "+98"],
    ["IN", "India", "+91"], ["PK", "Pakistan", "+92"], ["BD", "Bangladesh", "+880"], ["NP", "Nepal", "+977"],
    ["LK", "Sri Lanka", "+94"], ["CN", "China", "+86"], ["HK", "Hong Kong", "+852"], ["TW", "Taiwan", "+886"],
    ["JP", "Japan", "+81"], ["KR", "South Korea", "+82"], ["VN", "Vietnam", "+84"], ["PH", "Philippines", "+63"],
    ["TH", "Thailand", "+66"], ["MY", "Malaysia", "+60"], ["SG", "Singapore", "+65"], ["ID", "Indonesia", "+62"],
    ["AU", "Australia", "+61"], ["NZ", "New Zealand", "+64"]
];
const profilePhotoTypes = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp"
};

function callLog(attemptId, stage, details = {}) {
    console.info(`[FiniSpeak call][${attemptId}] ${stage}`, details);
}

function callErrorDetails(error, stage) {
    return {
        stage,
        name: error?.name || "Error",
        code: error?.code || null,
        message: error?.message || String(error),
        online: navigator.onLine,
        secureContext: window.isSecureContext
    };
}

async function boot() {
    initializePhoneFields();
    bindUI();
    loadFeaturedProfiles();
    const actionPath = location.pathname === "/verify-email" || location.pathname === "/reset-password";
    authActionToken = new URLSearchParams(location.search).get("token");
    if (location.pathname === "/verify-email" && authActionToken) {
        show("authView");
        const response = await fetch("/api/auth/verify-email", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: authActionToken }) });
        const payload = await response.json().catch(() => ({}));
        $("authStatus").textContent = payload.message || payload.error || "Email verification failed.";
        history.replaceState({}, "", "/"); authActionToken = null;
    } else if (location.pathname === "/reset-password" && authActionToken) {
        show("authView"); $("authTitle").textContent = "Set a new password"; $("authSubmit").textContent = "Update password";
        $("emailField").classList.add("hidden"); $("email").required = false; $("authToggle").classList.add("hidden");
    }
    try {
        const response = await fetch("/api/auth/session", { credentials: "same-origin" });
        const payload = await response.json().catch(() => ({}));
        if (response.ok) await handleAuthState(payload.user);
        else if (!actionPath) await handleAuthState(null);
    } catch (error) {
        $("status").textContent = `Account service unavailable: ${error.message}`;
        await handleAuthState(null);
    }
}

function replaceOutgoingVideo(track) {
    if (!track) return;
    for (const pc of peerConnections.values()) {
        const sender = senderFor(pc, "video") || pc.addTransceiver("video", { direction: "sendrecv" }).sender;
        sender.replaceTrack(track).catch(console.error);
    }
}

function bindUI() {
    callExperience = createCallExperience({
        $,
        apiFetch: (path, options) => apiFetch(path, options),
        languageLabel: detectedLanguageLabel,
        replaceOutgoingVideo,
        getLocalStream: () => localStream,
        getCallId: () => activeCallId,
        getUser: () => currentUser,
        getProfile: () => currentProfile,
        openModal,
        closeModal,
        setCallStatus: (text) => { if ($("callStatus")) $("callStatus").textContent = text; },
        renderTranscript: (rows) => renderTranscript(rows),
        replayCallMedia,
        onCallSynced: (call) => {
            activeCallRecord = call;
            syncTranscriptConsent(call);
            renderKeyMoments(call);
            renderSessionInterpreter(call);
        }
    });
    callExperience.bind();
    watchCameraHealth();
    const workflowTabs = [...document.querySelectorAll(".workflow-tab")];
    workflowTabs.forEach((tab, index) => {
        tab.addEventListener("click", () => activateWorkflowTab(tab));
        tab.addEventListener("keydown", (event) => {
            if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
            event.preventDefault();
            let nextIndex = event.key === "Home" ? 0 : event.key === "End" ? workflowTabs.length - 1 : index + (event.key === "ArrowRight" ? 1 : -1);
            nextIndex = (nextIndex + workflowTabs.length) % workflowTabs.length;
            activateWorkflowTab(workflowTabs[nextIndex]);
            workflowTabs[nextIndex].focus();
        });
    });
    $("startCall").onclick = openDirectCall;
    $("landingCta").onclick = () => openAuth(true, "customer");
    $("landingLogin").onclick = () => $("authNav").click();
    $("landingSearch").onclick = () => $("browseNav").click();
    $("landingLesson").onclick = () => {
        if (!currentUser) {
            openAuth(true, "customer");
            $("authStatus").textContent = "Create an account to book a language lesson.";
            return;
        }
        show("dashboardView");
        openDashboardPanel("lesson");
    };
    document.querySelectorAll("[data-landing-category]").forEach(button => {
        button.onclick = () => {
            const name = button.dataset.landingCategory;
            setConceptCategory(name);
            if (currentUser) {
                openConceptCategory(name);
                return;
            }
            if ($("featuredSearch")) {
                $("featuredSearch").value = name === "Personal" ? "" : name;
                filterFeaturedProfiles();
            }
            $("featuredProfiles")?.scrollIntoView({ behavior: "smooth", block: "start" });
        };
    });
    $("translatorSignup").onclick = () => openAuth(true, "translator");
    $("homeNav").onclick = () => show("heroView");
    $("browseNav").onclick = openInterpreterDirectory;
    $("browseHero").onclick = openInterpreterDirectory;
    $("authNav").onclick = async () => currentUser ? localSignOut() : openAuth(false, "customer");
    $("authToggle").onclick = () => setAuthMode(!signupMode);
    $("forgotPassword").onclick = requestPasswordReset;
    $("authForm").onsubmit = submitAuth;
    $("callForm").onsubmit = createCall;
    document.querySelectorAll("[data-dial]").forEach(button => {
        button.onclick = () => appendDialDigit(button.dataset.dial);
    });
    $("dialBackspace").onclick = backspaceDialDigit;
    $("receiverPhone").addEventListener("input", () => clearDialFriendSelection());
    $("receiverPhoneCountry").addEventListener("change", () => setDialNationalDigits(dialNationalDigits()));
    $("dialManageFriends").onclick = () => openDashboardPanel("friends");
    $("copyCallId").onclick = async () => {
        if (!activeCallId) return;
        await navigator.clipboard.writeText(activeCallId);
        $("copyCallId").textContent = "Copied";
        window.setTimeout(() => { if ($("copyCallId")) $("copyCallId").textContent = "Copy ID"; }, 1400);
    };
    $("muteButton").onclick = toggleMute;
    $("cameraButton").onclick = toggleCamera;
    $("audioMuteButton").onclick = toggleMute;
    $("audioVideoButton").onclick = toggleCamera;
    $("audioHangupButton").onclick = endCall;
    $("audioBookNow").onclick = bookFromAudioCall;
    $("audioFlagMoment").onclick = flagKeyMoment;
    $("conceptFlagMoment").onchange = () => {
        if ($("conceptFlagMoment").dataset.syncing === "true") return;
        if ($("conceptFlagMoment").checked) flagKeyMoment();
        else resolveLatestKeyMoment();
    };
    $("transcriptConsent").onchange = () => setTranscriptConsent($("transcriptConsent").checked);
    $("deleteTranscript").onclick = () => deleteSavedTranscript(activeCallId);
    $("deleteHistoryTranscript").onclick = () => deleteSavedTranscript(historyTranscriptCall?.id);
    $("audioCallNote").oninput = () => {
        const notes = $("callNotes");
        if (!notes) return;
        notes.value = $("audioCallNote").value;
        notes.dispatchEvent(new Event("input"));
    };
    $("returnToCall").onclick = () => { if (activeCallId) show("callView"); };
    document.querySelectorAll("[data-audio-category]").forEach(button => {
        button.onclick = () => setConceptCategory(button.dataset.audioCategory);
    });
    $("callView")?.addEventListener("pointerdown", playRemoteMedia, { passive: true });
    document.querySelectorAll("[data-processing-mode]").forEach(button => button.onclick = () => selectProcessingMode(button.dataset.processingMode));
    $("toggleCallProcessingModes").onclick = (event) => {
        event.stopPropagation();
        setCallProcessingModesOpen($("toggleCallProcessingModes").closest(".call-nav-modes").classList.contains("is-collapsed"));
    };
    document.addEventListener("click", (event) => {
        const modes = document.querySelector(".call-nav-modes");
        if (!modes || modes.classList.contains("is-collapsed") || modes.contains(event.target)) return;
        setCallProcessingModesOpen(false);
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") setCallProcessingModesOpen(false);
    });
    $("requestTranslatorButton").onclick = openTranslatorRequest;
    $("closeTranslatorRequestModal").onclick = () => closeModal("translatorRequestModal");
    $("cancelTranslatorRequest").onclick = () => closeModal("translatorRequestModal");
    $("translatorRequestForm").onsubmit = requestTranslator;
    $("requestMatchList").onclick = () => setRequestMatchView("list");
    $("requestMatchMapButton").onclick = () => setRequestMatchView("map");
    $("requestMatchSplit").onclick = () => setRequestMatchView("split");
    $("requestMatchMode").onchange = () => renderRequestMatchCards();
    $("translatorLanguageSearch").oninput = renderTranslatorLanguageOptions;
    $("confirmDetectedLanguage").onclick = confirmDetectedLanguage;
    $("endCallButton").onclick = endCall;
    $("acceptIncomingCall").onclick = acceptIncomingCall;
    $("declineIncomingCall").onclick = declineIncomingCall;
    $("closeReviewModal").onclick = () => closeModal("reviewModal");
    $("reviewForm").onsubmit = submitInterpreterReview;
    document.addEventListener("keydown", handleModalKeyboard);
    document.querySelectorAll("[data-app-tab]").forEach(button => button.addEventListener("click", () => openAppTab(button.dataset.appTab)));
    $("conceptHomeButton").onclick = goToAppHome;
    $("landingHomeButton").onclick = goToAppHome;
    $("profileHomeButton").onclick = goToAppHome;
    $("careersBrowseBusiness").onclick = () => {
        setConceptCategory("Business");
        openDashboardPanel("directory");
        if ($("directorySearch")) $("directorySearch").value = "Business";
        filterInterpreterDirectory();
    };
    document.querySelectorAll("[data-dashboard-panel]").forEach(button => button.addEventListener("click", () => openDashboardPanel(button.dataset.dashboardPanel)));
    document.querySelectorAll("[data-open-panel]").forEach(button => button.addEventListener("click", () => openDashboardPanel(button.dataset.openPanel)));
    $("profileForm").onsubmit = saveProfile;
    $("interpreterProfileForm").onsubmit = (e) => saveInterpreterProfile(e, false);
    $("saveInterpreterDraft").onclick = (e) => saveInterpreterProfile(e, true);
    $("submitInterpreterVerification").onclick = (e) => saveInterpreterProfile(e, false, true);
    $("interpreterWizardBack").onclick = () => showInterpreterWizardStep(currentInterpreterWizardStep - 1);
    $("interpreterWizardNext").onclick = advanceInterpreterWizard;
    document.querySelectorAll("[data-wizard-step]").forEach(button => {
        button.onclick = () => showInterpreterWizardStep(Number(button.dataset.wizardStep));
    });
    $("interpreterPhoto").onchange = previewInterpreterPhoto;
    $("interpreterCredentialFiles").onchange = () => updateInterpreterCompletion();
    $("interpreterProfileForm").addEventListener("input", () => updateInterpreterCompletion());
    Object.keys(taxonomyUI).forEach(kind => {
        const input = $(taxonomyUI[kind].input);
        input.addEventListener("keydown", async (event) => {
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                moveTaxonomySuggestion(kind, event.key === "ArrowDown" ? 1 : -1);
                return;
            }
            if (event.key === "Escape") {
                closeTaxonomySuggestions(kind);
                return;
            }
            if (event.key === "Enter" || event.key === ",") {
                event.preventDefault();
                const suggestions = [...$(taxonomyUI[kind].options).querySelectorAll(".tag-suggestion")];
                const active = suggestions[taxonomySuggestionIndex[kind]];
                if (active) input.value = active.dataset.value;
                await addTagFromInput(kind);
            }
        });
        input.addEventListener("input", () => renderTaxonomyOptions(kind, true));
        input.addEventListener("focus", () => renderTaxonomyOptions(kind, true));
        input.addEventListener("blur", () => window.setTimeout(() => closeTaxonomySuggestions(kind), 120));
    });
    document.querySelectorAll("[data-add-tag]").forEach(button => button.addEventListener("click", () => addTagFromInput(button.dataset.addTag)));
    $("dashboardAvailableNow").onchange = updateDashboardAvailability;
    $("settingsSignOut").onclick = async () => localSignOut();
    $("refreshAdmin").onclick = loadAdminDashboard;
    $("refreshFriends").onclick = loadFriends;
    $("friendForm").onsubmit = addFriend;
    $("refreshMessages").onclick = () => loadConversations({ announce: true });
    $("directMessageForm").onsubmit = startDirectMessage;
    $("groupMessageForm").onsubmit = createGroupMessage;
    $("messageComposeForm").onsubmit = sendConversationMessage;
    $("messageBody").addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            $("messageComposeForm").requestSubmit();
        }
    });
    $("messageBackToList").onclick = showMessageList;
    $("groupAddMemberButton").onclick = addGroupMember;
    $("groupLeaveButton").onclick = leaveGroup;
    $("organizationForm").onsubmit = createOrganization;
    $("directorySearch").addEventListener("input", filterInterpreterDirectory);
    $("directoryRating").addEventListener("change", refreshInterpreterDirectory);
    $("directorySort").addEventListener("change", filterInterpreterDirectory);
    $("directoryAvailable").addEventListener("change", refreshInterpreterDirectory);
    ["directoryLanguage", "directoryDialect", "directorySpecialty", "directoryMode", "directoryRadius", "directoryVerified"].forEach(id => $(id).addEventListener("change", refreshInterpreterDirectory));
    $("useMyLocation").onclick = useDirectoryLocation;
    $("manualLocationForm").onsubmit = useManualDirectoryLocation;
    $("directoryListView").onclick = () => setDirectoryView("list");
    $("directoryMapView").onclick = () => setDirectoryView("map");
    $("directorySplitView").onclick = () => setDirectoryView("split");
    $("showAllMapped").onclick = showAllMappedTranslators;
    $("searchMapArea").onclick = searchCurrentMapArea;
    $("featuredSearch").addEventListener("input", filterFeaturedProfiles);
    $("featuredLanguage").addEventListener("change", filterFeaturedProfiles);
    $("featuredSpecialty").addEventListener("change", filterFeaturedProfiles);
    $("featuredAvailable").addEventListener("change", filterFeaturedProfiles);
    $("clearFeaturedFilters").onclick = clearFeaturedFilters;
    $("backToDirectory").onclick = closePublicProfile;
    $("profileSearchButton").onclick = () => {
        if (!currentUser) {
            show("heroView");
            loadFeaturedProfiles();
            window.requestAnimationFrame(() => $("featuredProfiles")?.scrollIntoView({ behavior: "smooth", block: "start" }));
            return;
        }
        show("dashboardView");
        openDashboardPanel("directory");
        window.setTimeout(() => $("directorySearch")?.focus(), 50);
    };
    $("dashboardBackButton").onclick = goDashboardBack;
    $("authBack").onclick = () => {
        openDialAfterSignIn = false;
        show("heroView");
    };
    $("clearSelectedInterpreter").onclick = clearSelectedInterpreter;
    $("openDirectCall").onclick = openDirectCall;
    document.querySelectorAll("[data-discovery-category]").forEach(button => {
        button.onclick = () => openConceptCategory(button.dataset.discoveryCategory);
    });
    document.querySelectorAll("[data-concept-category]").forEach(button => {
        button.onclick = () => openConceptCategory(button.dataset.conceptCategory);
    });
    $("conceptMenuButton").onclick = () => {
        const open = document.body.classList.toggle("nav-open");
        $("conceptMenuButton").setAttribute("aria-expanded", String(open));
    };
    $("conceptSearchButton").onclick = () => {
        show("dashboardView");
        openDashboardPanel("directory");
        window.setTimeout(() => $("directorySearch")?.focus(), 50);
    };
    document.querySelectorAll("[data-concept-chip]").forEach(button => {
        button.onclick = () => {
            const active = !button.classList.contains("active");
            document.querySelectorAll("[data-concept-chip]").forEach(chip => chip.classList.toggle("active", active && chip === button));
            $("directorySearch").value = active ? button.dataset.conceptChip : "";
            filterInterpreterDirectory();
        };
    });
    $("conceptViewProfile").onclick = () => {
        const profile = directoryProfiles.find(item => item.id === $("conceptMapSheet")?.dataset.profileId) || filteredDirectoryProfiles[0];
        if (profile) openPublicProfile(profile);
    };
    bindConceptScreens();
    $("profileStartCall").onclick = () => {
        if (!currentUser) {
            selectInterpreterForCall(activeDirectoryProfile);
            openAuth(false, "customer");
            $("authStatus").textContent = "Log in when you are ready to start a call with an interpreter.";
            return;
        }
        selectInterpreterForCall(activeDirectoryProfile);
        showCallDialPad();
    };
    $("profileChatTranslator").onclick = startDirectTranslatorChat;
}

function setTranslatorDiscoveryVisible(visible) {
    $("openFindTranslator")?.classList.toggle("hidden", !visible);
}

function setLanguageLessonAction(hosting) {
    const label = hosting ? "Host a Language Session" : "Book a Language Lesson";
    if ($("openLanguageLessonLabel")) $("openLanguageLessonLabel").textContent = label;
    if ($("lessonTitle")) $("lessonTitle").textContent = label;
}

function showCallDialPad() {
    show("dashboardView");
    openDashboardPanel("dial");
    $("dashboardDial").scrollTop = 0;
    $("callPromptTitle").focus({ preventScroll: true });
}

function openDirectCall() {
    if (!currentUser) {
        openAuth(false, "customer");
        openDialAfterSignIn = true;
        $("authStatus").textContent = "Sign in to call another FiniSpeak user.";
        return;
    }
    showCallDialPad();
}

function openModal(id) {
    const modal = $(id);
    if (!modal) return;
    modalReturnFocus = document.activeElement;
    activeModal = modal;
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    $("mainContent")?.setAttribute("inert", "");
    document.querySelector(".site-header")?.setAttribute("inert", "");
    const target = modal.querySelector("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])");
    window.requestAnimationFrame(() => target?.focus());
}

function closeModal(id) {
    const modal = $(id);
    if (!modal) return;
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
    $("mainContent")?.removeAttribute("inert");
    document.querySelector(".site-header")?.removeAttribute("inert");
    activeModal = null;
    if (modalReturnFocus?.focus) modalReturnFocus.focus();
    modalReturnFocus = null;
}

function handleModalKeyboard(event) {
    if (!activeModal || activeModal.classList.contains("hidden")) return;
    if (event.key === "Escape") {
        event.preventDefault();
        closeModal(activeModal.id);
        return;
    }
    if (event.key !== "Tab") return;
    const focusable = [...activeModal.querySelectorAll("button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])")];
    if (!focusable.length) return;
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}

function activateWorkflowTab(activeTab) {
    document.querySelectorAll(".workflow-tab").forEach(tab => {
        const isActive = tab === activeTab;
        tab.classList.toggle("active", isActive);
        tab.setAttribute("aria-selected", String(isActive));
        tab.tabIndex = isActive ? 0 : -1;
        $(tab.getAttribute("aria-controls")).hidden = !isActive;
    });
}

function openInterpreterDirectory() {
    if (!currentUser) {
        show("heroView");
        loadFeaturedProfiles();
        window.requestAnimationFrame(() => $("featuredProfiles").scrollIntoView({ behavior: "smooth", block: "start" }));
        return;
    }
    show("dashboardView");
    openDashboardPanel("directory");
}

function openAuth(signup, role) {
    openDialAfterSignIn = false;
    setAuthMode(signup);
    $("role").value = role;
    if ($("authStatus")) $("authStatus").textContent = "";
    show("authView");
}
function setAuthMode(signup) {
    signupMode = signup;
    $("authTitle").textContent = signup ? "Create account" : "Sign in";
    $("authSubmit").textContent = signup ? "Create account" : "Sign in";
    $("authToggle").textContent = signup ? "Already have an account? Sign in" : "Need an account? Create one";
    $("nameField").classList.toggle("hidden", !signup);
    $("phoneField").classList.toggle("hidden", !signup);
    $("signupPhone").required = signup;
    $("roleField").classList.toggle("hidden", !signup);
}


async function submitAuth(e) {
    e.preventDefault(); $("authStatus").textContent = "Working…";
    try {
        if (authActionToken && location.pathname === "/reset-password") {
            const response = await fetch("/api/auth/reset-password", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: authActionToken, password: $("password").value }) });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(payload.error || "Password reset failed.");
            history.replaceState({}, "", "/"); authActionToken = null; $("emailField").classList.remove("hidden"); $("email").required = true; $("authToggle").classList.remove("hidden");
            setAuthMode(false); $("authStatus").textContent = payload.message; return;
        }
        const email = $("email").value.trim(), password = $("password").value;
        if (signupMode) {
            const phone = completePhoneNumber("signupPhone");
            normalizePhoneNumber(phone);
            const name = $("displayName").value.trim() || email.split("@")[0];
            const role = $("role").value;
            const response = await fetch("/api/auth/register", { method: "POST", credentials: "same-origin",
                headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password, displayName: name, phone, role }) });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(payload.error || "Account creation failed.");
            $("authStatus").textContent = payload.message;
            setAuthMode(false);
            return;
        }
        const response = await fetch("/api/auth/login", { method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.error || "Sign in failed.");
        await handleAuthState({ ...payload.user, accessToken: payload.accessToken });
        $("authStatus").textContent = "";
    } catch (error) { $("authStatus").textContent = error.message; }
}

async function requestPasswordReset() {
    const email = $("email").value.trim();
    if (!email) { $("authStatus").textContent = "Enter your email address first."; return; }
    const response = await fetch("/api/auth/forgot-password", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }) });
    const payload = await response.json().catch(() => ({}));
    $("authStatus").textContent = payload.message || "If the account exists, a recovery link will be sent.";
}

async function localSignOut() {
    try { await apiFetch("/api/auth/logout", { method: "POST", body: "{}" }); } catch (_) { /* clear local state anyway */ }
    await handleAuthState(null);
}

async function handleAuthState(user) {
    currentUser = user;
    const resumeDial = Boolean(user && openDialAfterSignIn);
    openDialAfterSignIn = false;
    document.body.classList.toggle("signed-in", Boolean(user));
    if (!user) document.body.classList.remove("nav-open");
    $("authNav").textContent = user ? "Log out" : "Log in";
    if ($("landingLogin")) $("landingLogin").setAttribute("aria-label", user ? "Log out" : "Log in");
    if (!user) {
        currentProfile = null;
        currentInterpreterProfile = null;
        dashboardHistory = ["home"];
        clearSelectedInterpreter();
        stopMessagePolling();
        cleanupDashboardListeners();
        cleanupCall();
        show("heroView");
        return;
    }

    // Authentication and dashboard loading are intentionally separated so a
    // missing profile cannot leave an authenticated user stuck on login.
    try {
        const fallbackProfile = {
            uid: user.uid,
            email: (user.email || "").toLowerCase(),
            displayName: user.displayName || user.email || "FiniSpeak user",
            role: "customer"
        };
        const accountPayload = await apiFetch("/api/accounts/me");
        currentProfile = { ...fallbackProfile, ...(accountPayload.account || {}) };
        currentInterpreterProfile = null;
        if (isInterpreterRole(currentProfile.role)) {
            const profilePayload = await apiFetch("/api/translators/me/profile");
            currentInterpreterProfile = { ...(profilePayload.profile || {}), ...(profilePayload.private || {}) };
        }

        hydrateDashboardProfile();
        await loadProcessingCapabilities().catch(error => console.warn("Experimental processing unavailable:", error));
        const isTranslator = isInterpreterRole(currentProfile.role);
        const isAdmin = currentProfile.role === "admin";
        $("interpreterProfileNav").classList.toggle("hidden", !isTranslator);
        $("adminNav").classList.toggle("hidden", !isAdmin);
        setLanguageLessonAction(isTranslator);
        setTranslatorDiscoveryVisible(!isTranslator);
        $("translatorTools").classList.toggle("hidden", !isTranslator);

        await refreshRtcConfiguration();

        // Show the dashboard before loading optional translator/profile data so
        // a profile problem cannot block navigation after login.
        openDashboardPanel(isAdmin ? "admin" : "home", "reset");
        show("dashboardView");
        if (resumeDial) showCallDialPad();
        $("authStatus").textContent = "";

        if (isTranslator) {
            try {
                if (currentInterpreterProfile) hydrateInterpreterProfile(currentInterpreterProfile);
                else await loadInterpreterProfile();
            } catch (error) {
                console.error("Interpreter profile load failed:", error);
                $("translatorRequestStatus").textContent = `Dashboard loaded, but the interpreter profile could not be loaded: ${error.message}`;
            }
            // Taxonomy powers three independent multi-selects. A migrated or
            // partially populated profile must not prevent their initialization.
            try {
                await loadTaxonomy();
            } catch (taxonomyError) {
                console.warn("Interpreter taxonomy load failed; saved profile remains available:", taxonomyError);
            }
        }

        try { startDashboardListeners(); } catch (error) { console.error("Dashboard listeners failed:", error); }
        loadConversationHistory().catch(error => console.error("History load failed:", error));
    } catch (error) {
        console.error("Dashboard initialization failed:", error);
        // Last-resort authenticated fallback: never strand the user on login.
        currentProfile = {
            uid: user.uid,
            email: user.email || "",
            displayName: user.displayName || user.email || "FiniSpeak user",
            role: "customer"
        };
        hydrateDashboardProfile();
        $("interpreterProfileNav")?.classList.add("hidden");
        $("translatorTools")?.classList.add("hidden");
        setLanguageLessonAction(false);
        setTranslatorDiscoveryVisible(true);
        openDashboardPanel("home");
        show("dashboardView");
        if (resumeDial) showCallDialPad();
        $("dashboardStatus").textContent = `Signed in, but some account data could not load: ${error.message}`;
        $("authStatus").textContent = "";
        try { startDashboardListeners(); } catch (listenerError) { console.error("Dashboard listeners failed:", listenerError); }
        loadConversationHistory().catch(historyError => console.error("History load failed:", historyError));
    }
}


function hydrateDashboardProfile() {
    const name = currentProfile.displayName || currentProfile.email || "FiniSpeak";
    const roleLabel = currentProfile.role === "admin" ? "Administrator" : isInterpreterRole(currentProfile.role) ? "Translator" : "Customer";
    $("welcomeName").textContent = name;
    $("appWelcomeName").textContent = name.split(/\s+/).filter(Boolean)[0] || "there";
    $("accountRole").textContent = `${roleLabel} account`;
    $("sidebarName").textContent = name;
    $("sidebarRole").textContent = roleLabel;
    $("profileInitials").textContent = name.split(/\s+/).filter(Boolean).slice(0,2).map(part => part[0]).join("").toUpperCase() || "FS";
    $("profileDisplayName").value = currentProfile.displayName || "";
    $("profileEmail").value = currentProfile.email || currentUser?.email || "";
    setPhoneFieldValue("profilePhone", currentProfile.phone || "");
    const profileLocation = currentProfile.profileLocation || currentInterpreterProfile?.serviceLocation || {};
    $("profileServiceArea").value = [profileLocation.city, profileLocation.state, profileLocation.country].filter(Boolean).join(", ");
    $("profileShowOnMap").checked = Boolean(profileLocation.showOnMap);
    $("profileRole").value = roleLabel;
    $("settingsEmail").textContent = currentProfile.email || currentUser?.email || "";
    loadFriends().catch(error => console.warn("Friends unavailable:", error));
}

let dashboardHistory = ["home"];
let profileReturnPanel = "directory";

function nextDashboardHistory(history, panel, mode) {
    const current = Array.isArray(history) && history.length ? history.slice() : ["home"];
    if (mode === "back") return current;
    if (panel === "home") return ["home"];
    if (mode === "reset") return ["home", panel];
    if (current[current.length - 1] === panel) return current;
    const existing = current.indexOf(panel);
    if (existing >= 0) return current.slice(0, existing + 1);
    return [...current, panel];
}

function updateDashboardBackButton() {
    const button = $("dashboardBackButton");
    if (!button) return;
    const showBack = (dashboardHistory[dashboardHistory.length - 1] || "home") !== "home";
    button.classList.toggle("hidden", !showBack);
    button.hidden = !showBack;
}

function goDashboardBack() {
    if (dashboardHistory.length > 1) dashboardHistory.pop();
    else dashboardHistory = ["home"];
    openDashboardPanel(dashboardHistory[dashboardHistory.length - 1] || "home", "back");
    if ($("dashboardBackButton")?.hidden) $("mainContent")?.focus();
}

function openDashboardPanel(panel, historyMode = "push") {
    const ids = { home: "dashboardHome", dial: "dashboardDial", directory: "dashboardDirectory", classroom: "dashboardClassroom", careers: "dashboardCareers", friends: "dashboardFriends", messages: "dashboardMessages", profile: "dashboardProfile", interpreter: "dashboardInterpreter", admin: "dashboardAdmin", settings: "dashboardSettings", lesson: "dashboardLesson", schedule: "conceptSchedulePanel", goal: "dashboardGoal", live: "dashboardLive", match: "dashboardMatch", summary: "dashboardSummary", transcript: "dashboardTranscript", intelligence: "dashboardIntelligence" };
    if (!ids[panel]) return;
    if (historyMode !== "back") dashboardHistory = nextDashboardHistory(dashboardHistory, panel, historyMode);
    updateDashboardBackButton();
    Object.entries(ids).forEach(([key, id]) => $(id)?.classList.toggle("hidden", key !== panel));
    document.querySelectorAll("[data-dashboard-panel]").forEach(button => {
        const active = button.dataset.dashboardPanel === panel;
        button.classList.toggle("active", active);
        if (active) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current");
    });
    document.body.classList.remove("nav-open");
    $("conceptMenuButton")?.setAttribute("aria-expanded", "false");
    if (panel === "messages") startMessagesPanel();
    else stopMessagePolling();
    if (historyMode === "back") return;
    $("dashboardView")?.querySelector(".dashboard-content")?.scrollTo({ top: 0, behavior: "auto" });
    if (panel === "directory") { setDirectoryView("map"); loadInterpreterDirectory(); }
    if (panel === "friends") loadFriends();
    if (panel === "admin") loadAdminDashboard();
    if (panel === "lesson") renderLessonScreen();
    if (panel === "schedule") renderScheduleScreen();
    if (panel === "goal") renderGoalScreen();
    if (panel === "match") renderAutoMatchScreen();
    if (panel === "live") renderLiveScreen();
    if (panel === "summary") renderSummaryScreen();
    if (panel === "classroom") renderEducationScreen();
    if (panel === "careers") renderCareersScreen();
    const tabForPanel = { directory: "translate", dial: "calls", messages: "chats", classroom: "education", careers: "careers" };
    setAppTab(tabForPanel[panel] || "");
}

function setAppTab(tab) {
    document.querySelectorAll("[data-app-tab]").forEach(button => {
        const active = Boolean(tab) && button.dataset.appTab === tab;
        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", String(active));
    });
}

function goToAppHome() {
    if (!currentUser) {
        show("heroView");
        return;
    }
    show("dashboardView");
    openDashboardPanel("home", "reset");
}

function openAppTab(tab) {
    const panels = { translate: "directory", calls: "dial", chats: "messages", education: "classroom", careers: "careers" };
    const panel = panels[tab];
    if (!panel) return;
    if (!currentUser) {
        if (tab === "translate") {
            show("heroView");
            return;
        }
        openAuth(false, tab === "careers" ? "translator" : "customer");
        $("authStatus").textContent = tab === "careers" ? "Sign in to join as an interpreter." : "Sign in to continue.";
        return;
    }
    show("dashboardView");
    openDashboardPanel(panel);
}

function setChatBadge(count) {
    const value = Math.max(0, Number(count) || 0);
    document.querySelectorAll("[data-chat-badge]").forEach(badge => {
        badge.textContent = value > 99 ? "99+" : String(value);
        badge.classList.toggle("hidden", value < 1);
    });
}

async function refreshChatBadge() {
    if (!currentUser) return;
    try {
        const result = await apiFetch("/api/messages/conversations");
        const total = (result.conversations || []).reduce((sum, item) => sum + (Number(item.unreadCount) || 0), 0);
        setChatBadge(total);
    } catch (_) { /* The badge stays at its last count. */ }
}

function renderCareersScreen() {
    const button = $("careersInterpreter");
    if (!button) return;
    const interpreter = isInterpreterRole(currentProfile?.role);
    button.textContent = interpreter ? "Your interpreter profile" : "Join as an interpreter";
    button.onclick = () => {
        if (interpreter) openDashboardPanel("interpreter");
        else joinAsInterpreter();
    };
}

async function joinAsInterpreter() {
    const status = $("careersStatus");
    if (status) status.textContent = "Starting…";
    try {
        await apiFetch("/api/translators/enroll", { method: "POST", body: JSON.stringify({ phone: currentProfile?.phone || "" }) });
        const accountPayload = await apiFetch("/api/accounts/me");
        currentProfile = { ...(currentProfile || {}), ...(accountPayload.account || {}) };
        const isTranslator = isInterpreterRole(currentProfile.role);
        $("interpreterProfileNav")?.classList.toggle("hidden", !isTranslator);
        setLanguageLessonAction(isTranslator);
        setTranslatorDiscoveryVisible(!isTranslator);
        $("translatorTools")?.classList.toggle("hidden", !isTranslator);
        if (status) status.textContent = "Interpreter profile started. Finish credentials in your interpreter profile.";
        renderCareersScreen();
    } catch (error) {
        if (status) status.textContent = error.message;
    }
}

async function apiFetch(path, options = {}) {
    if (!currentUser) throw new Error("Sign in to continue.");
    const isForm = options.body instanceof FormData;
    const csrf = document.cookie.split("; ").find(row => row.startsWith("csrf_access_token="))?.split("=")[1];
    const headers = { ...(isForm ? {} : { "Content-Type": "application/json" }), ...(options.headers || {}) };
    if (currentUser.accessToken) headers.Authorization = `Bearer ${currentUser.accessToken}`;
    if (csrf) headers["X-CSRF-TOKEN"] = decodeURIComponent(csrf);
    const method = String(options.method || "GET").toUpperCase();
    const response = await fetch(path, {
        ...options, cache: method === "GET" ? "no-store" : options.cache, credentials: "same-origin", headers
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    return payload;
}

function setCallProcessingModesOpen(open) {
    const modes = document.querySelector(".call-nav-modes");
    const toggle = $("toggleCallProcessingModes");
    const panel = $("callProcessingModes");
    if (!modes || !toggle || !panel) return;
    modes.classList.toggle("is-collapsed", !open);
    toggle.setAttribute("aria-expanded", String(open));
    panel.setAttribute("aria-hidden", String(!open));
    panel.style.left = "";
    if (!open) return;
    const overflow = panel.getBoundingClientRect().right - (window.innerWidth - 12);
    if (overflow > 0) panel.style.left = `${-Math.ceil(overflow)}px`;
}
async function loadProcessingCapabilities() {
    const result = await apiFetch("/api/calls/processing-capabilities"); processingModesEnabled = result.experimental === true;
    document.querySelectorAll(".processing-mode-panel, .processing-mode-toggle").forEach(panel => panel.classList.toggle("hidden", !processingModesEnabled));
    if (!processingModesEnabled) setCallProcessingModesOpen(false);
    selectedProcessingMode = result.default || "streaming"; renderProcessingMode();
}
function renderProcessingMode() {
    document.querySelectorAll("[data-processing-mode]").forEach(button => { button.setAttribute("aria-pressed", String(button.dataset.processingMode === selectedProcessingMode)); button.disabled = transcriptionSwitching; });
    const processingLabels = { baseline: "Baseline", concurrent: "Concurrent Audio Processing", streaming: "Real-Time Streaming" };
    document.querySelectorAll("[data-active-processing-label]").forEach(label => label.textContent = processingLabels[selectedProcessingMode] || selectedProcessingMode);
}
async function selectProcessingMode(mode) {
    if (!processingModesEnabled || transcriptionSwitching) return; const next = mode;
    if (!activeCallId) { selectedProcessingMode = next; renderProcessingMode(); return; }
    await switchProcessingMode(next);
}

async function loadAdminDashboard() {
    if (currentProfile?.role !== "admin") return;
    $("adminStatus").textContent = "Loading platform activity…";
    try {
        const [overview, queue, activity] = await Promise.all([
            apiFetch("/api/admin/overview"), apiFetch("/api/admin/verifications"), apiFetch("/api/admin/activity")
        ]);
        const metrics = overview.metrics || {};
        $("adminAccounts").textContent = metrics.accounts ?? 0;
        $("adminActiveAccounts").textContent = `${metrics.activeAccounts ?? 0} active`;
        $("adminVerified").textContent = metrics.verifiedInterpreters ?? 0;
        $("adminPending").textContent = `${metrics.pendingVerifications ?? 0} awaiting review`;
        $("adminSessions").textContent = metrics.sessions ?? 0;
        $("adminActiveSessions").textContent = `${metrics.activeSessions ?? 0} active`;
        $("adminOrganizations").textContent = metrics.organizations ?? 0;
        const pendingInterpreters = queue.interpreters || [];
        renderAdminVerificationQueue(pendingInterpreters);
        renderAdminAccounts(activity.accounts || [], pendingInterpreters);
        renderAdminSessions(activity.sessions || []);
        renderAdminReviews(activity.reviews || []);
        renderAdminOrganizations(activity.organizations || []);
        $("adminStatus").textContent = "Platform activity is up to date.";
    } catch (error) {
        $("adminStatus").textContent = `Could not load administration data: ${error.message}`;
        $("adminVerificationQueue").innerHTML = '<p class="status">The verification queue is unavailable.</p>';
    }
}

function adminEmpty(message) {
    return `<p class="admin-empty">${escapeHtml(message)}</p>`;
}

function renderAdminAccounts(accounts, pendingInterpreters = []) {
    const container = $("adminAccountList");
    if (!accounts.length) { container.innerHTML = adminEmpty("No accounts found."); return; }
    const pendingIds = new Set(pendingInterpreters.flatMap(profile => [profile.id, profile.uid].filter(Boolean)));
    container.innerHTML = accounts.map(account => {
        const isCurrentAdmin = account.uid === currentUser?.uid;
        const deleted = account.status === "deleted" || Boolean(account.deletedAt);
        const awaitingApproval = !deleted && pendingIds.has(account.uid);
        const approveButton = awaitingApproval ? `<button type="button" data-approve-interpreter>Approve interpreter</button>` : "";
        return `<article class="admin-account-editor" data-admin-account="${escapeHtml(account.uid || "")}"><div class="admin-account-heading"><strong>${escapeHtml(account.displayName || account.email || "User")}</strong><span class="status-badge">${escapeHtml(awaitingApproval ? "awaiting approval" : deleted ? "deleted" : account.status || "active")}</span></div><div class="admin-account-fields"><label>Name<input data-account-field="displayName" value="${escapeHtml(account.displayName || "")}"${deleted ? " disabled" : ""}></label><label>Email<input data-account-field="email" type="email" value="${escapeHtml(account.email || "")}"${deleted ? " disabled" : ""}></label><label>Phone<input data-account-field="phone" type="tel" value="${escapeHtml(account.phone || "")}"${deleted ? " disabled" : ""}></label><label>Role<select data-account-field="role"${deleted || isCurrentAdmin ? " disabled" : ""}><option value="customer"${account.role === "customer" ? " selected" : ""}>Customer</option><option value="translator_applicant"${account.role === "translator_applicant" ? " selected" : ""}>Translator applicant</option><option value="translator"${account.role === "translator" ? " selected" : ""}>Translator</option><option value="admin"${account.role === "admin" ? " selected" : ""}>Administrator</option></select></label><label>Status<select data-account-field="status"${deleted || isCurrentAdmin ? " disabled" : ""}><option value="active"${account.status === "active" || !account.status ? " selected" : ""}>Active</option><option value="pending"${account.status === "pending" ? " selected" : ""}>Pending</option><option value="suspended"${account.status === "suspended" ? " selected" : ""}>Suspended</option></select></label></div><div class="admin-account-actions">${approveButton}<button type="button" data-save-account${deleted ? " disabled" : ""}>Save profile</button><button class="secondary reject-action" type="button" data-delete-account${deleted || isCurrentAdmin ? " disabled" : ""}>${deleted ? "Deleted" : "Delete account"}</button></div></article>`;
    }).join("");
    container.querySelectorAll("[data-approve-interpreter]").forEach(button => button.onclick = () => reviewInterpreter(button.closest("[data-admin-account]").dataset.adminAccount, "verified"));
    container.querySelectorAll("[data-save-account]").forEach(button => button.onclick = () => saveAdminAccount(button.closest("[data-admin-account]")));
    container.querySelectorAll("[data-delete-account]").forEach(button => button.onclick = () => deleteAdminAccount(button.closest("[data-admin-account]")));
}

async function saveAdminAccount(editor) {
    const button = editor.querySelector("[data-save-account]"); button.disabled = true;
    const values = Object.fromEntries([...editor.querySelectorAll("[data-account-field]")].filter(field => !field.disabled).map(field => [field.dataset.accountField, field.value.trim()]));
    try {
        await apiFetch(`/api/admin/accounts/${encodeURIComponent(editor.dataset.adminAccount)}`, { method: "PATCH", body: JSON.stringify(values) });
        $("adminStatus").textContent = values.role === "translator" ? "Account updated and translator approved." : "Account profile updated.";
        await loadAdminDashboard();
    } catch (error) {
        $("adminStatus").textContent = `Could not update account: ${error.message}`;
        button.disabled = false;
    }
}

async function deleteAdminAccount(editor) {
    if (!window.confirm("Soft-delete this account? The user will be signed out and the record will be retained for audit purposes.")) return;
    const button = editor.querySelector("[data-delete-account]"); button.disabled = true;
    try {
        await apiFetch(`/api/admin/accounts/${encodeURIComponent(editor.dataset.adminAccount)}`, { method: "DELETE" });
        $("adminStatus").textContent = "Account soft-deleted and active sessions revoked.";
        await loadAdminDashboard();
    } catch (error) {
        $("adminStatus").textContent = `Could not delete account: ${error.message}`;
        button.disabled = false;
    }
}

let savedFriends = [];

function dialNationalDigits() {
    return ($("receiverPhone")?.value || "").replace(/\D/g, "").slice(0, 15);
}

function formatDialNumber(digits) {
    const country = $("receiverPhoneCountry")?.value || "+1";
    if (country === "+1") {
        const area = digits.slice(0, 3);
        const prefix = digits.slice(3, 6);
        const line = digits.slice(6, 10);
        const extra = digits.slice(10);
        if (digits.length <= 3) return area;
        if (digits.length <= 6) return `(${area}) ${prefix}`;
        return `(${area}) ${prefix}-${line}${extra}`;
    }
    return digits.replace(/(\d{3})(?=\d)/g, "$1 ").trim();
}

function clearDialFriendSelection() {
    if ($("receiverEmail")) $("receiverEmail").value = "";
    if ($("dialTargetName")) $("dialTargetName").textContent = "";
}

function setDialNationalDigits(digits) {
    const input = $("receiverPhone");
    if (!input) return;
    input.value = formatDialNumber(String(digits || "").replace(/\D/g, "").slice(0, 15));
}

function appendDialDigit(value) {
    if (!/^\d$/.test(value || "")) return;
    clearDialFriendSelection();
    setDialNationalDigits(dialNationalDigits() + value);
}

function backspaceDialDigit() {
    clearDialFriendSelection();
    setDialNationalDigits(dialNationalDigits().slice(0, -1));
}

function applyFriendToDialPad(friend) {
    if (!friend) return;
    const phone = friend.savedPhone || friend.phone || "";
    const name = friend.nickname || friend.displayName || friend.email || "Friend";
    clearDialFriendSelection();
    if (phone) {
        setPhoneFieldValue("receiverPhone", phone);
        setDialNationalDigits(dialNationalDigits());
        if ($("dialTargetName")) $("dialTargetName").textContent = name;
    } else if (friend.email) {
        if ($("receiverPhone")) $("receiverPhone").value = "";
        if ($("receiverEmail")) $("receiverEmail").value = friend.email;
        if ($("dialTargetName")) $("dialTargetName").textContent = `${name} · ${friend.email}`;
    }
    $("receiverPhone")?.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function loadFriends() {
    const container = $("friendsList");
    const dialList = $("dialFriendsList");
    if (container) container.innerHTML = "<p>Loading friends…</p>";
    if (dialList) dialList.innerHTML = '<p class="dial-friends-empty">Loading friends…</p>';
    try {
        const result = await apiFetch("/api/friends");
        savedFriends = result.friends || [];
        renderFriends(savedFriends);
        renderDialFriends(savedFriends);
        renderGroupFriendChoices(savedFriends);
        if ($("friendsStatus")) $("friendsStatus").textContent = `${savedFriends.length} saved friend${savedFriends.length === 1 ? "" : "s"}.`;
    } catch (error) {
        savedFriends = [];
        if (container) container.innerHTML = `<p class="status">Could not load friends: ${escapeHtml(error.message)}</p>`;
        if (dialList) dialList.innerHTML = `<p class="dial-friends-empty">Could not load friends.</p>`;
    }
}

async function addFriend(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
        const phone = completePhoneNumber("friendPhone");
        await apiFetch("/api/friends", { method: "POST", body: JSON.stringify({ email: $("friendEmail").value.trim(), phone, savedPhone: phone, nickname: $("friendNickname").value.trim() }) });
        form.reset(); $("friendPhoneCountry").value = "+1"; $("friendsStatus").textContent = "Friend added."; await loadFriends();
    } catch (error) { $("friendsStatus").textContent = `Could not add friend: ${error.message}`; }
    finally { button.disabled = false; }
}

function renderFriends(friends) {
    const container = $("friendsList");
    if (!friends.length) { container.innerHTML = '<p class="admin-empty">No friends saved yet.</p>'; return; }
    container.innerHTML = friends.map(friend => `<article class="friend-card" data-friend-id="${escapeHtml(friend.uid)}"><div class="friend-card-heading"><span class="presence-dot ${friend.online ? "online" : ""}" aria-hidden="true"></span><div><strong>${escapeHtml(friend.nickname || friend.displayName || friend.email)}</strong><small>${friend.online ? "Online now" : "Offline"} · ${escapeHtml(friend.email || "")}</small></div></div><div class="friend-fields"><label>Nickname<input data-friend-field="nickname" maxlength="160" value="${escapeHtml(friend.nickname || "")}"></label><label>Saved number<input data-friend-field="savedPhone" type="tel" value="${escapeHtml(friend.savedPhone || friend.phone || "")}"></label></div><div class="friend-actions"><button class="secondary" type="button" data-message-friend>Message</button><button type="button" data-call-friend>Start call</button><button class="secondary" type="button" data-save-friend>Save</button><button class="secondary reject-action" type="button" data-remove-friend>Remove</button></div></article>`).join("");
    container.querySelectorAll("[data-message-friend]").forEach(button => button.onclick = () => messageFriend(button.closest("[data-friend-id]")));
    container.querySelectorAll("[data-call-friend]").forEach(button => button.onclick = () => callFriend(button.closest("[data-friend-id]"), friends));
    container.querySelectorAll("[data-save-friend]").forEach(button => button.onclick = () => saveFriend(button.closest("[data-friend-id]")));
    container.querySelectorAll("[data-remove-friend]").forEach(button => button.onclick = () => removeFriend(button.closest("[data-friend-id]")));
}

function renderDialFriends(friends) {
    const container = $("dialFriendsList");
    if (!container) return;
    if (!friends.length) {
        container.innerHTML = '<p class="dial-friends-empty">No friends yet. Add the people you call inside FiniSpeak.</p>';
        return;
    }
    container.innerHTML = friends.map(friend => {
        const name = friend.nickname || friend.displayName || friend.email || "Friend";
        const detail = friend.savedPhone || friend.phone || friend.email || "";
        return `<button type="button" class="dial-friend" data-friend-id="${escapeHtml(friend.uid)}"><span class="concept-avatar dial-friend-avatar" aria-hidden="true">${escapeHtml(profileInitials(name))}</span><span class="dial-friend-copy"><strong>${escapeHtml(name)}</strong><small>${friend.online ? "Online" : "Offline"}${detail ? ` · ${escapeHtml(detail)}` : ""}</small></span><span class="presence-dot ${friend.online ? "online" : ""}" aria-hidden="true"></span></button>`;
    }).join("");
    container.querySelectorAll(".dial-friend").forEach(button => {
        button.onclick = () => applyFriendToDialPad(savedFriends.find(item => item.uid === button.dataset.friendId));
    });
}

function callFriend(card, friends) {
    const friend = friends.find(item => item.uid === card.dataset.friendId); if (!friend) return;
    showCallDialPad();
    applyFriendToDialPad(friend);
}

async function saveFriend(card) {
    const button = card.querySelector("[data-save-friend]"); button.disabled = true;
    const data = Object.fromEntries([...card.querySelectorAll("[data-friend-field]")].map(field => [field.dataset.friendField, field.value.trim()]));
    try { await apiFetch(`/api/friends/${encodeURIComponent(card.dataset.friendId)}`, { method: "PATCH", body: JSON.stringify(data) }); $("friendsStatus").textContent = "Friend updated."; await loadFriends(); }
    catch (error) { $("friendsStatus").textContent = `Could not update friend: ${error.message}`; button.disabled = false; }
}

async function removeFriend(card) {
    if (!window.confirm("Remove this friend from your saved list?")) return;
    try { await apiFetch(`/api/friends/${encodeURIComponent(card.dataset.friendId)}`, { method: "DELETE" }); $("friendsStatus").textContent = "Friend removed."; await loadFriends(); }
    catch (error) { $("friendsStatus").textContent = `Could not remove friend: ${error.message}`; }
}

let savedConversations = [];
let openConversationId = "";
let pendingConversationId = "";
let renderedMessageTail = "";
let messagePollTimer = null;

function messageTime(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function stopMessagePolling() {
    if (!messagePollTimer) return;
    window.clearInterval(messagePollTimer);
    messagePollTimer = null;
}

function startMessagePolling() {
    stopMessagePolling();
    messagePollTimer = window.setInterval(() => {
        if ($("dashboardMessages")?.classList.contains("hidden")) {
            stopMessagePolling();
            return;
        }
        refreshOpenMessages();
    }, 4000);
}

function renderGroupFriendChoices(friends) {
    const container = $("groupFriendChoices");
    if (!container) return;
    if (!friends.length) {
        container.innerHTML = '<p class="transcript-empty">Save a friend before creating a group.</p>';
        return;
    }
    container.innerHTML = friends.map(friend => {
        const name = friend.nickname || friend.displayName || friend.email || "Friend";
        return `<label class="inline-check"><input type="checkbox" value="${escapeHtml(friend.uid)}"> ${escapeHtml(name)}</label>`;
    }).join("");
}

function renderConversationList(conversations) {
    const container = $("conversationList");
    if (!container) return;
    if (!conversations.length) {
        container.innerHTML = '<p class="transcript-empty">No chats yet. Message a friend or create a group.</p>';
        setChatBadge(0);
        return;
    }
    let chatUnreadTotal = 0;
    container.innerHTML = conversations.map(conversation => {
        const preview = conversation.lastMessage
            ? `${conversation.lastMessage.mine ? "You: " : ""}${conversation.lastMessage.body}`
            : "No messages yet";
        const when = conversation.lastMessage?.createdAt ? messageTime(conversation.lastMessage.createdAt) : "";
        const unread = Number(conversation.unreadCount) || 0;
        const current = conversation.id === openConversationId ? ' aria-current="true"' : "";
        const badge = unread ? `<span class="status-badge">${unread > 99 ? "99+" : unread} unread</span>` : "";
        chatUnreadTotal += unread;
        return `<div class="conversation-row"><button type="button" class="conversation-item" data-conversation-id="${escapeHtml(conversation.id)}"${current}><strong>${escapeHtml(conversation.title || "Chat")}</strong><span class="conversation-meta">${escapeHtml(preview)}${when ? ` · ${escapeHtml(when)}` : ""}</span></button>${badge}</div>`;
    }).join("");
    setChatBadge(chatUnreadTotal);
    container.querySelectorAll("[data-conversation-id]").forEach(button => {
        button.onclick = () => openConversation(button.dataset.conversationId);
    });
}

function showMessageList() {
    openConversationId = "";
    renderedMessageTail = "";
    $("messageThread")?.classList.add("hidden");
    $("messageComposeForm")?.classList.add("hidden");
    $("groupMemberTools")?.classList.add("hidden");
    $("conversationList")?.classList.remove("hidden");
    if ($("messageThreadEyebrow")) $("messageThreadEyebrow").textContent = "Inbox";
    if ($("messageThreadTitle")) $("messageThreadTitle").textContent = "Your chats";
    if ($("messageThreadHelp")) $("messageThreadHelp").textContent = "Open a chat, or start one from the form.";
    renderConversationList(savedConversations);
}

function renderGroupTools(conversation) {
    const tools = $("groupMemberTools");
    if (!tools) return;
    const isGroup = conversation.kind === "group";
    tools.classList.toggle("hidden", !isGroup);
    if (!isGroup) return;
    const select = $("groupAddMember");
    const memberIds = new Set((conversation.members || []).map(member => member.uid));
    const choices = savedFriends.filter(friend => !memberIds.has(friend.uid));
    const owner = conversation.viewerRole === "owner";
    select.innerHTML = choices.length
        ? choices.map(friend => `<option value="${escapeHtml(friend.uid)}">${escapeHtml(friend.nickname || friend.displayName || friend.email || "Friend")}</option>`).join("")
        : '<option value="">No more friends to add</option>';
    select.disabled = !owner || !choices.length;
    $("groupAddMemberField")?.classList.toggle("hidden", !owner);
    $("groupAddMemberButton").disabled = !owner || !choices.length;
    $("groupAddMemberButton").classList.toggle("hidden", !owner);
}

function renderOpenConversation(result, { forceScroll = false } = {}) {
    const conversation = result?.conversation;
    if (!conversation || conversation.id !== openConversationId) return;
    const thread = $("messageThread");
    const messages = result.messages || [];
    const tail = messages.map(message => message.id).join(",");
    const others = (conversation.members || []).filter(member => member.uid !== currentUser?.uid);
    $("messageThreadEyebrow").textContent = conversation.kind === "group" ? "Group" : "Direct message";
    $("messageThreadTitle").textContent = conversation.title || "Chat";
    if (conversation.kind === "direct") {
        $("messageThreadHelp").textContent = others[0] ? (others[0].online ? "Online now" : "Offline") : "Direct message";
    } else {
        const names = (conversation.members || []).map(member => member.displayName).filter(Boolean);
        $("messageThreadHelp").textContent = names.length ? names.join(", ") : "Group chat";
    }
    $("conversationList")?.classList.add("hidden");
    thread?.classList.remove("hidden");
    $("messageComposeForm")?.classList.remove("hidden");
    renderGroupTools(conversation);
    if (!thread || tail === renderedMessageTail) return;
    const nearBottom = forceScroll || thread.scrollHeight - thread.scrollTop - thread.clientHeight < 80;
    renderedMessageTail = tail;
    thread.innerHTML = messages.length
        ? messages.map(message => `<article class="conversation-item"><strong>${escapeHtml(message.mine ? "You" : (message.senderName || "FiniSpeak user"))}${message.createdAt ? ` · ${escapeHtml(messageTime(message.createdAt))}` : ""}</strong><span class="conversation-meta">${escapeHtml(message.body)}</span></article>`).join("")
        : '<p class="transcript-empty">No messages yet. Say hello.</p>';
    if (nearBottom) thread.scrollTop = thread.scrollHeight;
    const saved = savedConversations.find(item => item.id === conversation.id);
    if (saved) saved.unreadCount = 0;
    renderConversationList(savedConversations);
}

async function loadConversations({ announce = false } = {}) {
    const result = await apiFetch("/api/messages/conversations");
    savedConversations = result.conversations || [];
    renderConversationList(savedConversations);
    if (announce && $("messagesStatus") && !openConversationId) {
        const count = savedConversations.length;
        $("messagesStatus").textContent = `${count} chat${count === 1 ? "" : "s"}.`;
    }
    return savedConversations;
}

async function openConversation(conversationId) {
    if (!conversationId) return;
    openConversationId = conversationId;
    const result = await apiFetch(`/api/messages/conversations/${encodeURIComponent(conversationId)}`);
    const index = savedConversations.findIndex(item => item.id === result.conversation?.id);
    if (result.conversation && index >= 0) {
        savedConversations[index] = { ...savedConversations[index], ...result.conversation };
    }
    renderOpenConversation(result, { forceScroll: true });
}

async function refreshOpenMessages() {
    try {
        await loadConversations({ announce: false });
        if (!openConversationId || $("dashboardMessages")?.classList.contains("hidden")) return;
        const result = await apiFetch(`/api/messages/conversations/${encodeURIComponent(openConversationId)}`);
        renderOpenConversation(result, { forceScroll: false });
    } catch (_) { /* keep the open chat if a refresh fails */ }
}

function startMessagesPanel() {
    renderGroupFriendChoices(savedFriends);
    if (!savedFriends.length) loadFriends().catch(() => {});
    loadConversations({ announce: true }).then(() => {
        if (!pendingConversationId) return null;
        const conversationId = pendingConversationId;
        pendingConversationId = "";
        return openConversation(conversationId);
    }).catch(error => {
        if ($("messagesStatus")) $("messagesStatus").textContent = `Could not load chats: ${error.message}`;
    });
    startMessagePolling();
}

async function messageFriend(card) {
    const friendId = card?.dataset.friendId;
    if (!friendId) return;
    try {
        const result = await apiFetch("/api/messages/conversations", {
            method: "POST", body: JSON.stringify({ kind: "direct", userId: friendId }),
        });
        pendingConversationId = result.conversation.id;
        openDashboardPanel("messages");
    } catch (error) {
        if ($("friendsStatus")) $("friendsStatus").textContent = `Could not open chat: ${error.message}`;
    }
}

async function startDirectMessage(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
        const email = $("messageEmail").value.trim();
        if (!email) throw new Error("Enter a FiniSpeak email.");
        const result = await apiFetch("/api/messages/conversations", {
            method: "POST", body: JSON.stringify({ kind: "direct", email }),
        });
        form.reset();
        await openConversation(result.conversation.id);
        await loadConversations({ announce: false });
        $("messagesStatus").textContent = "Chat opened.";
    } catch (error) {
        $("messagesStatus").textContent = error.message;
    } finally { button.disabled = false; }
}

async function createGroupMessage(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
        const memberIds = [...form.querySelectorAll('input[type="checkbox"]:checked')].map(input => input.value);
        const result = await apiFetch("/api/messages/conversations", {
            method: "POST",
            body: JSON.stringify({ kind: "group", title: $("groupTitle").value.trim(), memberIds }),
        });
        form.reset();
        await openConversation(result.conversation.id);
        await loadConversations({ announce: false });
        $("messagesStatus").textContent = "Group created.";
    } catch (error) {
        $("messagesStatus").textContent = error.message;
    } finally { button.disabled = false; }
}

async function sendConversationMessage(event) {
    event.preventDefault();
    if (!openConversationId) return;
    const body = $("messageBody").value.trim();
    if (!body) return;
    const button = event.currentTarget.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
        await apiFetch(`/api/messages/conversations/${encodeURIComponent(openConversationId)}/messages`, {
            method: "POST", body: JSON.stringify({ body }),
        });
        $("messageBody").value = "";
        await openConversation(openConversationId);
        await loadConversations({ announce: false });
    } catch (error) {
        $("messagesStatus").textContent = error.message;
    } finally {
        button.disabled = false;
        $("messageBody")?.focus();
    }
}

async function addGroupMember() {
    if (!openConversationId) return;
    const userId = $("groupAddMember")?.value;
    if (!userId) return;
    const button = $("groupAddMemberButton");
    button.disabled = true;
    try {
        await apiFetch(`/api/messages/conversations/${encodeURIComponent(openConversationId)}/members`, {
            method: "POST", body: JSON.stringify({ userId }),
        });
        await openConversation(openConversationId);
        $("messagesStatus").textContent = "Friend added to the group.";
    } catch (error) {
        $("messagesStatus").textContent = error.message;
        button.disabled = false;
    }
}

async function leaveGroup() {
    if (!openConversationId || !currentUser?.uid) return;
    if (!window.confirm("Leave this group?")) return;
    try {
        const result = await apiFetch(`/api/messages/conversations/${encodeURIComponent(openConversationId)}/members/${encodeURIComponent(currentUser.uid)}`, { method: "DELETE" });
        showMessageList();
        await loadConversations({ announce: false });
        $("messagesStatus").textContent = result.left ? "You left the group." : "Group updated.";
    } catch (error) {
        $("messagesStatus").textContent = error.message;
    }
}

function renderAdminSessions(sessions) {
    const container = $("adminSessionList");
    if (!sessions.length) { container.innerHTML = adminEmpty("No sessions have been created."); return; }
    container.innerHTML = sessions.slice(0, 12).map(session => {
        const date = timestampDate(session.createdAt);
        return `<article class="admin-list-row"><div><strong>${escapeHtml(session.callerName || session.callerId || "Customer session")}</strong><small>${escapeHtml(date ? date.toLocaleString() : "Recent")} · ${escapeHtml(session.language || "Language not detected")}</small></div><span class="status-badge">${escapeHtml(session.status || "unknown")}</span></article>`;
    }).join("");
}

function renderAdminReviews(reviews) {
    const container = $("adminReviewList");
    if (!reviews.length) { container.innerHTML = adminEmpty("No customer reviews yet."); return; }
    container.innerHTML = reviews.slice(0, 20).map(review => `<article class="admin-list-row admin-review-row"><div><strong>${escapeHtml(review.authorName || "Customer")} · ${Number(review.rating || 0)}/5</strong><small>${escapeHtml(review.text || "No written feedback")}</small></div><div class="admin-review-actions"><button class="secondary" type="button" data-review-status="visible" data-interpreter-id="${escapeHtml(review.interpreterId)}" data-review-id="${escapeHtml(review.id)}">Show</button><button class="secondary reject-action" type="button" data-review-status="hidden" data-interpreter-id="${escapeHtml(review.interpreterId)}" data-review-id="${escapeHtml(review.id)}">Hide</button></div></article>`).join("");
    container.querySelectorAll("[data-review-status]").forEach(button => button.onclick = () => moderateAdminReview(button));
}

async function moderateAdminReview(button) {
    const buttons = button.closest(".admin-review-actions").querySelectorAll("button");
    buttons.forEach(item => item.disabled = true);
    try {
        await apiFetch(`/api/admin/interpreters/${encodeURIComponent(button.dataset.interpreterId)}/reviews/${encodeURIComponent(button.dataset.reviewId)}`, { method: "PATCH", body: JSON.stringify({ status: button.dataset.reviewStatus }) });
        $("adminStatus").textContent = `Review is now ${button.dataset.reviewStatus}.`;
        await loadAdminDashboard();
    } catch (error) {
        $("adminStatus").textContent = `Could not moderate review: ${error.message}`;
        buttons.forEach(item => item.disabled = false);
    }
}

function renderAdminOrganizations(organizations) {
    const container = $("adminOrganizationList");
    if (!organizations.length) { container.innerHTML = adminEmpty("No organizations have been added yet."); return; }
    container.innerHTML = organizations.slice(0, 20).map(organization => `<article class="admin-list-row"><div><strong>${escapeHtml(organization.name || organization.displayName || "Organization")}</strong><small>${escapeHtml(organization.contactEmail || organization.domain || organization.id || "Managed organization")}</small></div><label class="admin-inline-control"><span class="sr-only">Organization status</span><select data-organization-id="${escapeHtml(organization.id || "")}"><option value="active"${organization.status === "active" ? " selected" : ""}>Active</option><option value="pending"${organization.status === "pending" ? " selected" : ""}>Pending</option><option value="suspended"${organization.status === "suspended" ? " selected" : ""}>Suspended</option></select></label></article>`).join("");
    container.querySelectorAll("[data-organization-id]").forEach(select => select.onchange = () => updateOrganizationStatus(select));
}

async function createOrganization(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
        await apiFetch("/api/admin/organizations", {
            method: "POST",
            body: JSON.stringify({ name: $("organizationName").value.trim(), contactEmail: $("organizationEmail").value.trim() })
        });
        form.reset();
        $("adminStatus").textContent = "Organization added.";
        await loadAdminDashboard();
    } catch (error) {
        $("adminStatus").textContent = `Could not add organization: ${error.message}`;
    } finally { button.disabled = false; }
}

async function updateOrganizationStatus(select) {
    select.disabled = true;
    try {
        await apiFetch(`/api/admin/organizations/${encodeURIComponent(select.dataset.organizationId)}`, {
            method: "PATCH", body: JSON.stringify({ status: select.value })
        });
        $("adminStatus").textContent = "Organization status updated.";
    } catch (error) {
        $("adminStatus").textContent = `Could not update organization: ${error.message}`;
        await loadAdminDashboard();
    } finally { select.disabled = false; }
}

function renderAdminVerificationQueue(profiles) {
    const container = $("adminVerificationQueue");
    $("adminQueueStatus").textContent = `${profiles.length} pending`;
    if (!profiles.length) {
        container.innerHTML = "<p>No credential submissions are waiting for review.</p>";
        return;
    }
    container.replaceChildren(...profiles.map(profile => {
        const row = document.createElement("article");
        row.className = "admin-review-item";
        const documents = (profile.credentialDocuments || []).map(document => document.path
            ? `<button class="text-button" type="button" data-credential-path="${escapeHtml(document.path)}">${escapeHtml(document.name || "Credential document")}</button>`
            : `<a href="${escapeHtml(document.url || "#")}" target="_blank" rel="noopener">${escapeHtml(document.name || "Credential document")}</a>`
        ).join("");
        row.innerHTML = `<div><strong>${escapeHtml(profile.displayName || profile.email || "Interpreter")}</strong><span>${escapeHtml([...(profile.languages || []), ...(profile.specialties || [])].slice(0, 4).join(" · ") || "Profile submitted")}</span><div class="admin-credential-links">${documents || "No uploaded documents"}</div></div><div class="admin-review-actions"><button class="secondary" type="button" data-status="needs_changes">Request changes</button><button type="button" data-status="verified">Approve</button></div>`;
        row.querySelectorAll("[data-status]").forEach(button => button.onclick = () => reviewInterpreter(profile.id, button.dataset.status));
        row.querySelectorAll("[data-credential-path]").forEach(button => button.onclick = () => openCredentialDocument(button));
        return row;
    }));
}

async function openCredentialDocument(button) {
    button.disabled = true;
    try {
        window.open(button.dataset.credentialPath, "_blank", "noopener");
    } catch (error) {
        $("adminStatus").textContent = `Could not open credential document: ${error.message}`;
    } finally { button.disabled = false; }
}

async function reviewInterpreter(interpreterId, status) {
    $("adminStatus").textContent = status === "verified" ? "Approving interpreter…" : "Returning profile for changes…";
    try {
        await apiFetch(`/api/admin/interpreters/${encodeURIComponent(interpreterId)}/verification`, {
            method: "PATCH", body: JSON.stringify({ status })
        });
        $("adminStatus").textContent = status === "verified" ? "Interpreter approved and published." : "Interpreter was asked to update their credentials.";
        await loadAdminDashboard();
    } catch (error) {
        $("adminStatus").textContent = `Could not update verification: ${error.message}`;
    }
}

function selectInterpreterForCall(profile) {
    selectedInterpreterProfile = profile?.id ? profile : null;
    renderSelectedInterpreter();
}

function clearSelectedInterpreter() {
    selectedInterpreterProfile = null;
    renderSelectedInterpreter();
}

function renderSelectedInterpreter() {
    const selected = $("selectedInterpreter");
    if (!selected) return;
    const hasSelection = Boolean(selectedInterpreterProfile?.id);
    selected.classList.toggle("hidden", !hasSelection);
    $("selectedInterpreterName").textContent = hasSelection
        ? selectedInterpreterProfile.displayName || "FiniSpeak interpreter"
        : "";
    $("callFormHelp").textContent = hasSelection
        ? "Dial the other customer, or choose a friend. Your selected interpreter will be requested when the call starts."
        : "Dial another FiniSpeak customer, or choose a friend. You can request an interpreter after the call starts.";
}

function setCallFormStatus(message = "", isError = false) {
    const status = $("callFormStatus");
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("error", Boolean(message) && isError);
}

function requireMediaCapture() {
    if (window.isSecureContext && typeof navigator.mediaDevices?.getUserMedia === "function") return;
    const error = new Error(
        "Camera and microphone access is blocked on this HTTP address. For isolated testing, connect through the documented SSH tunnel and open http://localhost:8080. Public calls require HTTPS."
    );
    error.code = "MEDIA_CAPTURE_REQUIRES_SECURE_CONTEXT";
    throw error;
}

async function fetchPublicProfiles() {
    const response = await fetch("/api/translators/");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Could not load interpreter profiles");
    return payload.filter(profile => profile.displayName);
}

async function loadFeaturedProfiles() {
    const container = $("featuredInterpreters");
    try {
        featuredProfilesData = await fetchPublicProfiles();
        featuredProfilesData.sort((a, b) => Number(b.rating || 0) - Number(a.rating || 0) || Number(b.ratingCount || 0) - Number(a.ratingCount || 0));
        hydrateHeroProfiles();
        hydrateFeaturedFilters();
        filterFeaturedProfiles();
    } catch (error) {
        console.error("Featured profiles failed:", error);
        $("featuredResultCount").textContent = "Directory unavailable";
        $("featuredAvailableCount").textContent = "Availability unavailable";
        container.innerHTML = '<div class="directory-empty">Featured profiles are temporarily unavailable.</div>';
    }
}

function hydrateHeroProfiles() {
    const slots = [
        { prefix: "heroPrimary", profile: featuredProfilesData[0] },
        { prefix: "heroSecondary", profile: featuredProfilesData[1] }
    ];
    slots.forEach(({ prefix, profile }) => {
        const card = $(`${prefix}Profile`);
        card.hidden = !profile;
        card.disabled = !profile;
        if (!profile) return;

        const language = (profile.languages || [])[0];
        const specialty = (profile.specialties || [])[0];
        $(`${prefix}Name`).textContent = profile.displayName || "FiniSpeak interpreter";
        $(`${prefix}Summary`).textContent = [language, specialty].filter(Boolean).join(" · ") || "Professional interpreter";
        $(`${prefix}Verified`).hidden = profileVerificationLabel(profile) !== "Verified";
        setProfileAvatar($(`${prefix}Avatar`), profile);
        card.setAttribute("aria-label", `View ${profile.displayName || "interpreter"}'s public profile`);
        card.onclick = () => openPublicProfile(profile);
    });

    const primary = featuredProfilesData[0];
    $("heroPrimaryDetails").hidden = !primary;
    if (!primary) return;
    const rating = Number(primary.rating || 0);
    const years = Number(primary.yearsExperience || 0);
    $("heroPrimaryRegion").textContent = (primary.dialects || [])[0] || (primary.languages || [])[0] || "Language specialist";
    $("heroPrimaryRating").textContent = rating ? `${rating.toFixed(1)} rating` : "New profile";
    $("heroPrimaryExperience").textContent = `${years} year${years === 1 ? "" : "s"}`;
}

function hydrateFeaturedFilters() {
    const populate = (element, values) => {
        const current = element.value;
        element.replaceChildren(element.options[0], ...values.map(value => {
            const option = document.createElement("option");
            option.value = value;
            option.textContent = value;
            return option;
        }));
        element.value = current;
    };
    const languages = [...new Set(featuredProfilesData.flatMap(profile => profile.languages || []).filter(Boolean))].sort((a, b) => a.localeCompare(b));
    const specialties = [...new Set(featuredProfilesData.flatMap(profile => profile.specialties || []).filter(Boolean))].sort((a, b) => a.localeCompare(b));
    populate($("featuredLanguage"), languages);
    populate($("featuredSpecialty"), specialties);
    const available = featuredProfilesData.filter(profile => profile.availability?.availableNow).length;
    $("featuredAvailableCount").textContent = `${available} interpreter${available === 1 ? "" : "s"} available now`;
}

function filterFeaturedProfiles() {
    const search = normalizeTaxonomyValue($("featuredSearch").value || "");
    const language = normalizeTaxonomyValue($("featuredLanguage").value || "");
    const specialty = normalizeTaxonomyValue($("featuredSpecialty").value || "");
    const availableOnly = $("featuredAvailable").checked;
    const profiles = featuredProfilesData.filter(profile => {
        const searchable = [
            profile.displayName, profile.bio,
            ...(profile.languages || []), ...(profile.dialects || []), ...(profile.specialties || [])
        ].filter(Boolean).join(" ").toLocaleLowerCase();
        const languages = (profile.languages || []).map(normalizeTaxonomyValue);
        const specialties = (profile.specialties || []).map(normalizeTaxonomyValue);
        return (!search || searchable.includes(search))
            && (!language || languages.includes(language))
            && (!specialty || specialties.includes(specialty))
            && (!availableOnly || Boolean(profile.availability?.availableNow));
    });
    $("featuredResultCount").textContent = `${profiles.length} interpreter${profiles.length === 1 ? "" : "s"} found`;
    renderFeaturedProfiles(profiles);
}

function clearFeaturedFilters() {
    $("featuredSearch").value = "";
    $("featuredLanguage").value = "";
    $("featuredSpecialty").value = "";
    $("featuredAvailable").checked = false;
    filterFeaturedProfiles();
    $("featuredSearch").focus();
}

function renderFeaturedProfiles(profiles) {
    const container = $("featuredInterpreters");
    if (!profiles.length) {
        container.innerHTML = '<div class="directory-empty"><div><strong>No exact matches yet.</strong><p>Try a different language, specialty, or availability filter.</p></div></div>';
        return;
    }
    container.replaceChildren(...profiles.map(profile => {
        const card = document.createElement("button");
        card.type = "button";
        card.className = "concept-person-card landing-profile-card";
        card.setAttribute("aria-label", `View ${profile.displayName || "interpreter"}'s public profile`);
        const languages = [...(profile.languages || []), ...(profile.dialects || [])].slice(0, 2);
        const specialties = (profile.specialties || []).slice(0, 2);
        const tags = [...languages, ...specialties];
        const available = Boolean(profile.availability?.availableNow);
        const verified = profileVerificationLabel(profile) === "Verified";
        card.innerHTML = `
            <div class="concept-avatar">${escapeHtml(profileInitials(profile.displayName))}</div>
            <div class="concept-person-copy">
                <strong>${escapeHtml(profile.displayName || "Interpreter")}</strong>
                <div class="concept-stars">${"★".repeat(Math.max(1, Math.round(Number(profile.rating || 0) || 5)))} <span>${available ? "Available" : "View schedule"}</span></div>
                <small>${escapeHtml(tags.join(" · ") || "Professional interpreter")}</small>
            </div>
            ${verified ? '<span class="concept-verified">Verified</span>' : ""}`;
        setProfileAvatar(card.querySelector(".concept-avatar"), profile);
        card.onclick = () => openPublicProfile(profile);
        return card;
    }));
}

async function loadInterpreterDirectory() {
    const container = $("interpreterDirectory");
    container.innerHTML = '<div class="directory-loading"><span class="button-spinner" aria-hidden="true"></span>Loading profiles…</div>';
    $("directoryResultCount").textContent = "Loading interpreters…";
    try {
        directoryProfiles = await fetchDirectoryProfiles();
        hydrateDirectoryFilterOptions();
        filterInterpreterDirectory();
    } catch (error) {
        console.error("Interpreter directory failed:", error);
        $("directoryResultCount").textContent = "Directory unavailable";
        container.innerHTML = `<div class="directory-empty">Could not load interpreter profiles: ${escapeHtml(error.message)}</div>`;
    }
}

async function fetchDirectoryProfiles() {
    const params = new URLSearchParams({
        mode: $("directoryMode").value,
        radius: $("directoryRadius").value,
        minimumRating: $("directoryRating").value,
        limit: "100"
    });
    if ($("directoryLanguage").value) params.set("language", $("directoryLanguage").value);
    if ($("directoryDialect").value) params.set("dialect", $("directoryDialect").value);
    if ($("directorySpecialty").value) params.set("specialty", $("directorySpecialty").value);
    if ($("directoryAvailable").checked) params.set("available", "now");
    if ($("directoryVerified").checked) params.set("verified", "true");
    if (directoryOrigin) {
        params.set("latitude", String(directoryOrigin.latitude));
        params.set("longitude", String(directoryOrigin.longitude));
    } else if ($("directoryRadius").value !== "anywhere" && $("directoryMode").value !== "remote") {
        params.delete("radius");
    }
    let response = await fetch(`/api/discovery?${params}`);
    let payload = await response.json().catch(() => ({}));
    if (!response.ok && directoryOrigin && $("directoryMode").value === "both") {
        const remoteParams = new URLSearchParams(params);
        remoteParams.set("mode", "remote");
        remoteParams.delete("latitude");
        remoteParams.delete("longitude");
        remoteParams.delete("radius");
        response = await fetch(`/api/discovery?${remoteParams}`);
        payload = await response.json().catch(() => ({}));
        if (response.ok) payload.locationSearchUnavailable = true;
    }
    if (!response.ok) throw new Error(payload.error || "Could not search interpreter profiles");
    $("directoryLocationStatus").textContent = payload.remoteFallback
        ? "No nearby interpreters matched, so remote video interpreters are shown."
        : payload.locationSearchUnavailable
            ? "Nearby search is temporarily unavailable, so remote video interpreters are shown."
        : (directoryOrigin?.label || "Location is optional for remote search.");
    return (payload.interpreters || []).filter(profile => profile.displayName);
}

function hydrateDirectoryFilterOptions() {
    const fill = (id, values) => {
        const select = $(id), current = select.value, first = select.options[0];
        select.replaceChildren(first, ...[...new Set(values.filter(Boolean))].sort((a,b) => a.localeCompare(b)).map(value => {
            const option = document.createElement("option"); option.value = value; option.textContent = value; return option;
        }));
        select.value = current;
    };
    fill("directoryLanguage", directoryProfiles.flatMap(profile => profile.languages || []));
    fill("directoryDialect", directoryProfiles.flatMap(profile => profile.dialects || []));
    fill("directorySpecialty", directoryProfiles.flatMap(profile => profile.specialties || []));
}

async function refreshInterpreterDirectory() {
    $("interpreterDirectory").innerHTML = '<div class="directory-loading"><span class="button-spinner" aria-hidden="true"></span>Updating results…</div>';
    try {
        directoryProfiles = await fetchDirectoryProfiles();
        hydrateDirectoryFilterOptions();
        filterInterpreterDirectory();
    } catch (error) {
        $("directoryResultCount").textContent = "Search unavailable";
        $("interpreterDirectory").innerHTML = `<div class="directory-empty">${escapeHtml(error.message)}</div>`;
    }
}

function filterInterpreterDirectory() {
    const search = normalizeTaxonomyValue($("directorySearch").value || "");
    const minimumRating = Number($("directoryRating").value || 0);
    const availableOnly = $("directoryAvailable").checked;
    const sort = $("directorySort").value;
    const profiles = directoryProfiles.filter(profile => {
        const searchable = [
            profile.displayName, profile.bio,
            ...(profile.languages || []), ...(profile.dialects || []), ...(profile.specialties || [])
        ].filter(Boolean).join(" ").toLocaleLowerCase();
        const matchesSearch = !search || searchable.includes(search);
        const matchesRating = Number(profile.rating || 0) >= minimumRating;
        const matchesAvailability = !availableOnly || Boolean(profile.availability?.availableNow);
        return matchesSearch && matchesRating && matchesAvailability;
    });

    profiles.sort((a, b) => {
        if (sort === "experience") return Number(b.yearsExperience || 0) - Number(a.yearsExperience || 0);
        if (sort === "name") return String(a.displayName || "").localeCompare(String(b.displayName || ""));
        return Number(b.rating || 0) - Number(a.rating || 0) || Number(b.ratingCount || 0) - Number(a.ratingCount || 0);
    });
    filteredDirectoryProfiles = profiles;
    renderInterpreterDirectory(profiles);
    renderDirectoryMap(profiles);
}

function renderInterpreterDirectory(profiles) {
    const container = $("interpreterDirectory");
    $("directoryResultCount").textContent = `${profiles.length} interpreter${profiles.length === 1 ? "" : "s"} found`;
    if (!profiles.length) {
        container.innerHTML = '<div class="directory-empty">No profiles match these filters. Try broadening your search.</div>';
        return;
    }
    container.replaceChildren(...profiles.map(profile => {
        const card = document.createElement("button");
        card.type = "button";
        card.className = "interpreter-card";
        card.dataset.interpreterId = profile.id;
        card.setAttribute("aria-label", `Select ${profile.displayName} and view their interpreter profile`);
        const languages = [...(profile.languages || []), ...(profile.dialects || [])].slice(0, 3);
        const specialties = (profile.specialties || []).slice(0, 2);
        const tags = [...languages, ...specialties];
        card.innerHTML = `
            <div class="directory-avatar">${escapeHtml(profileInitials(profile.displayName))}</div>
            <div>
                <div class="interpreter-card-header"><div><h3>${escapeHtml(profile.displayName)}</h3>${ratingMarkup(profile.rating, profile.ratingCount)}</div><span class="availability-dot${profile.availability?.availableNow ? " available" : ""}" title="${profile.availability?.availableNow ? "Available now" : "Currently unavailable"}"></span></div>
                <p class="card-bio">${escapeHtml(profile.bio || "Professional FiniSpeak interpreter profile.")}</p>
                <div class="directory-tags">${tags.map(tag => `<span class="directory-tag">${escapeHtml(tag)}</span>`).join("")}</div>
                <div class="directory-meta"><span>${Number(profile.yearsExperience || 0)} years experience</span><span>${escapeHtml((profile.verificationStatus || "unverified").replace(/_/g, " "))}</span>${profile.distanceMiles != null ? `<span>${Number(profile.distanceMiles).toFixed(1)} miles away</span>` : ""}<span>${profile.serviceOptions?.remote ? "Remote" : "In person"}</span></div>
            </div>`;
        setProfileAvatar(card.querySelector(".directory-avatar"), profile);
        card.onclick = () => selectDirectoryProfile(profile, true);
        return card;
    }));
    renderConceptMapSheet(profiles[0]);
}

function selectDirectoryProfile(profile, openProfile = false) {
    document.querySelectorAll(".interpreter-card.selected").forEach(card => card.classList.remove("selected"));
    document.querySelector(`.interpreter-card[data-interpreter-id="${CSS.escape(profile.id)}"]`)?.classList.add("selected");
    const marker = directoryMarkers.get(profile.id);
    if (marker && directoryMap) {
        directoryMap.panTo(marker.getLatLng());
        marker.openPopup();
    }
    renderConceptMapSheet(profile);
    if (openProfile && directoryView === "list") openPublicProfile(profile);
}

function setDirectoryView(view) {
    directoryView = view;
    const layout = $("directoryResultsLayout");
    layout.className = `directory-results-layout ${view}-view`;
    $("interpreterDirectory").classList.toggle("hidden", view === "map");
    $("interpreterMapPanel").classList.toggle("hidden", view === "list");
    [["directoryListView", "list"], ["directoryMapView", "map"], ["directorySplitView", "split"]].forEach(([id, value]) => {
        $(id).classList.toggle("active", view === value); $(id).setAttribute("aria-pressed", String(view === value));
    });
    if (view !== "list") {
        initializeDirectoryMap();
        window.setTimeout(() => { directoryMap.invalidateSize(); renderDirectoryMap(filteredDirectoryProfiles, true); }, 0);
    }
}

function initializeDirectoryMap() {
    if (directoryMap || !window.L) return;
    directoryMap = L.map("interpreterMap", { scrollWheelZoom: false }).setView([39.8, -98.6], 4);
    const tileUrl = document.documentElement.dataset.mapTileUrl || "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
    const attribution = document.documentElement.dataset.mapAttribution || '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
    L.tileLayer(tileUrl, { maxZoom: 19, attribution }).addTo(directoryMap);
    directoryMarkerLayer = L.markerClusterGroup ? L.markerClusterGroup({ showCoverageOnHover: false }) : L.layerGroup();
    directoryMarkerLayer.addTo(directoryMap);
    directoryMap.on("moveend", () => $("searchMapArea").classList.remove("hidden"));
    requestAnimationFrame(() => directoryMap?.invalidateSize({ pan: false }));
}

function renderDirectoryMap(profiles, fitToResults = false) {
    if (!directoryMap || !directoryMarkerLayer) return;
    directoryMap.invalidateSize({ pan: false });
    directoryMarkerLayer.clearLayers(); directoryMarkers.clear();
    const bounds = [];
    profiles.forEach(profile => {
        const location = profile.serviceLocation;
        if (!location?.showOnMap || location.latitude == null || location.longitude == null) return;
        const available = Boolean(profile.availability?.availableNow);
        const marker = L.marker([location.latitude, location.longitude], { icon: interpreterMarkerIcon(profile) });
        const distance = profile.distanceMiles != null ? `${Number(profile.distanceMiles).toFixed(1)} miles away` : "Distance available after choosing your location";
        const photoUrl = safeProfilePhotoUrl(profile.photoUrl);
        const photo = photoUrl ? `<img alt="">` : `<span class="map-popup-avatar" aria-hidden="true">${escapeHtml(profileInitials(profile.displayName))}</span>`;
        const popupContent = document.createElement("article");
        popupContent.className = "map-profile-popup";
        popupContent.innerHTML = `<header>${photo}<strong>${escapeHtml(profile.displayName)}</strong></header><span>${escapeHtml([...(profile.languages || []), ...(profile.dialects || [])].slice(0,3).join(" · "))}</span><span>${escapeHtml((profile.specialties || []).slice(0,2).join(" · "))}</span><span>${Number(profile.yearsExperience || 0)} years · ${Number(profile.rating || 0).toFixed(1)} ★ (${Number(profile.ratingCount || 0)})</span><span>${escapeHtml(profile.verificationStatus === "verified" ? "Verified" : "")}${available ? " · Available now" : ""}</span><span>${escapeHtml(distance)}</span><div><button type="button" data-map-profile="${escapeHtml(profile.id)}">View profile</button></div>`;
        popupContent.querySelector("[data-map-profile]").onclick = event => {
            event.preventDefault(); event.stopPropagation();
            marker.closePopup();
            openPublicProfile(profile);
        };
        const popupImage = popupContent.querySelector("img");
        if (popupImage) {
            popupImage.onerror = () => {
                const fallback = document.createElement("span");
                fallback.className = "map-popup-avatar";
                fallback.setAttribute("aria-hidden", "true");
                fallback.textContent = profileInitials(profile.displayName);
                popupImage.replaceWith(fallback);
            };
            popupImage.src = photoUrl;
        }
        marker.bindPopup(popupContent);
        marker.on("click", () => selectDirectoryProfile(profile));
        directoryMarkers.set(profile.id, marker); directoryMarkerLayer.addLayer(marker); bounds.push([location.latitude, location.longitude]);
    });
    const mappedCount = directoryMarkers.size;
    $("interpreterMapStatus").textContent = mappedCount
        ? `${mappedCount} mapped interpreter${mappedCount === 1 ? "" : "s"}. Zoom or pan to explore other areas.`
        : "No matching interpreters have shared an approximate public area yet.";
    if (directoryUserMarker) {
        directoryMap.removeLayer(directoryUserMarker);
        directoryUserMarker = null;
    }
    if (directoryOrigin) {
        directoryUserMarker = L.circleMarker([directoryOrigin.latitude, directoryOrigin.longitude], { radius: 8, color: "#fff", weight: 3, fillColor: "#2563eb", fillOpacity: 1 }).addTo(directoryMap).bindTooltip("Your approximate location");
        bounds.push([directoryOrigin.latitude, directoryOrigin.longitude]);
    }
    if (fitToResults && bounds.length) directoryMap.fitBounds(bounds, { padding: [35, 35], maxZoom: 11 });
}

async function showAllMappedTranslators() {
    directoryOrigin = null;
    $("directoryMode").value = "both";
    $("directoryRadius").value = "anywhere";
    $("directoryLocationStatus").textContent = "Showing every interpreter who shared an approximate public area.";
    await refreshInterpreterDirectory();
    setDirectoryView("map");
    renderDirectoryMap(filteredDirectoryProfiles, true);
}

function useDirectoryLocation() {
    const status = $("directoryLocationStatus");
    if (!navigator.geolocation) { status.textContent = "Location is not supported here. Enter a city, state, or ZIP instead."; return; }
    status.textContent = "Requesting your location…";
    navigator.geolocation.getCurrentPosition(async position => {
        directoryOrigin = { latitude: position.coords.latitude, longitude: position.coords.longitude, label: "Using your approximate current location." };
        status.textContent = directoryOrigin.label;
        await refreshInterpreterDirectory(); setDirectoryView("map");
    }, error => {
        status.textContent = error.code === 1 ? "Location permission was denied. Enter a city, state, or ZIP instead." : "Could not determine your location. Enter it manually instead.";
        $("manualLocation").focus();
    }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
}

async function useManualDirectoryLocation(event) {
    event.preventDefault();
    const status = $("directoryLocationStatus"), query = $("manualLocation").value.trim();
    if (!query) return;
    status.textContent = "Finding that area…";
    try {
        const response = await fetch(`/api/discovery/geocode?q=${encodeURIComponent(query)}`), payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Location not found");
        directoryOrigin = { ...payload.location, label: `Searching near ${payload.location.label}.` };
        await refreshInterpreterDirectory(); setDirectoryView("map");
    } catch (error) { status.textContent = error.message; }
}

async function searchCurrentMapArea() {
    if (!directoryMap) return;
    const center = directoryMap.getCenter();
    directoryOrigin = { latitude: center.lat, longitude: center.lng, label: "Searching the visible map area." };
    $("searchMapArea").classList.add("hidden");
    await refreshInterpreterDirectory();
}

function closePublicProfile() {
    if (!currentUser) {
        show("heroView");
        loadFeaturedProfiles();
        window.requestAnimationFrame(() => $("featuredProfiles")?.scrollIntoView({ behavior: "smooth", block: "start" }));
        return;
    }
    const panel = profileReturnPanel || "directory";
    if (dashboardHistory[dashboardHistory.length - 1] !== panel) {
        dashboardHistory = nextDashboardHistory(dashboardHistory, panel, "push");
    }
    show("dashboardView");
    openDashboardPanel(panel, "back");
}

async function openPublicProfile(profile) {
    activeDirectoryProfile = profile;
    profileReturnPanel = dashboardHistory[dashboardHistory.length - 1] || "directory";
    const backLabel = $("backToDirectory")?.querySelector("span");
    if (backLabel) backLabel.textContent = currentUser ? "Back" : "Back to interpreters";
    const available = Boolean(profile.availability?.availableNow);
    $("publicProfileName").textContent = profile.displayName || "Interpreter";
    const specialtyLine = (profile.specialties || []).filter(Boolean).slice(0, 2).join(", ");
    $("publicProfileHeadline").textContent = specialtyLine || (profile.languages || []).filter(Boolean).slice(0, 2).join(", ") || "Professional interpreter";
    const verifiedMark = $("publicProfileVerified");
    if (verifiedMark) {
        const verified = profile.verificationStatus === "verified";
        verifiedMark.hidden = !verified;
        verifiedMark.classList.toggle("hidden", !verified);
    }
    $("publicProfileAvailability").textContent = available ? "Available now" : "Currently unavailable";
    $("publicProfileAvailability").classList.toggle("available", available);
    $("publicProfileRating").innerHTML = ratingMarkup(profile.rating, profile.ratingCount, false);
    $("publicProfileBio").textContent = profile.bio || "This interpreter has not added a professional bio yet.";
    setProfileAvatar($("publicProfileAvatar"), profile);
    setProfileAvatar($("publicProfileSlotAvatar"), profile);
    renderProfileTags($("publicProfileLanguages"), "Languages", [...(profile.languages || []), ...(profile.dialects || [])]);
    renderProfileTags($("publicProfileSpecialties"), "Specialties", profile.specialties || []);
    $("publicProfileExperience").textContent = `${Number(profile.yearsExperience || 0)} years`;
    $("publicProfileCredentials").textContent = (profile.credentials || []).join(", ") || "Not listed";
    const serviceLocation = profile.serviceLocation || {};
    const publicArea = [serviceLocation.city, serviceLocation.state, serviceLocation.country].filter(Boolean).join(", ");
    $("publicProfileLocation").textContent = publicArea
        ? `${publicArea}${profile.serviceOptions?.inPerson ? ` · within ${Number(profile.serviceOptions.radiusMiles || 25)} miles` : " · Remote service"}`
        : "Remote video";
    $("publicProfileVerification").textContent = profileVerificationLabel(profile);
    const scheduleText = formatAvailabilitySchedule(profile.availability, "Schedule not listed");
    $("publicProfileSchedule").textContent = `${available ? "Available now" : "Not available now"} · ${scheduleText}`;
    $("publicProfileReviewSummary").innerHTML = ratingMarkup(profile.rating, profile.ratingCount);
    renderProfileReviews(Array.isArray(profile.recentReviews) ? profile.recentReviews : []);
    renderConceptProfile(profile);
    const viewerIsInterpreter = isInterpreterRole(currentProfile?.role);
    ["conceptRequestCall", "profileChatTranslator", "profileStartCall"].forEach(id => {
        $(id)?.classList.toggle("hidden", viewerIsInterpreter);
    });
    if ($("profileCallStatus") && !viewerIsInterpreter) $("profileCallStatus").textContent = "";
    show("profileView");
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderProfileTags(container, label, values) {
    const cleanValues = values.filter(Boolean);
    container.innerHTML = `<strong>${escapeHtml(label)}</strong>${cleanValues.length ? cleanValues.map(value => `<span class="profile-tag">${escapeHtml(value)}</span>`).join("") : '<span class="profile-tag">Not listed</span>'}`;
}

function profileVerificationLabel(profile = {}) {
    const verificationStatus = profile.verificationStatus || "unverified";
    if (verificationStatus === "verified") return "Verified";
    if (profile.credentialStatus === "submitted") return "Submitted for verification";
    return verificationStatus.replace(/_/g, " ").replace(/^./, value => value.toUpperCase());
}

function formatAvailabilityTime(value) {
    const [hourText, minuteText] = String(value || "").split(":");
    const hour = Number(hourText);
    if (!Number.isInteger(hour) || hour < 0 || hour > 23 || !/^\d{2}$/.test(minuteText || "")) return value || "";
    const suffix = hour >= 12 ? "PM" : "AM";
    return `${hour % 12 || 12}:${minuteText} ${suffix}`;
}

function formatAvailabilitySchedule(availability = {}, fallback = "Add your availability schedule.") {
    const days = Array.isArray(availability?.days) ? availability.days.filter(Boolean) : [];
    if (!days.length) return fallback;
    const dayLabel = days.map(day => day.slice(0, 3).replace(/^./, value => value.toUpperCase())).join(", ");
    const timeLabel = availability.start && availability.end
        ? ` · ${formatAvailabilityTime(availability.start)}–${formatAvailabilityTime(availability.end)}`
        : "";
    return `${dayLabel}${timeLabel}`;
}

function renderProfileReviews(reviews) {
    const container = $("publicProfileReviews");
    if (!reviews.length) {
        container.innerHTML = "<p>No reviews yet. Completed customer reviews will appear here.</p>";
        return;
    }
    container.innerHTML = reviews.map(review => {
        const date = timestampDate(review.createdAt);
        return `<article class="review-card"><div class="review-card-header"><div><strong>${escapeHtml(review.authorName || "FiniSpeak customer")}</strong><small>${escapeHtml(date ? date.toLocaleDateString() : "Recent review")}</small></div>${ratingMarkup(review.rating, 0, false)}</div><p>${escapeHtml(review.text || review.comment || "")}</p></article>`;
    }).join("");
}

function ratingMarkup(rating, count = 0, includeCount = true) {
    const value = Number(rating || 0);
    const filled = value ? Math.max(1, Math.min(5, Math.round(value))) : 0;
    const stars = `${"★".repeat(filled)}${"☆".repeat(5 - filled)}`;
    const countText = includeCount ? ` <span>(${Number(count || 0)} review${Number(count || 0) === 1 ? "" : "s"})</span>` : "";
    return `<div class="profile-rating" aria-label="${value ? `${value.toFixed(1)} out of 5 stars` : "Not yet rated"}"><span class="rating-stars" aria-hidden="true">${stars}</span><span class="rating-value">${value ? value.toFixed(1) : "New"}</span>${countText}</div>`;
}

function safeProfilePhotoUrl(url) {
    // Uploaded photos are same-origin file paths. Older profiles may still
    // point at a public https image. Anything else stays on the initials.
    const value = String(url || "").trim();
    if (/^\/api\/files\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/content$/i.test(value)) return value;
    let parsed;
    try { parsed = new URL(value); } catch (_) { return ""; }
    if (parsed.username || parsed.password || parsed.protocol !== "https:") return "";
    if (/[\s"'\\<>()]/.test(parsed.href)) return "";
    return parsed.href;
}

let avatarRequestSerial = 0;
const callFacePhotos = new Map();
const callFacePhotoRequests = new Set();

function rememberCallFacePhoto(id, name, photoUrl) {
    const safe = safeProfilePhotoUrl(photoUrl);
    if (!safe) return "";
    if (id) callFacePhotos.set(`id:${id}`, safe);
    const normalized = String(name || "").trim().toLocaleLowerCase();
    if (normalized) callFacePhotos.set(`name:${normalized}`, safe);
    return safe;
}

function lookupCallFacePhoto(person) {
    if (!person) return "";
    const id = person.id || person.uid || "";
    const name = String(person.displayName || "").trim().toLocaleLowerCase();
    const direct = rememberCallFacePhoto(id, person.displayName, person.photoUrl);
    if (direct) return direct;
    if (id && callFacePhotos.has(`id:${id}`)) return callFacePhotos.get(`id:${id}`);
    if (name && callFacePhotos.has(`name:${name}`)) return callFacePhotos.get(`name:${name}`);
    const profiles = [currentInterpreterProfile, currentProfile, selectedInterpreterProfile, activeDirectoryProfile, ...directoryProfiles];
    interpreterProfileCache.forEach(profile => profiles.push(profile));
    for (const profile of profiles) {
        if (!profile) continue;
        const profileId = profile.id || profile.uid || "";
        const profileName = String(profile.displayName || "").trim().toLocaleLowerCase();
        if ((id && profileId === id) || (name && profileName && profileName === name)) {
            const saved = rememberCallFacePhoto(profileId || id, profile.displayName || person.displayName, profile.photoUrl);
            if (saved) return saved;
        }
    }
    return "";
}

function ensureCallFacePhoto(person) {
    const id = person?.id || person?.uid || "";
    if (!id || lookupCallFacePhoto(person) || callFacePhotoRequests.has(id)) return;
    callFacePhotoRequests.add(id);
    apiFetch(`/api/translators/${encodeURIComponent(id)}`).then(profile => {
        if (profile) interpreterProfileCache.set(id, profile);
        rememberCallFacePhoto(id, profile?.displayName || person.displayName, profile?.photoUrl);
        syncAudioCallFaces();
    }).catch(() => {});
}

function setProfileAvatar(element, profile) {
    if (!element) return;
    const id = profile?.id || profile?.uid || "";
    const faceId = id || String(profile?.displayName || "");
    const initials = profileInitials(profile?.displayName);
    const photoUrl = lookupCallFacePhoto(profile);
    if (!photoUrl && element.dataset.faceId === faceId && element.classList.contains("has-photo")) return;
    if (photoUrl && element.dataset.photoFailed === photoUrl && element.dataset.faceId === faceId && element.dataset.avatarReady === "1") return;
    if (element.dataset.faceId === faceId && element.dataset.photoUrl === (photoUrl || "") && element.dataset.avatarReady === "1") return;
    element.dataset.faceId = faceId;
    element.dataset.photoUrl = photoUrl || "";
    element.dataset.avatarReady = "1";
    if (!photoUrl || element.dataset.photoFailed === photoUrl) {
        element.textContent = initials;
        element.style.backgroundImage = "";
        element.classList.remove("has-photo");
        return;
    }
    element.style.backgroundImage = `url("${photoUrl}")`;
    element.style.backgroundSize = "cover";
    element.style.backgroundPosition = "center";
    element.style.backgroundRepeat = "no-repeat";
    element.textContent = "";
    element.classList.add("has-photo");
    const requestId = String(++avatarRequestSerial);
    element.dataset.avatarRequest = requestId;
    const image = new Image();
    image.onload = () => {
        if (element.dataset.avatarRequest !== requestId) return;
        element.classList.add("has-photo");
        delete element.dataset.photoFailed;
    };
    image.onerror = () => {
        if (element.dataset.avatarRequest !== requestId) return;
        element.dataset.photoFailed = photoUrl;
        element.dataset.photoUrl = "";
        element.dataset.avatarReady = "";
        element.textContent = initials;
        element.style.backgroundImage = "";
        element.classList.remove("has-photo");
    };
    image.src = photoUrl;
}

function interpreterMarkerIcon(profile) {
    const available = Boolean(profile?.availability?.availableNow);
    const photoUrl = safeProfilePhotoUrl(profile?.photoUrl);
    const state = available ? "available" : "unavailable";
    const photoStyle = photoUrl ? ` style="--marker-photo:url('${photoUrl}')"` : "";
    return L.divIcon({
        className: "interpreter-map-marker-wrap",
        html: `<span class="interpreter-map-marker ${state}${photoUrl ? " has-photo" : ""}"${photoStyle} aria-hidden="true"></span>`,
        iconSize: photoUrl ? [42, 42] : [28, 38],
        iconAnchor: photoUrl ? [21, 50] : [14, 38]
    });
}

function profileInitials(name = "") {
    return name.split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join("").toUpperCase() || "FS";
}

function normalizePhoneNumber(value = "") {
    const digits = String(value).replace(/\D/g, "");
    if (!digits) return "";
    if (digits.length < 7 || digits.length > 15) throw new Error("Enter a valid phone number with 7 to 15 digits.");
    return digits;
}

function initializePhoneFields() {
    document.querySelectorAll("[data-phone-country]").forEach(select => {
        const options = phoneCountries.map(([iso, name, code]) => {
            const option = document.createElement("option");
            option.value = code;
            option.dataset.country = iso;
            option.textContent = `${countryFlag(iso)} ${iso} ${code}`;
            option.title = `${name} (${code})`;
            return option;
        });
        select.replaceChildren(...options);
        select.value = "+1";
    });
}

function countryFlag(iso) {
    return [...iso.toUpperCase()].map(character => String.fromCodePoint(127397 + character.charCodeAt(0))).join("");
}

function completePhoneNumber(inputId) {
    const input = $(inputId);
    const raw = input.value.trim();
    if (!raw) return "";
    if (raw.startsWith("+")) return `+${normalizePhoneNumber(raw)}`;
    const countryCode = $(`${inputId}Country`).value;
    let nationalDigits = normalizePhoneNumber(raw);
    if (countryCode !== "+39") nationalDigits = nationalDigits.replace(/^0/, "");
    return `${countryCode}${nationalDigits}`;
}

function setPhoneFieldValue(inputId, value = "") {
    const input = $(inputId), select = $(`${inputId}Country`), raw = String(value || "").trim();
    if (!raw) { input.value = ""; return; }
    const digits = raw.replace(/\D/g, "");
    if (!raw.startsWith("+")) { input.value = raw; return; }
    const codes = [...new Set(phoneCountries.map(([, , code]) => code))].sort((a, b) => b.length - a.length);
    const matchedCode = codes.find(code => digits.startsWith(code.slice(1))) || "+1";
    select.value = matchedCode;
    input.value = digits.slice(matchedCode.length - 1);
}

function profileTimestampMillis(value) {
    if (!value) return 0;
    if (typeof value.toMillis === "function") return value.toMillis();
    if (typeof value === "number") return value;
    const parsed = new Date(value).getTime();
    return Number.isFinite(parsed) ? parsed : 0;
}

function timestampDate(value) {
    if (!value) return null;
    if (typeof value.toDate === "function") return value.toDate();
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
}

function latestReviewMillis(profile) {
    if (profile.latestReviewAt) return profileTimestampMillis(profile.latestReviewAt);
    return Math.max(0, ...(profile.recentReviews || []).map(review => profileTimestampMillis(review.createdAt)));
}

async function saveProfile(e) {
    e.preventDefault();
    const status = $("profileStatus");
    const displayName = $("profileDisplayName").value.trim();
    const phone = completePhoneNumber("profilePhone");
    if (!displayName) { status.textContent = "Enter a display name."; return; }
    status.textContent = "Saving…";
    try {
        const phoneNormalized = normalizePhoneNumber(phone);
        const serviceArea = $("profileServiceArea").value.trim();
        const existingLocation = currentProfile.profileLocation || currentInterpreterProfile?.serviceLocation || {};
        const savedArea = [existingLocation.city, existingLocation.state, existingLocation.country].filter(Boolean).join(", ");
        let profileLocation = serviceArea ? existingLocation : {};
        if (serviceArea && (serviceArea !== savedArea || !existingLocation.geohash)) {
            const geocodeResponse = await fetch(`/api/discovery/geocode?q=${encodeURIComponent(serviceArea)}`);
            const geocodePayload = await geocodeResponse.json().catch(() => ({}));
            if (!geocodeResponse.ok) throw new Error(geocodePayload.error || "Could not locate that public area.");
            profileLocation = geocodePayload.location;
        }
        if (serviceArea) profileLocation = { ...profileLocation, showOnMap: $("profileShowOnMap").checked };
        const result = await apiFetch("/api/accounts/me", { method: "PATCH", body: JSON.stringify({ displayName, phone, profileLocation }) });
        currentProfile = { ...currentProfile, ...(result.account || {}), displayName, phone, phoneNormalized, profileLocation };
        hydrateDashboardProfile();
        status.textContent = "Profile saved.";
    } catch (error) { status.textContent = `Could not save profile: ${error.message}`; }
}


function splitList(value) {
    return value.split(/[,\n]/).map(item => item.trim()).filter(Boolean);
}

function normalizeTaxonomyValue(value) {
    return value.trim().replace(/\s+/g, " ").toLocaleLowerCase();
}

function taxonomyDocId(value) {
    return normalizeTaxonomyValue(value).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 100);
}

async function loadTaxonomy() {
    try {
        const payload = await apiFetch("/api/taxonomy");
        await Promise.all(Object.keys(taxonomyUI).map(async kind => {
            const values = payload[kind] || [];
            taxonomy[kind] = (values.length ? values : defaultTaxonomy[kind])
                .sort((a, b) => a.localeCompare(b));
            renderTaxonomyOptions(kind);
        }));

        console.log("FiniSpeak taxonomy loaded:", taxonomy);
    } catch (error) {
        console.error("Unable to load taxonomy:", error);

        Object.keys(taxonomyUI).forEach(kind => {
            taxonomy[kind] = [...defaultTaxonomy[kind]];
            renderTaxonomyOptions(kind);
        });
    }
}

function renderTaxonomyOptions(kind, open = false) {
    const input = $(taxonomyUI[kind].input);
    const list = $(taxonomyUI[kind].options);
    const search = normalizeTaxonomyValue(input.value || "");
    const matches = taxonomy[kind]
        .filter(name => !selectedTags[kind].some(v => normalizeTaxonomyValue(v) === normalizeTaxonomyValue(name)))
        .filter(name => !search || normalizeTaxonomyValue(name).includes(search))
        .slice(0, 25);

    const suggestions = matches.map((name, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.id = `${taxonomyUI[kind].options}-${index}`;
        button.className = "tag-suggestion";
        button.dataset.value = name;
        button.setAttribute("role", "option");
        button.setAttribute("aria-selected", "false");
        button.textContent = name;
        button.addEventListener("mousedown", event => event.preventDefault());
        button.addEventListener("click", async () => {
            input.value = name;
            await addTagFromInput(kind);
        });
        return button;
    });

    list.replaceChildren(...suggestions);
    taxonomySuggestionIndex[kind] = -1;
    const shouldOpen = open && document.activeElement === input && matches.length > 0;
    list.classList.toggle("hidden", !shouldOpen);
    input.setAttribute("aria-expanded", String(shouldOpen));
}

function closeTaxonomySuggestions(kind) {
    $(taxonomyUI[kind].options).classList.add("hidden");
    $(taxonomyUI[kind].input).setAttribute("aria-expanded", "false");
    $(taxonomyUI[kind].input).removeAttribute("aria-activedescendant");
    taxonomySuggestionIndex[kind] = -1;
}

function moveTaxonomySuggestion(kind, direction) {
    const input = $(taxonomyUI[kind].input);
    const list = $(taxonomyUI[kind].options);
    if (list.classList.contains("hidden")) renderTaxonomyOptions(kind, true);
    const suggestions = [...list.querySelectorAll(".tag-suggestion")];
    if (!suggestions.length) return;
    taxonomySuggestionIndex[kind] = taxonomySuggestionIndex[kind] === -1
        ? (direction > 0 ? 0 : suggestions.length - 1)
        : (taxonomySuggestionIndex[kind] + direction + suggestions.length) % suggestions.length;
    suggestions.forEach((suggestion, index) => {
        const active = index === taxonomySuggestionIndex[kind];
        suggestion.classList.toggle("active", active);
        suggestion.setAttribute("aria-selected", String(active));
        if (active) suggestion.scrollIntoView({ block: "nearest" });
    });
    input.setAttribute("aria-activedescendant", `${taxonomyUI[kind].options}-${taxonomySuggestionIndex[kind]}`);
}

function setSelectedTags(kind, values = []) {
    const unique = [];
    values.forEach(value => {
        const clean = String(value || "").trim();
        if (clean && !unique.some(v => normalizeTaxonomyValue(v) === normalizeTaxonomyValue(clean))) unique.push(clean);
    });
    selectedTags[kind] = unique;
    renderTags(kind);
}

function renderTags(kind) {
    const container = $(taxonomyUI[kind].tags);
    container.replaceChildren(...selectedTags[kind].map(name => {
        const chip = document.createElement("span"); chip.className = "tag-chip";
        const text = document.createElement("span"); text.textContent = name;
        const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "×"; remove.setAttribute("aria-label", `Remove ${name}`);
        remove.onclick = () => { selectedTags[kind] = selectedTags[kind].filter(v => v !== name); renderTags(kind); updateInterpreterCompletion(); };
        chip.append(text, remove); return chip;
    }));
    renderTaxonomyOptions(kind);
}

async function addTagFromInput(kind) {
    const input = $(taxonomyUI[kind].input);
    const addButton = document.querySelector(`[data-add-tag="${kind}"]`);
    const raw = input.value.replace(/,$/, "").trim();
    if (!raw) return;
    const normalized = normalizeTaxonomyValue(raw);
    const existing = taxonomy[kind].find(name => normalizeTaxonomyValue(name) === normalized);
    const name = existing || raw.replace(/\b\w/g, c => c.toUpperCase());
    try {
        addButton.disabled = true;
        addButton.textContent = existing ? "Adding…" : "Saving…";
        if (!existing) {
            const id = taxonomyDocId(name);
            if (!id) return;
            const result = currentProfile.role === "admin"
                ? await apiFetch(`/api/taxonomy/${encodeURIComponent(kind)}`, { method: "POST", body: JSON.stringify({ id, name, extra: { nameLower: normalized, seeded: false } }) })
                : { record: { name } };
            const stored = result.record?.name || name;
            if (!taxonomy[kind].some(v => normalizeTaxonomyValue(v) === normalizeTaxonomyValue(stored))) taxonomy[kind].push(stored);
            taxonomy[kind].sort((a,b) => a.localeCompare(b));
        }
        const canonical = taxonomy[kind].find(v => normalizeTaxonomyValue(v) === normalized) || name;
        if (!selectedTags[kind].some(v => normalizeTaxonomyValue(v) === normalized)) selectedTags[kind].push(canonical);
        input.value = "";
        renderTags(kind);
        closeTaxonomySuggestions(kind);
        updateInterpreterCompletion();
    } catch (error) {
        console.error(`Unable to add ${kind} value:`, error);
        $("interpreterProfileStatus").textContent = `Could not add “${name}”. Please try again.`;
    } finally {
        addButton.disabled = false;
        addButton.textContent = "Add";
    }
}

function hydrateInterpreterProfile(profile = {}) {
    const p = profile;
    $("interpreterFullName").value = p.displayName || currentProfile.displayName || "";
    setPhoneFieldValue("interpreterPhone", p.phone || "");
    $("interpreterBio").value = p.bio || "";
    setSelectedTags("languages", p.languages || []);
    setSelectedTags("dialects", p.dialects || []);
    setSelectedTags("specialties", p.specialties || []);
    $("interpreterYears").value = p.yearsExperience ?? "";
    $("interpreterRate").value = p.ratePerMinute ?? "";
    $("interpreterCredentials").value = (p.credentials || []).join("\n");
    pendingCredentialRemovalPaths = new Set();
    renderCredentialReviewStatus(p);
    renderCredentialDocuments(p.credentialDocuments || []);
    const availability = p.availability || {};
    document.querySelectorAll('input[name="availabilityDay"]').forEach(input => input.checked = (availability.days || []).includes(input.value));
    $("availabilityStart").value = availability.start || "";
    $("availabilityEnd").value = availability.end || "";
    $("interpreterAvailableNow").checked = Boolean(availability.availableNow);
    const serviceLocation = p.serviceLocation || {};
    const serviceOptions = p.serviceOptions || {};
    $("interpreterServiceArea").value = [serviceLocation.city, serviceLocation.state, serviceLocation.country].filter(Boolean).join(", ");
    $("interpreterServiceRadius").value = String(serviceOptions.radiusMiles || 25);
    $("interpreterInPerson").checked = Boolean(serviceOptions.inPerson);
    $("interpreterRemote").checked = serviceOptions.remote !== false;
    $("interpreterShowOnMap").checked = Boolean(serviceLocation.showOnMap);
    setInterpreterPhoto(p.photoUrl || "");
    updateInterpreterCompletion();
    renderInterpreterLifecycle(p);
    hydrateDashboardProfile();
    renderTranslatorDashboard();
}

function renderCredentialDocuments(documents = []) {
    const container = $("credentialDocumentList");
    const visibleDocuments = documents.filter(credentialDocument => !pendingCredentialRemovalPaths.has(credentialDocument.path));
    if (!visibleDocuments.length) {
        container.innerHTML = "<p>No credential documents uploaded yet.</p>";
        return;
    }
    container.replaceChildren(...visibleDocuments.map(credentialDocument => {
        const row = document.createElement("span");
        row.className = "credential-document";
        const name = document.createElement("span");
        name.textContent = credentialDocument.name || "Credential document";
        const view = document.createElement("button");
        view.className = "text-button";
        view.type = "button";
        view.textContent = "View";
        view.onclick = () => openInterpreterCredentialDocument(credentialDocument, view);
        const remove = document.createElement("button");
        remove.className = "text-button reject-action";
        remove.type = "button";
        remove.textContent = "Remove";
        remove.onclick = () => {
            if (credentialDocument.path) pendingCredentialRemovalPaths.add(credentialDocument.path);
            renderCredentialDocuments(documents);
            updateInterpreterCompletion();
            $("interpreterProfileStatus").textContent = `${credentialDocument.name || "Credential document"} will be removed when you save.`;
        };
        row.append(name, view, remove);
        return row;
    }));
}

async function openInterpreterCredentialDocument(credentialDocument, button) {
    if (!credentialDocument.path) return;
    button.disabled = true;
    try {
        window.open(credentialDocument.path, "_blank", "noopener");
    } catch (error) {
        $("interpreterProfileStatus").textContent = `Could not open credential document: ${error.message}`;
    } finally { button.disabled = false; }
}

function renderCredentialReviewStatus(profile = {}) {
    const labels = {
        unsubmitted: "Not submitted",
        submitted: "Pending review",
        approved: "Approved",
        needs_changes: "Changes requested",
        rejected: "Rejected"
    };
    const status = profile.verificationStatus === "verified" ? "approved" : (profile.credentialStatus || "unsubmitted");
    $("interpreterCredentialStatus").textContent = labels[status] || status.replace(/_/g, " ");
}

function interpreterLifecycleStatus(profile = {}) {
    if (profile.verificationStatus === "verified") return "verified";
    if (profile.credentialStatus === "submitted" || profile.onboardingStatus === "submitted") return "submitted";
    if (profile.verificationStatus === "needs_changes" || profile.verificationStatus === "rejected") return profile.verificationStatus;
    if (profile.onboardingStatus === "complete") return "complete";
    return "draft";
}

function renderInterpreterLifecycle(profile = {}) {
    const status = interpreterLifecycleStatus(profile);
    const labels = {
        draft: "Not submitted",
        complete: "Ready to submit",
        submitted: "Pending review",
        verified: "Verified",
        needs_changes: "Changes requested",
        rejected: "Not approved"
    };
    const messages = {
        draft: "Finish the steps below, then submit your profile for review.",
        complete: "Your profile is complete and ready to submit for verification.",
        submitted: "Your profile and credential evidence are pending administrator review.",
        verified: "Your interpreter profile is verified and visible in discovery.",
        needs_changes: "An administrator requested changes. Update your profile or credentials, then submit again.",
        rejected: "Verification was not approved. Update your information before submitting again."
    };
    const notes = ["needs_changes", "rejected"].includes(status) && profile.verificationNotes
        ? ` Reviewer note: ${profile.verificationNotes}`
        : "";
    $("interpreterVerificationSummary").textContent = labels[status] || labels.draft;
    $("interpreterLifecycleText").textContent = (messages[status] || messages.draft) + notes;
}

async function uploadCredentialDocuments(existing = []) {
    const files = [...($("interpreterCredentialFiles").files || [])];
    if (!files.length) return existing;
    const allowed = new Set(["application/pdf", "image/jpeg", "image/png", "image/webp"]);
    const documents = [...existing];
    for (const file of files) {
        if (!allowed.has(file.type)) throw new Error(`${file.name} must be a PDF, JPG, PNG, or WebP file.`);
        if (file.size > 10 * 1024 * 1024) throw new Error(`${file.name} must be under 10 MB.`);
        const body = new FormData(); body.append("purpose", "credential"); body.append("file", file);
        const uploaded = await apiFetch("/api/files", { method: "POST", body });
        documents.push(uploaded.file);
    }
    return documents;
}

async function loadInterpreterProfile() {
    const result = await apiFetch("/api/translators/me/profile");
    currentInterpreterProfile = { ...(result.profile || {}), ...(result.private || {}) };
    hydrateInterpreterProfile(currentInterpreterProfile);
}

function renderScheduledSessionList(sessions) {
    const box = $("dashboardScheduledSessions");
    if (!box || !currentUser) return;
    const upcoming = (sessions || []).filter(call => {
        if (call.translatorId !== currentUser.uid || !call.scheduledAt) return false;
        if (["ended", "declined", "cancelled"].includes(call.status)) return false;
        const when = timestampDate(call.scheduledAt);
        return !when || when.getTime() > Date.now() - 60 * 60 * 1000;
    }).sort((left, right) => (timestampDate(left.scheduledAt)?.getTime() || 0) - (timestampDate(right.scheduledAt)?.getTime() || 0));
    if (!upcoming.length) {
        box.innerHTML = "<p>No sessions are scheduled yet.</p>";
        return;
    }
    box.innerHTML = upcoming.map(call => {
        const when = timestampDate(call.scheduledAt);
        const label = when ? when.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : String(call.scheduledAt);
        const detail = [call.purpose, call.language, call.specialty].filter(Boolean).join(" · ");
        return `<article><strong>${escapeHtml(call.callerName || "Customer")}</strong><small>${escapeHtml(label)}</small>${detail ? `<p>${escapeHtml(detail)}</p>` : ""}</article>`;
    }).join("");
}

function renderTranslatorDashboard() {
    if (!isInterpreterRole(currentProfile?.role)) return;
    const p = currentInterpreterProfile || {};
    const completion = interpreterCompletion({
        displayName: p.displayName || currentProfile.displayName || "", bio: p.bio || "",
        languages: p.languages || [], specialties: p.specialties || [],
        yearsExperience: Number(p.yearsExperience || 0), availability: p.availability || { days: [] }
    });
    const availability = p.availability || {};
    $("dashboardProfileCompletion").textContent = `${completion}%`;
    $("dashboardProfileCompletionText").textContent = completion === 100 ? "Profile complete" : "Finish onboarding";
    $("dashboardVerification").textContent = profileVerificationLabel(p);
    $("dashboardRating").textContent = p.rating == null ? "New" : Number(p.rating).toFixed(1);
    $("dashboardRatingCount").textContent = p.ratingCount ? `${p.ratingCount} review${p.ratingCount === 1 ? "" : "s"}` : "No reviews yet";
    $("dashboardExperience").textContent = `${Number(p.yearsExperience || 0)} yrs`;
    const languages = [...(p.languages || []), ...(p.dialects || [])];
    $("dashboardLanguages").textContent = languages.length ? languages.join(" · ") : "Add your languages and dialects.";
    $("dashboardSpecialties").textContent = (p.specialties || []).length ? p.specialties.join(" · ") : "Add your specialties.";
    $("dashboardSchedule").textContent = formatAvailabilitySchedule(availability);
    $("dashboardAvailableNow").checked = Boolean(availability.availableNow);
    $("dashboardAvailabilityLabel").textContent = availability.availableNow ? "Available now" : "Unavailable";
}

async function updateDashboardAvailability() {
    if (!isInterpreterRole(currentProfile?.role)) return;
    const toggle = $("dashboardAvailableNow");
    const availableNow = toggle.checked;
    $("dashboardAvailabilityLabel").textContent = availableNow ? "Available now" : "Unavailable";
    $("translatorRequestStatus").textContent = "Updating availability…";
    try {
        const availability = { ...(currentInterpreterProfile?.availability || {}), availableNow };
        await apiFetch("/api/availability", {
            method: "PATCH",
            body: JSON.stringify(availability)
        });
        currentInterpreterProfile = { ...(currentInterpreterProfile || {}), availability };
        $("interpreterAvailableNow").checked = availableNow;
        $("translatorRequestStatus").textContent = availableNow ? "Ready for interpretation requests." : "You will not be shown as available for new requests.";
    } catch (error) {
        toggle.checked = !availableNow;
        $("dashboardAvailabilityLabel").textContent = !availableNow ? "Available now" : "Unavailable";
        $("translatorRequestStatus").textContent = `Could not update availability: ${error.message}`;
    }
}

function setInterpreterPhoto(url) {
    const preview = $("interpreterPhotoPreview");
    preview.style.backgroundImage = url ? `url("${url}")` : "";
    preview.textContent = url ? "" : "Photo";
}

function previewInterpreterPhoto() {
    const file = $("interpreterPhoto").files?.[0];
    if (!file) return;
    if (!profilePhotoTypes[file.type]) { $("interpreterProfileStatus").textContent = "Choose a JPG, PNG, or WebP image."; $("interpreterPhoto").value = ""; return; }
    if (file.size > 5 * 1024 * 1024) { $("interpreterProfileStatus").textContent = "Profile photos must be under 5 MB."; $("interpreterPhoto").value = ""; return; }
    const reader = new FileReader();
    reader.onload = () => setInterpreterPhoto(reader.result);
    reader.readAsDataURL(file);
}

function interpreterFormData() {
    const experienceValue = $("interpreterYears").value.trim();
    return {
        displayName: $("interpreterFullName").value.trim(),
        phone: completePhoneNumber("interpreterPhone"),
        bio: $("interpreterBio").value.trim(),
        languages: [...selectedTags.languages],
        dialects: [...selectedTags.dialects],
        specialties: [...selectedTags.specialties],
        yearsExperience: experienceValue === "" ? null : Number(experienceValue),
        ratePerMinute: $("interpreterRate").value.trim() === "" ? null : Number($("interpreterRate").value),
        credentials: splitList($("interpreterCredentials").value),
        serviceArea: $("interpreterServiceArea").value.trim(),
        serviceOptions: {
            inPerson: $("interpreterInPerson").checked,
            remote: $("interpreterRemote").checked,
            radiusMiles: Number($("interpreterServiceRadius").value || 25)
        },
        showOnMap: $("interpreterShowOnMap").checked,
        availability: {
            days: [...document.querySelectorAll('input[name="availabilityDay"]:checked')].map(input => input.value),
            start: $("availabilityStart").value,
            end: $("availabilityEnd").value,
            availableNow: $("interpreterAvailableNow").checked,
            timezone: currentInterpreterProfile?.availability?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
        }
    };
}

function interpreterWizardSteps(data = interpreterFormData()) {
    // MySQL migration rows can legitimately omit nested values that Firestore
    // used to materialize. Normalize them here because this calculator is used
    // both with complete form data and with lightweight dashboard summaries.
    const languages = Array.isArray(data?.languages) ? data.languages : [];
    const specialties = Array.isArray(data?.specialties) ? data.specialties : [];
    const credentials = Array.isArray(data?.credentials) ? data.credentials : [];
    const availability = data?.availability && typeof data.availability === "object" ? data.availability : {};
    const availabilityDays = Array.isArray(availability.days) ? availability.days : [];
    const serviceOptions = data?.serviceOptions && typeof data.serviceOptions === "object" ? data.serviceOptions : {};
    const hasValidExperience = Number.isFinite(data.yearsExperience) && data.yearsExperience >= 0 && data.yearsExperience <= 80;
    const hasValidSchedule = availabilityDays.length && availability.start && availability.end && availability.start < availability.end;
    const existingDocuments = (currentInterpreterProfile?.credentialDocuments || []).filter(document => !pendingCredentialRemovalPaths.has(document.path));
    const selectedDocuments = [...($("interpreterCredentialFiles").files || [])];
    return [
        { label: "Personal info", complete: Boolean(data.displayName && data.bio), message: "Add your full name and professional bio before continuing." },
        { label: "Languages", complete: Boolean(languages.length && specialties.length), message: "Add at least one language and one specialty before continuing." },
        { label: "Credentials", complete: Boolean(hasValidExperience && credentials.length && (existingDocuments.length || selectedDocuments.length)), message: "Add your years of experience, at least one credential, and a supporting document before continuing." },
        { label: "Service location", complete: Boolean(serviceOptions.remote || (serviceOptions.inPerson && data.serviceArea)), message: "Choose remote or in-person service. In-person service requires a public city, state/province, or ZIP." },
        { label: "Availability", complete: Boolean(hasValidSchedule), message: "Choose at least one day and a valid start and end time." }
    ];
}

function interpreterCompletion(data = interpreterFormData()) {
    const steps = interpreterWizardSteps(data);
    return Math.round((steps.filter(step => step.complete).length / steps.length) * 100);
}

function renderInterpreterWizard(data = interpreterFormData()) {
    const steps = interpreterWizardSteps(data);
    document.querySelectorAll("[data-wizard-step]").forEach((button, index) => {
        const step = steps[index];
        const active = index === currentInterpreterWizardStep;
        button.classList.toggle("complete", step.complete);
        button.classList.toggle("incomplete", !step.complete);
        button.classList.toggle("active", active);
        button.querySelector(".wizard-step-icon").textContent = step.complete ? "✓" : "✕";
        button.setAttribute("aria-label", `${step.label}: ${step.complete ? "complete" : "incomplete"}`);
        if (active) button.setAttribute("aria-current", "step");
        else button.removeAttribute("aria-current");
    });
    document.querySelectorAll("[data-wizard-panel]").forEach(panel => {
        panel.classList.toggle("hidden", Number(panel.dataset.wizardPanel) !== currentInterpreterWizardStep);
    });
    $("interpreterWizardBack").disabled = currentInterpreterWizardStep === 0;
    $("interpreterWizardNext").classList.toggle("hidden", currentInterpreterWizardStep === steps.length - 1);
    $("interpreterFinalActions").classList.toggle("hidden", currentInterpreterWizardStep !== steps.length - 1);
    $("interpreterWizardPosition").textContent = `Step ${currentInterpreterWizardStep + 1} of ${steps.length}`;
    return steps;
}

function showInterpreterWizardStep(index, focus = true) {
    currentInterpreterWizardStep = Math.max(0, Math.min(interpreterWizardSteps().length - 1, Number(index) || 0));
    renderInterpreterWizard();
    if (focus) document.querySelector(`[data-wizard-panel="${currentInterpreterWizardStep}"] h3`)?.focus();
}

function advanceInterpreterWizard() {
    const steps = renderInterpreterWizard();
    const current = steps[currentInterpreterWizardStep];
    if (!current.complete) {
        $("interpreterProfileStatus").textContent = current.message;
        return;
    }
    $("interpreterProfileStatus").textContent = "";
    showInterpreterWizardStep(currentInterpreterWizardStep + 1);
}

function verificationSubmissionError(data) {
    const incompleteStep = interpreterWizardSteps(data).find(step => !step.complete);
    if (incompleteStep) return incompleteStep.message;
    return "";
}

function updateInterpreterCompletion(data = interpreterFormData()) {
    const pct = interpreterCompletion(data);
    renderInterpreterWizard(data);
    $("interpreterProgressBar").style.width = `${pct}%`;
    const completeSteps = interpreterWizardSteps(data).filter(step => step.complete).length;
    const totalSteps = interpreterWizardSteps(data).length;
    $("interpreterProgressText").textContent = pct === 100 ? `All ${totalSteps} profile steps are complete.` : `${completeSteps} of ${totalSteps} steps complete · Finish the steps marked ✕.`;
    $("interpreterCompletionBadge").textContent = pct === 100 ? "Profile complete" : "Not complete";
    $("interpreterCompletionBadge").classList.toggle("pending-badge", pct !== 100);
    return pct;
}

function setInterpreterSaveLoading(loading, draft = false, submitForVerification = false) {
    const profileButton = $("saveInterpreterProfile");
    const draftButton = $("saveInterpreterDraft");
    const submitButton = $("submitInterpreterVerification");
    const activeButton = submitForVerification ? submitButton : (draft ? draftButton : profileButton);
    profileButton.disabled = loading;
    draftButton.disabled = loading;
    submitButton.disabled = loading;
    profileButton.setAttribute("aria-busy", String(loading && !draft));
    draftButton.setAttribute("aria-busy", String(loading && draft));
    submitButton.setAttribute("aria-busy", String(loading && submitForVerification));

    if (loading) {
        const spinner = document.createElement("span");
        spinner.className = "button-spinner";
        spinner.setAttribute("aria-hidden", "true");
        activeButton.replaceChildren(spinner, document.createTextNode(submitForVerification ? "Submitting…" : (draft ? "Saving draft…" : "Saving profile…")));
        return;
    }

    profileButton.textContent = "Save profile";
    draftButton.textContent = "Save draft";
    submitButton.textContent = "Submit for verification";
}

async function saveInterpreterProfile(e, draft = false, submitForVerification = false) {
    e?.preventDefault?.();
    if (!isInterpreterRole(currentProfile?.role)) return;
    const status = $("interpreterProfileStatus");
    const data = interpreterFormData();
    if (data.ratePerMinute !== null && !Number.isFinite(data.ratePerMinute)) {
        status.textContent = "Enter a price per minute in dollars, or leave it blank.";
        return;
    }
    const completion = interpreterCompletion(data);
    if (!draft && completion < 100) { status.textContent = "Complete all required interpreter fields before finishing onboarding."; updateInterpreterCompletion(data); return; }
    const submissionError = submitForVerification ? verificationSubmissionError(data) : "";
    if (submissionError) { status.textContent = submissionError; updateInterpreterCompletion(data); return; }
    status.textContent = submitForVerification ? "Submitting profile for verification…" : "Saving interpreter profile…";
    setInterpreterSaveLoading(true, draft, submitForVerification);
    try {
        let photoUrl = currentInterpreterProfile?.photoUrl || "";
        let photoUploadError = null;
        const file = $("interpreterPhoto").files?.[0];
        if (file) {
            try {
                const body = new FormData(); body.append("purpose", "profile_photo"); body.append("file", file);
                const uploaded = await apiFetch("/api/files", { method: "POST", body });
                photoUrl = uploaded.file.path;
            } catch (error) {
                photoUploadError = error;
                console.error("Interpreter photo upload failed:", error);
            }
        }
        const existingCredentialDocuments = (currentInterpreterProfile?.credentialDocuments || []).filter(document => !pendingCredentialRemovalPaths.has(document.path));
        const credentialDocuments = await uploadCredentialDocuments(existingCredentialDocuments);
        const credentialStatus = submitForVerification ? "submitted" : (currentInterpreterProfile?.credentialStatus || "unsubmitted");
        const onboardingStatus = submitForVerification
            ? "submitted"
            : (currentInterpreterProfile?.verificationStatus === "verified"
                ? (currentInterpreterProfile.onboardingStatus || "verified")
                : (draft ? "draft" : (completion === 100 ? "complete" : "draft")));
        let serviceLocation = currentInterpreterProfile?.serviceLocation || {};
        const savedServiceArea = [serviceLocation.city, serviceLocation.state, serviceLocation.country].filter(Boolean).join(", ");
        if (data.serviceArea && (data.serviceArea !== savedServiceArea || !serviceLocation.geohash)) {
            const geocodeResponse = await fetch(`/api/discovery/geocode?q=${encodeURIComponent(data.serviceArea)}`);
            const geocodePayload = await geocodeResponse.json();
            if (!geocodeResponse.ok) throw new Error(geocodePayload.error || "Could not locate the public service area.");
            serviceLocation = geocodePayload.location;
        }
        // Publishing an approximate service area is controlled by its own
        // explicit consent checkbox. Remote interpreters may also choose to
        // appear on the map; requiring in-person service silently discarded
        // that consent and left otherwise valid coordinates invisible.
        serviceLocation = data.serviceArea ? { ...serviceLocation, showOnMap: Boolean(data.showOnMap) } : {};
        const { phone, serviceArea, showOnMap, ...publicData } = data;
        const payload = {
            ...publicData, serviceLocation, uid: currentUser.uid, photoUrl,
            credentialStatus, onboardingStatus,
            verificationStatus: currentInterpreterProfile?.verificationStatus || "unverified",
            rating: currentInterpreterProfile?.rating ?? null, ratingCount: currentInterpreterProfile?.ratingCount || 0,
            // The authenticated backend allowlists public fields and scrubs
            // legacy private fields before persisting this profile.
            updatedAt: Date.now()
        };
        const privatePayload = {
            uid: currentUser.uid,
            email: (currentProfile.email || currentUser.email || "").toLowerCase(),
            phone,
            credentialDocuments,
            updatedAt: Date.now()
        };
        await apiFetch("/api/translators/me/profile", { method: "PUT", body: JSON.stringify({ profile: payload, private: privatePayload }) });
        const removalPaths = [...pendingCredentialRemovalPaths];
        pendingCredentialRemovalPaths = new Set();
        await Promise.allSettled(removalPaths.map(path => {
            const match = String(path).match(/\/api\/files\/([^/]+)\/content/);
            return match ? apiFetch(`/api/files/${encodeURIComponent(match[1])}`, { method: "DELETE" }) : Promise.resolve();
        }));
        if (data.displayName && data.displayName !== currentProfile.displayName) {
            await apiFetch("/api/accounts/me", { method: "PATCH", body: JSON.stringify({ displayName: data.displayName, phone }) });
            currentUser.displayName = data.displayName;
            currentProfile = { ...currentProfile, displayName: data.displayName };
            hydrateDashboardProfile();
        }
        currentInterpreterProfile = { ...currentInterpreterProfile, ...payload, ...privatePayload, photoUrl };
        if (!photoUploadError) {
            $("interpreterPhoto").value = "";
            setInterpreterPhoto(photoUrl);
        }
        $("interpreterCredentialFiles").value = "";
        renderCredentialDocuments(credentialDocuments);
        renderCredentialReviewStatus(currentInterpreterProfile);
        renderInterpreterLifecycle(currentInterpreterProfile);
        updateInterpreterCompletion(data);
        renderTranslatorDashboard();
        if (photoUploadError) {
            status.textContent = `Profile saved, but the photo could not upload: ${photoUploadError.message}. Your selected photo is still here to retry.`;
        } else {
            status.textContent = submitForVerification ? "Profile submitted for verification. You will see the review outcome here." : (completion === 100 ? "Interpreter profile saved. It is ready to submit for verification." : "Draft saved. You can finish onboarding later.");
        }
    } catch (error) {
        status.textContent = `Could not save interpreter profile: ${error.message}`;
    } finally {
        setInterpreterSaveLoading(false, draft, submitForVerification);
    }
}

async function createCall(e) {
    e.preventDefault();
    const attemptId = `${Date.now().toString(36)}-${++callAttemptSequence}`;
    let stage = "form-submit";
    const submitButton = e.submitter || $("callForm").querySelector('button[type="submit"]');
    const preserveDialButton = submitButton?.id === "dialCallButton";
    const originalButtonText = submitButton.textContent;
    submitButton.disabled = true;
    if (!preserveDialButton) submitButton.textContent = "Finding FiniSpeak user…";
    $("dashboardStatus").textContent = "";
    setCallFormStatus("Looking up the FiniSpeak account…");
    callLog(attemptId, stage, {
        authenticated: Boolean(currentUser),
        profileRole: currentProfile?.role || null,
        signalingReady: Boolean(signalingSocket),
        online: navigator.onLine,
        secureContext: window.isSecureContext,
        mediaDevicesAvailable: Boolean(navigator.mediaDevices?.getUserMedia)
    });
    try {
        stage = "media-security-preflight";
        requireMediaCapture();
        const dialed = dialNationalDigits();
        const receiverEmail = dialed ? "" : $("receiverEmail").value.trim().toLowerCase();
        const receiverPhone = dialed ? completePhoneNumber("receiverPhone") : "";
        const phoneNormalized = dialed ? normalizePhoneNumber(receiverPhone) : "";
        if (!receiverEmail && !phoneNormalized) throw new Error("Dial a FiniSpeak number or choose a friend.");
        stage = "customer-directory-lookup";
        callLog(attemptId, stage, { emailProvided: Boolean(receiverEmail) });
        const lookupQuery = receiverEmail ? `email=${encodeURIComponent(receiverEmail)}` : `phone=${encodeURIComponent(phoneNormalized)}`;
        const lookup = await apiFetch(`/api/accounts/lookup?${lookupQuery}`);
        const receiver = lookup.account || null;
        const lookupSource = receiverEmail ? "account-email" : "account-phone";

        stage = "customer-validation";
        callLog(attemptId, stage, {
            found: Boolean(receiver),
            lookupSource,
            receiverRole: receiver?.role || null,
            receiverHasUid: Boolean(receiver?.uid)
        });
        if (!receiver) throw new Error(`No FiniSpeak account was found with that ${receiverEmail ? "email" : "number"}. Ask them to save it in their profile, then try again.`);
        const callingTranslator = isInterpreterRole(receiver.role);
        if (!callingTranslator && !["customer", "admin"].includes(receiver.role)) throw new Error("That contact belongs to an account that cannot receive customer calls.");
        if (receiver.uid === currentUser.uid) throw new Error("You cannot call yourself.");
        const selectedInterpreter = selectedInterpreterProfile?.id ? selectedInterpreterProfile : null;
        if (!preserveDialButton) submitButton.textContent = "Starting call…";
        setCallFormStatus(selectedInterpreter
            ? `Starting the call and requesting ${selectedInterpreter.displayName || "your selected interpreter"}…`
            : "Starting the call…");
        stage = "call-document-create";
        callLog(attemptId, stage, { interpreterRequested: Boolean(selectedInterpreter) });
        const created = await apiFetch("/api/calls/", {
            method: "POST", headers: { "Idempotency-Key": attemptId },
            body: JSON.stringify({
                receiverId: receiver.uid,
                translatorId: callingTranslator ? null : (selectedInterpreter?.id || null),
                purpose: callingTranslator ? "translator_chat" : "",
                processingMode: selectedProcessingMode
            })
        });
        const callId = created.callId;
        callLog(attemptId, "call-document-created", { callId });
        clearSelectedInterpreter();
        stage = "local-join";
        await joinCall(callId, attemptId);
        if (activeCallId) setCallFormStatus("");
    } catch (error) {
        console.error(`[FiniSpeak call][${attemptId}] start failed`, callErrorDetails(error, stage), error);
        setCallFormStatus(error.message || "Could not start the call. Please try again.", true);
    } finally {
        submitButton.disabled = false;
        if (!preserveDialButton) submitButton.textContent = originalButtonText;
        callLog(attemptId, "form-restored", { activeCall: Boolean(activeCallId) });
    }
}

async function startDirectTranslatorChat() {
    const profile = activeDirectoryProfile;
    const button = $("profileChatTranslator");
    const status = $("profileCallStatus");
    if (!profile?.id) return;
    if (!currentUser) {
        selectInterpreterForCall(profile);
        openAuth(false, "customer");
        $("authStatus").textContent = "Log in, then open this interpreter's profile to start a direct chat.";
        return;
    }
    const attemptId = `translator-chat-${Date.now().toString(36)}-${++callAttemptSequence}`;
    const originalButtonText = button.textContent;
    button.disabled = true;
    button.textContent = "Starting chat…";
    status.textContent = `Calling ${profile.displayName || "the translator"}…`;
    try {
        requireMediaCapture();
        const created = await apiFetch("/api/calls/", {
            method: "POST",
            headers: { "Idempotency-Key": attemptId },
            body: JSON.stringify({
                receiverId: profile.id,
                purpose: "translator_chat",
                processingMode: selectedProcessingMode
            })
        });
        await joinCall(created.callId, attemptId);
        if (activeCallId) status.textContent = "";
    } catch (error) {
        status.textContent = error.message || "Could not start the chat. Please try again.";
    } finally {
        button.disabled = false;
        button.textContent = originalButtonText;
    }
}

async function joinCall(callId, attemptId = `join-${Date.now().toString(36)}`) {
    let stage = "call-document-read";
    callLog(attemptId, stage, { callId });
    try {
        const result = await apiFetch(`/api/calls/${encodeURIComponent(callId)}`);
        const call = result.call;
        if (!call) throw new Error("Call not found.");
        const role = currentProfile?.role;
        if (!role) throw new Error("Sign in again to join this call.");
        const guest = Array.isArray(call.guestIds) && call.guestIds.includes(currentUser.uid);
        const allowedCustomer = [call.callerId, call.receiverId].includes(currentUser.uid) || guest;
        const directTranslatorChat = call.purpose === "translator_chat";
        stage = "participant-validation";
        callLog(attemptId, stage, {
            callId,
            profileRole: role,
            allowedCustomer,
            translatorAssigned: Boolean(call.translatorId)
        });
        if ((role !== "translator" || directTranslatorChat) && !allowedCustomer) throw new Error("You are not a participant in this call.");
        if (role === "translator" && !guest && !directTranslatorChat) {
            if (call.translatorId && call.translatorId !== currentUser.uid) throw new Error("Another translator has already joined.");
            stage = "translator-connect-update";
            await apiFetch(`/api/calls/${encodeURIComponent(callId)}/translator-claim`, { method: "POST", body: "{}" });
        }
        activeCallId = callId; setCallPresentation("audio"); show("callView"); $("callIdLabel").textContent = callId;
        const storedMode = call.processingModes?.[currentUser.uid]; if (storedMode) selectedProcessingMode = storedMode; renderProcessingMode();
        resetDetectedLanguage();
        document.querySelector('.video-card[data-role="local"]').dataset.speaker = currentUser.uid;
        $("requestTranslatorButton").classList.toggle("hidden", role === "translator");
        $("requestTranslatorButton").disabled = false;
        stage = "media-permission";
        callLog(attemptId, stage, { audio: true, video: false });
        await startMedia();
        callLog(attemptId, "media-ready", {
            audioTracks: localStream?.getAudioTracks().length || 0,
            videoTracks: localStream?.getVideoTracks().length || 0
        });
        currentCallRole = role === "translator" && !guest && !directTranslatorChat ? "translator" : (currentUser.uid === call.callerId ? "caller" : currentUser.uid === call.receiverId ? "receiver" : "guest");
        callExperience?.onJoined(call);
        if (processingModesEnabled && !storedMode && selectedProcessingMode !== "baseline") await apiFetch(`/api/calls/${encodeURIComponent(callId)}/processing-mode`, {method:"PATCH", body:JSON.stringify({processingMode:selectedProcessingMode})});
        stage = "participant-document-write";
        await apiFetch(`/api/sessions/${encodeURIComponent(callId)}/participants`, {
            method: "POST",
            body: JSON.stringify({ role: currentCallRole })
        });
        stage = "call-watchers-start";
        await refreshRtcConfiguration();
        watchCall(callId);
        stage = "transcription-start";
        await startTranscription(callId);
        callLog(attemptId, "join-complete", { callId, callRole: currentCallRole });
    } catch (error) {
        console.error(`[FiniSpeak call][${attemptId}] join failed`, callErrorDetails(error, stage), error);
        $("dashboardStatus").textContent = error.message;
        setCallFormStatus(error.message || "The call was created, but this device could not join it.", true);
        if (localStream || activeCallId) cleanupCall();
        show("dashboardView");
    }
}

const frontCamera = {
    facingMode: { ideal: "user" },
    width: { ideal: 640, max: 1280 },
    height: { ideal: 480, max: 720 },
    frameRate: { ideal: 15, max: 24 }
};

async function startMedia() {
    if (localStream) {
        await bindLocalPreview(localStream);
        startCameraRelay();
        const cameraLive = localStream.getVideoTracks().some(track => track.readyState === "live" && track.enabled);
        setCallPresentation(cameraLive ? "video" : "audio");
        return;
    }
    requireMediaCapture();
    localStream = await captureCallMedia({ video: false });
    for (const track of localStream.getVideoTracks()) watchCameraTrack(track);
    await bindLocalPreview(localStream);
    const cameraOn = localStream.getVideoTracks().some(track => track.readyState === "live" && track.enabled);
    document.querySelector('.video-card[data-role="local"]')?.classList.toggle("is-camera-on", cameraOn);
    setCallPresentation(cameraOn ? "video" : "audio");
    callExperience?.attachLocalStream(localStream);
    startCameraRelay();
}

async function captureCallMedia({ video = true } = {}) {
    const attempts = video ? [
        { audio: { echoCancellation: true, noiseSuppression: true }, video: frontCamera },
        { audio: true, video: { facingMode: "user" } },
        { audio: false, video: { facingMode: "user" } }
    ] : [
        { audio: { echoCancellation: true, noiseSuppression: true }, video: false },
        { audio: true, video: false }
    ];
    let stream = null;
    let failure = null;
    for (const constraints of attempts) {
        try {
            stream = await navigator.mediaDevices.getUserMedia(constraints);
            break;
        } catch (error) {
            failure = error;
        }
    }
    if (!stream) throw failure || new Error(video ? "Camera is unavailable on this device." : "Microphone is unavailable on this device.");
    if (!stream.getAudioTracks().some(track => track.readyState === "live")) {
        try {
            const microphone = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
            for (const track of microphone.getAudioTracks()) stream.addTrack(track);
        } catch (_) { /* The camera can stay on when the microphone is blocked. */ }
    }
    return stream;
}

async function bindLocalPreview(stream) {
    for (const id of ["localCapture", "localVideo"]) {
        const video = $(id);
        if (!video) continue;
        if (video.srcObject !== stream) video.srcObject = stream;
        await playPreview(video);
    }
}

async function playPreview(video) {
    if (!video) return;
    video.muted = true;
    video.defaultMuted = true;
    video.autoplay = true;
    video.playsInline = true;
    video.setAttribute("muted", "");
    video.setAttribute("playsinline", "");
    video.setAttribute("webkit-playsinline", "");
    try { await video.play(); } catch (_) {}
}

function replayCallMedia() {
    playPreview($("localCapture"));
    playPreview($("localVideo"));
    playRemoteMedia();
}

const watchedCameraTracks = new WeakSet();
function watchCameraTrack(track) {
    if (!track || watchedCameraTracks.has(track)) return;
    watchedCameraTracks.add(track);
    track.addEventListener("ended", () => {
        if (suppressCameraRestart || !document.body.classList.contains("video-call")) return;
        restartLocalCamera();
    });
}

async function restartLocalCamera() {
    if (!activeCallId || callExperience?.isAvatar?.()) return false;
    if (cameraRestart) return cameraRestart;
    if (Date.now() - lastCameraRestart < 2000) return false;
    const current = localStream?.getVideoTracks?.().find(track => track.readyState === "live" && track.enabled);
    if (current && ($("localCapture")?.videoWidth > 0 || $("localVideo")?.videoWidth > 0)) return true;
    lastCameraRestart = Date.now();
    cameraRestart = (async () => {
        try {
            const fresh = await navigator.mediaDevices.getUserMedia({ audio: false, video: frontCamera });
            const track = fresh.getVideoTracks()[0];
            if (!track || !localStream) { track?.stop(); return false; }
            for (const old of [...localStream.getVideoTracks()]) {
                localStream.removeTrack(old);
                old.stop();
            }
            localStream.addTrack(track);
            watchCameraTrack(track);
            await bindLocalPreview(localStream);
            replaceOutgoingVideo(track);
            callExperience?.markCamera?.(true);
            return true;
        } catch (error) {
            console.warn("Camera restart failed", error);
            return false;
        } finally {
            cameraRestart = null;
        }
    })();
    return cameraRestart;
}

function resumeLocalPreview() {
    if (!activeCallId) return;
    replayCallMedia();
    window.setTimeout(() => {
        if (!activeCallId) return;
        if (!document.body.classList.contains("video-call")) return;
        const track = localStream?.getVideoTracks?.()[0];
        if (!track || track.readyState === "ended") restartLocalCamera();
    }, 400);
}

function relaySource() {
    if (callExperience?.isAvatar?.()) {
        const canvas = $("localAvatarCanvas");
        return { element: canvas, enabled: Boolean(canvas && canvas.width > 0) };
    }
    const outgoing = callExperience?.outgoingVideoTrack?.();
    const cameraTrack = localStream?.getVideoTracks?.()[0];
    const sharing = outgoing && outgoing !== cameraTrack;
    if (sharing) {
        const preview = $("localVideo");
        return { element: preview, enabled: Boolean(outgoing.enabled && outgoing.readyState === "live" && preview?.videoWidth) };
    }
    const capture = $("localCapture");
    const preview = $("localVideo");
    const element = capture?.videoWidth > 0 ? capture : preview;
    const live = cameraTrack && cameraTrack.readyState === "live" && cameraTrack.enabled;
    return { element, enabled: Boolean(live && element?.videoWidth) };
}

function startCameraRelay() {
    if (!activeCallId || cameraRelay) return;
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    cameraRelay = createCameraRelay({
        callId: activeCallId,
        url: `${scheme}://${location.host}/ws/camera`,
        getSource: relaySource,
        onFrame: showRelayFrame,
        onState: open => {
            cameraRelayOpen = open;
            renderCallRoster(rosterParticipants);
        },
        onClock: refreshRelayPictures
    });
}

function stopCameraRelay() {
    cameraRelay?.stop();
    cameraRelay = null;
    cameraRelayOpen = false;
}

function showRelayFrame(uid, jpeg) {
    const profile = peerProfiles.get(uid);
    if (!document.querySelector(`[data-peer="${uid}"]`)) {
        ensureParticipantTile({ id: uid, role: profile?.role, displayName: profile?.displayName });
    }
    const card = document.querySelector(`[data-peer="${uid}"]`);
    if (!card) return;
    let image = card.querySelector("img.relay-camera");
    if (!image) {
        image = document.createElement("img");
        image.className = "relay-camera";
        image.alt = "";
        card.insertBefore(image, card.querySelector(".video-slate"));
    }
    const blob = new Blob([jpeg], { type: "image/jpeg" });
    const url = URL.createObjectURL(blob);
    const previous = image.dataset.objectUrl;
    image.onload = () => { if (previous) URL.revokeObjectURL(previous); };
    image.onerror = () => URL.revokeObjectURL(url);
    image.src = url;
    image.dataset.objectUrl = url;
    card.dataset.relayAt = String(Date.now());
    refreshTilePicture(card);
}

function refreshRelayPictures() {
    document.querySelectorAll("#callView .video-card[data-peer]").forEach(refreshTilePicture);
}

function refreshTilePicture(card) {
    if (!card) return;
    const video = card.querySelector("video");
    const webrtc = Boolean(video && video.videoWidth > 0);
    const relayFresh = Number(card.dataset.relayAt || 0) > Date.now() - 1600;
    const liveTrack = video?.srcObject instanceof MediaStream && video.srcObject.getVideoTracks().some(track => track.readyState === "live" && track.enabled !== false);
    card.classList.toggle("is-relay-camera", relayFresh && !webrtc);
    if (webrtc || relayFresh || liveTrack || card.classList.contains("is-avatar")) card.classList.add("is-camera-on");
}

function watchCameraHealth() {
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") resumeLocalPreview();
    });
    window.addEventListener("pageshow", resumeLocalPreview);
}

function watchCall(callId) {
    cleanupListeners();
    connectSignaling(callId);
    const refresh = async () => {
      try {
        const callPayload = await apiFetch(`/api/calls/${encodeURIComponent(callId)}`);
        const call = callPayload.call;
        if (["ended", "declined", "cancelled"].includes(call.status)) {
            const ended = call.status === "ended";
            if (ended) {
                lastCallRecord = call;
                lastSessionSnapshot = captureSessionSnapshot();
                rememberEndedCall(callId);
                renderKeyMoments(call);
            }
            cleanupCall();
            show("dashboardView");
            if (ended) openDashboardPanel("summary");
            loadConversationHistory();
            return;
        }
        const [participantPayload, transcriptPayload] = await Promise.all([
          apiFetch(`/api/sessions/${encodeURIComponent(callId)}/participants`),
          apiFetch(`/api/calls/${encodeURIComponent(callId)}/transcripts`)
        ]);
        const translatorConnected = call.translationStatus === "connected";
        activeTranslatorConnected = translatorConnected;
        $("callTitle").textContent = call.status === "ended" ? "Call ended" : "Live conversation";
        $("requestTranslatorButton").disabled = translatorConnected;
        $("requestTranslatorButton").title = translatorConnected ? "A translator has joined this call" : "";
        invitedTranslatorId = call.invitedTranslatorId || null;
        const translatorWait = `Calling ${call.invitedTranslatorName || "the translator"}… waiting for them to accept.`;
        $("callStatus").textContent = call.status === "ringing"
            ? "Calling… waiting for the other customer to accept."
            : call.status === "declined"
                ? "Call declined."
                : call.invitedTranslatorId
                    ? translatorWait
                    : translatorConnected
                        ? ""
                        : "Customer call connected";
        const participantRows = participantPayload.participants || [];
        if (participantRows.some(person => person?.id === currentUser.uid && person.leftAt)) {
            lastSessionSnapshot = captureSessionSnapshot();
            rememberEndedCall(callId);
            cleanupCall();
            show("dashboardView");
            openDashboardPanel("summary");
            loadConversationHistory();
            return;
        }
        const ids = new Set();
        rosterParticipants = peopleInCall(call, participantRows);
        syncAudioCallFaces();
        const nextMembershipKey = rosterParticipants.map(person => person?.id).filter(Boolean).sort().join("|");
        if (callMembershipKey && nextMembershipKey !== callMembershipKey) {
            connectSignaling(callId);
            cameraRelay?.reconnect?.();
        }
        callMembershipKey = nextMembershipKey;
        for (const participant of rosterParticipants) {
            if (!participant?.id || participant.id === currentUser.uid) continue;
            ids.add(participant.id);
            ensureParticipantTile(participant);
            kickPeer(callId, participant.id, participant);
        }
        for (const [uid, pc] of peerConnections) if (!ids.has(uid)) { pc.close(); peerConnections.delete(uid); peerDebug.delete(uid); removeRemoteVideo(uid); }
        const rows = transcriptPayload.transcripts || [];
        rows.sort((a, b) => {
            const aMs = profileTimestampMillis(a.createdAt) || a.clientCreatedAt || 0;
            const bMs = profileTimestampMillis(b.createdAt) || b.clientCreatedAt || 0;
            return aMs - bMs;
        });
        renderCallRoster(rosterParticipants, rows);
        renderTranscript(rows);
        callExperience?.sync(call, participantRows.filter(person => person && !person.leftAt));
        callExperience?.updateSubtitles(rows);
        callExperience?.maybeSpeak(rows);
        callExperience?.layout();
      } catch (error) { handleDashboardListenerError("active-call", error); }
    };
    refresh();
    const timer = window.setInterval(refresh, 2000);
    callUnsubs.push(() => window.clearInterval(timer));
}

function mergeLiveTranscript(row) {
    if (!row?.id || !activeCallId) return;
    const rows = [...rosterTranscripts];
    const index = rows.findIndex(item => item.id === row.id);
    if (index >= 0) rows[index] = row;
    else rows.push(row);
    rows.sort((a, b) => {
        const aMs = profileTimestampMillis(a.createdAt) || a.clientCreatedAt || 0;
        const bMs = profileTimestampMillis(b.createdAt) || b.clientCreatedAt || 0;
        return aMs - bMs;
    });
    rosterTranscripts = rows;
    renderCallRoster(rosterParticipants, rows);
    renderTranscript(rows);
    callExperience?.updateSubtitles(rows);
    callExperience?.maybeSpeak(rows);
}

async function broadcastCallUpdate(type, payload) {
    if (!activeCallId) return;
    try { await signalingReady; } catch (_) { return; }
    const recipients = new Set(rosterParticipants.map(person => person?.id).filter(Boolean));
    for (const uid of peerConnections.keys()) recipients.add(uid);
    recipients.delete(currentUser?.uid);
    for (const uid of recipients) {
        try { sendSignal(type, uid, payload); } catch (_) {}
    }
}

function queueCaptionBroadcast(text) {
    pendingCaptionText = String(text || "").trim();
    if (captionBroadcastTimer) return;
    captionBroadcastTimer = window.setTimeout(() => {
        captionBroadcastTimer = null;
        if (pendingCaptionText === lastCaptionText) return;
        lastCaptionText = pendingCaptionText;
        broadcastCallUpdate("caption", {
            text: pendingCaptionText,
            speakerName: currentProfile?.displayName || currentUser?.displayName || "Speaker"
        });
    }, 350);
}

function clearSharedCaption() {
    window.clearTimeout(captionBroadcastTimer);
    captionBroadcastTimer = null;
    pendingCaptionText = "";
    if (!lastCaptionText) return;
    lastCaptionText = "";
    broadcastCallUpdate("caption", {
        text: "",
        speakerName: currentProfile?.displayName || currentUser?.displayName || "Speaker"
    });
}

function peerSnapshot(pc) {
    return {
        connection: pc?.connectionState || "waiting",
        ice: pc?.iceConnectionState || "",
        signaling: pc?.signalingState || "",
        video: liveReceiver(pc, "video"),
        audio: liveReceiver(pc, "audio")
    };
}

function peopleInCall(call, participants) {
    const people = new Map();
    for (const participant of participants || []) {
        if (!participant?.id) continue;
        if (participant.leftAt) continue;
        people.set(participant.id, participant);
    }
    const roles = [
        ["callerId", "callerName", "caller"],
        ["receiverId", "receiverName", "receiver"],
        ["translatorId", "translatorName", "translator"]
    ];
    for (const [idKey, nameKey, role] of roles) {
        const id = call?.[idKey];
        if (role === "translator" && call?.translationStatus !== "connected" && !people.has(id)) continue;
        if (!id || people.has(id)) continue;
        people.set(id, { id, displayName: call[nameKey] || "Guest", role });
    }
    for (const id of call?.guestIds || []) {
        if (id && !people.has(id)) people.set(id, { id, displayName: "Guest", role: "guest" });
    }
    return [...people.values()];
}

async function refreshRtcConfiguration() {
    try {
        rtcConfiguration = normalizeIceConfiguration(await apiFetch("/api/webrtc-config"));
    } catch (error) {
        rtcConfiguration = normalizeIceConfiguration(null);
        console.error("WebRTC configuration failed:", error);
    }
}

function relayNote(pc) {
    if (pc?._forceRelay) return "turn relay";
    if (rtcConfiguration.relay) return "turn ready";
    if (pc?.iceConnectionState === "failed") return "relay required";
    return "stun only";
}

function iceKey() {
    return JSON.stringify(rtcConfiguration.iceServers || []);
}

function recordPeer(uid, patch) {
    peerDebug.set(uid, { ...(peerDebug.get(uid) || {}), ...patch });
    renderCallRoster(rosterParticipants);
}

function signalingLabel() {
    if (!signalingSocket) return "signaling off";
    if (signalingSocket.readyState === WebSocket.OPEN) {
        const picture = cameraRelayOpen ? "picture relay" : (rtcConfiguration.relay ? "" : "stun only");
        return ["signaling open", picture].filter(Boolean).join(", ");
    }
    return "signaling closed";
}

function renderCallRoster(participants = rosterParticipants, transcripts = rosterTranscripts) {
    rosterParticipants = participants || [];
    rosterTranscripts = transcripts || [];
    const list = $("callRosterList");
    const status = $("callRosterStatus");
    if (!list || !currentUser) return;
    const people = [];
    const joined = new Map((participants || []).filter(person => person?.id).map(person => [person.id, person]));
    const local = joined.get(currentUser.uid);
    people.push({
        id: currentUser.uid,
        name: local?.displayName || currentProfile?.displayName || "You",
        role: "you",
        connection: "local",
        video: Boolean(localStream?.getVideoTracks?.().some(track => track.readyState === "live" && track.enabled)),
        audio: Boolean(localStream?.getAudioTracks?.().some(track => track.readyState === "live" && track.enabled))
    });
    for (const participant of joined.values()) {
        if (participant.id === currentUser.uid) continue;
        const debug = peerDebug.get(participant.id) || {};
        const live = peerSnapshot(peerConnections.get(participant.id));
        people.push({
            id: participant.id,
            name: participant.displayName || "Guest",
            role: participant.role || "guest",
            connection: debug.error ? "error" : (live.connection || debug.connection || "waiting"),
            ice: live.ice || debug.ice || "",
            signaling: live.signaling || debug.signaling || "",
            video: Boolean(live.video),
            audio: Boolean(live.audio),
            error: debug.error || "",
            note: debug.note || ""
        });
    }
    const seen = new Set(people.map(person => person.id));
    for (const row of transcripts || []) {
        if (!row?.speakerId || seen.has(row.speakerId)) continue;
        seen.add(row.speakerId);
        people.push({ id: row.speakerId, name: row.speakerName || "Speaker", role: row.speakerRole || "transcript", connection: "transcript only", video: false, audio: false, error: "heard in transcript, no camera peer" });
    }
    const summary = people.map(person => [person.id, person.connection, person.ice, person.signaling, person.video, person.audio, person.error, person.note].join(":")).join("|");
    if (status) status.textContent = `${people.length} active · ${signalingLabel()}`;
    if (list.dataset.summary === summary) return;
    list.dataset.summary = summary;
    list.replaceChildren();
    for (const person of people) {
        const item = document.createElement("li");
        const failed = person.connection === "failed" || person.connection === "error" || person.connection === "transcript only";
        item.className = person.connection === "connected" || person.connection === "local" ? "is-connected" : failed ? "is-failed" : "";
        const name = document.createElement("strong");
        name.textContent = person.name;
        const meta = document.createElement("small");
        meta.textContent = person.error || [person.role, person.connection, person.ice, person.signaling, person.video ? "video" : "no video", person.audio ? "audio" : "no audio", person.note].filter(Boolean).join(" · ");
        item.append(name, meta);
        list.appendChild(item);
    }
}

function ensureParticipantTile(participant) {
    if (!participant?.id || participant.id === currentUser?.uid) return;
    let card = document.querySelector(`[data-peer="${participant.id}"]`);
    if (!card) {
        card = document.createElement("article");
        card.className = "video-card";
        card.dataset.peer = participant.id;
        card.innerHTML = '<video autoplay muted playsinline></video><canvas class="avatar-canvas is-hidden" aria-hidden="true"></canvas><div class="call-face-photo concept-avatar" aria-hidden="true"></div><div class="video-slate"><strong></strong><span>Camera</span></div><span class="speaking-indicator" aria-hidden="true"></span><div class="video-label"><span class="video-role"></span><span class="video-label-separator" aria-hidden="true">·</span><span class="video-name"></span></div><p class="tile-subtitle" hidden></p>';
        $("videoGrid").appendChild(card);
    }
    const role = ["translator", "caller", "receiver"].includes(participant.role) ? participant.role : "guest";
    card.dataset.role = role;
    card.dataset.speaker = participant.id;
    const name = participant.displayName || "FiniSpeak guest";
    card.querySelector(".video-role").textContent = participantRoleLabel(role);
    card.querySelector(".video-name").textContent = name;
    card.querySelector(".video-slate strong").textContent = name;
    const video = card.querySelector("video");
    card.classList.toggle("is-camera-on", remoteVideoVisible(video));
    setProfileAvatar(card.querySelector(".call-face-photo"), { ...participant, id: participant.id });
}

function peerSender(remoteUid) {
    return async (type, payload) => {
        await signalingReady;
        sendSignal(type, remoteUid, payload);
    };
}

function openPeer(remoteUid, profile, offerer, { forceRelay = false } = {}) {
    const send = peerSender(remoteUid);
    const pc = new RTCPeerConnection({
        iceServers: rtcConfiguration.iceServers,
        iceTransportPolicy: forceRelay ? "relay" : "all",
        bundlePolicy: "max-bundle"
    });
    pc._iceKey = iceKey();
    pc._offerer = offerer;
    pc._forceRelay = forceRelay;
    pc._suppressOffer = true;
    pc._waitStarted = Date.now();
    peerConnections.set(remoteUid, pc);
    peerProfiles.set(remoteUid, profile || null);
    const publishState = () => {
        const failed = pc.connectionState === "failed" || pc.iceConnectionState === "failed";
        if (pc.iceConnectionState === "disconnected") pc._disconnectedAt ||= Date.now();
        else pc._disconnectedAt = 0;
        recordPeer(remoteUid, {
            error: failed ? (peerDebug.get(remoteUid)?.error || "") : "",
            note: relayNote(pc),
            ...peerSnapshot(pc)
        });
        const states = [...peerConnections.values()].map(peer => peer.connectionState);
        const summary = states.includes("connected") ? "connected" : states.includes("failed") ? "failed" : "connecting";
        callExperience?.noteConnection(summary);
    };
    pc.onconnectionstatechange = publishState;
    pc.oniceconnectionstatechange = publishState;
    attachMeshHandlers(pc, {
        offerer,
        send,
        onTrack: (track, stream) => attachRemoteTrack(remoteUid, profile, track, stream),
        onError: error => recordPeer(remoteUid, { error: error.message, connection: "error" })
    });
    publishState();
    return pc;
}

function senderFor(pc, kind) {
    const transceiver = pc.getTransceivers?.().find(item => item.receiver?.track?.kind === kind || item.sender?.track?.kind === kind);
    return transceiver?.sender || null;
}

function liveLocalTrack(kind) {
    if (kind === "video") {
        const preferred = callExperience?.outgoingVideoTrack();
        if (preferred?.readyState === "live") return preferred;
    }
    return localStream?.getTracks?.().find(track => track.kind === kind && track.readyState === "live") || null;
}

async function attachLocalTracks(pc) {
    if (!pc || pc.connectionState === "closed" || pc.signalingState === "closed") return;
    const jobs = [];
    for (const kind of ["audio", "video"]) {
        let sender = senderFor(pc, kind);
        if (!sender) sender = pc.addTransceiver(kind, { direction: "sendrecv" }).sender;
        const track = liveLocalTrack(kind);
        if (track && sender.track !== track) jobs.push(Promise.resolve(sender.replaceTrack(track)).catch(() => {}));
    }
    await Promise.all(jobs);
}

function kickPeer(callId, remoteUid, profile) {
    const prior = peerJobs.get(remoteUid) || Promise.resolve();
    const run = prior.catch(() => {}).then(() => ensurePeer(callId, remoteUid, profile));
    peerJobs.set(remoteUid, run);
    run.catch(error => recordPeer(remoteUid, { error: error.message, connection: "error" }));
}

function peerIsConnected(pc) {
    return pc?.connectionState === "connected" || pc?.iceConnectionState === "connected" || pc?.iceConnectionState === "completed";
}

async function ensurePeer(callId, remoteUid, profile) {
    if (activeCallId !== callId) return;
    peerProfiles.set(remoteUid, profile || null);
    const offerer = isOfferer(currentUser.uid, remoteUid);
    let existing = peerConnections.get(remoteUid);
    const relayTimedOut = shouldForceRelay({
        relayAvailable: rtcConfiguration.relay,
        forceRelay: Boolean(existing?._forceRelay),
        connected: peerIsConnected(existing),
        waitedMs: existing ? Date.now() - (existing._waitStarted || Date.now()) : 0,
        disconnectedMs: existing?._disconnectedAt ? Date.now() - existing._disconnectedAt : 0
    });
    const stale = existing && (existing.connectionState === "failed" || existing.connectionState === "closed" || existing.signalingState === "closed" || existing.iceConnectionState === "failed");
    const wrongNetwork = existing && existing._iceKey !== iceKey() && existing.connectionState !== "connected";
    const offerStuck = existing && existing.signalingState === "have-local-offer" && existing.iceConnectionState === "new" && existing._offerStarted && Date.now() - existing._offerStarted > 8000;
    const makingStuck = existing && existing._makingOffer && existing.signalingState === "stable" && !existing.currentRemoteDescription && Date.now() - (existing._waitStarted || 0) > 8000;
    const replaceWithRelay = Boolean(existing?._forceRelay || (rtcConfiguration.relay && existing && (stale || offerStuck || makingStuck || relayTimedOut)));
    if (stale || wrongNetwork || offerStuck || makingStuck || relayTimedOut) {
        existing.close();
        peerConnections.delete(remoteUid);
        existing = null;
    }
    const send = peerSender(remoteUid);
    if (existing) {
        existing._offerer = offerer;
        await attachLocalTracks(existing);
        const connected = peerIsConnected(existing);
        recordPeer(remoteUid, { note: relayNote(existing), ...peerSnapshot(existing) });
        if (connected || activeCallId !== callId) return;
        try {
            if (existing && peerConnections.get(remoteUid) === existing) {
                const decision = shouldSendOffer({
                    offerer,
                    signalingState: existing.signalingState,
                    hasRemote: Boolean(existing.currentRemoteDescription),
                    waitedMs: Date.now() - (existing._waitStarted || 0),
                    connected: false
                });
                if (decision === "resend") await resendLocalOffer(existing, send);
                else if (decision === "offer") await sendOffer(existing, send);
            }
        } catch (error) {
            recordPeer(remoteUid, { error: error.message, connection: "error" });
        }
        if (existing && peerConnections.get(remoteUid) === existing) return;
    }
    if (!localStream) throw new Error("Local camera is not ready.");
    const queued = pendingSignals.get(remoteUid) || [];
    const pc = openPeer(remoteUid, profile, offerer, { forceRelay: replaceWithRelay });
    await attachLocalTracks(pc);
    for (const message of queued) await applySignal(message);
    pendingSignals.delete(remoteUid);
    pc._suppressOffer = false;
    if (peerConnections.get(remoteUid) === pc && offerer && pc.signalingState === "stable" && !pc.currentRemoteDescription) {
        await sendOffer(pc, send);
    }
}

function connectSignaling(callId) {
    if (signalingSocket) {
        signalingSocket.onclose = null;
        signalingSocket.onmessage = null;
        signalingSocket.onerror = null;
        signalingSocket.close();
    }
    const scheme = location.protocol === "https:" ? "wss" : "ws";
        signalingReady = new Promise((resolve, reject) => {
        let settled = false;
        const fail = error => {
            if (settled) return;
            settled = true;
            reject(error);
        };
        signalingSocket = new WebSocket(`${scheme}://${location.host}/ws/signaling`);
        signalingSocket.onopen = () => signalingSocket.send(JSON.stringify({ type: "join", callId, after: signalingCursor }));
        signalingSocket.onmessage = async event => {
            const message = JSON.parse(event.data);
            if (message.type === "ready") { settled = true; resolve(); return; }
            if (message.type === "error") { fail(new Error(message.message || "Signaling failed.")); return; }
            if (message.type === "signal-error") {
                const uid = message.to || message.from;
                if (uid) recordPeer(uid, { error: message.message || "Signaling rejected the camera offer." });
                return;
            }
            if (message.eventId) signalingCursor = Math.max(signalingCursor, Number(message.eventId));
            if (message.type === "caption") {
                callExperience?.onRemotePartial(message.from, message.payload?.speakerName, message.payload?.text || "");
                return;
            }
            if (message.type === "transcript" && message.payload?.transcript) {
                callExperience?.onRemotePartial(message.from, "", "");
                mergeLiveTranscript(message.payload.transcript);
                return;
            }
            if (["offer", "answer", "ice", "hangup", "reconnect"].includes(message.type)) {
                if (peerConnections.has(message.from)) await applySignal(message);
                else pendingSignals.set(message.from, [...(pendingSignals.get(message.from) || []), message]);
            }
        };
        signalingSocket.onerror = () => fail(new Error("Signaling connection failed."));
        signalingSocket.onclose = () => {
            fail(new Error("Signaling connection closed."));
            if (activeCallId === callId) window.setTimeout(() => connectSignaling(callId), 1000);
        };
    });
}

function sendSignal(type, to, payload = {}) {
    if (!signalingSocket || signalingSocket.readyState !== WebSocket.OPEN) throw new Error("Signaling is not connected.");
    signalingSocket.send(JSON.stringify({ type, to, payload, clientEventId: crypto.randomUUID() }));
}

async function applySignal(message) {
    const pc = peerConnections.get(message.from);
    if (!pc) return;
    if (message.type === "hangup") {
        pc.close();
        peerConnections.delete(message.from);
        removeRemoteVideo(message.from);
        return;
    }
    try {
        const queued = await applyMeshSignal(pc, message, (type, payload) => sendSignal(type, message.from, payload));
        if (queued === "queue") {
            pendingIceCandidates.set(message.from, [...(pendingIceCandidates.get(message.from) || []), message.payload]);
            return;
        }
        if (queued === "restart") {
            if (message.restarted) {
                recordPeer(message.from, { error: "Could not accept the other camera." });
                return;
            }
            message.restarted = true;
            const forceRelay = Boolean(pc._forceRelay);
            pc.close();
            peerConnections.delete(message.from);
            if (!localStream) throw new Error("Local camera is not ready.");
            const restarted = openPeer(message.from, peerProfiles.get(message.from), false, { forceRelay });
            await attachLocalTracks(restarted);
            await applySignal(message);
            if (peerConnections.get(message.from) === restarted) restarted._suppressOffer = false;
            return;
        }
        if (message.type === "offer" || message.type === "answer") await flushPendingIce(message.from, peerConnections.get(message.from) || pc);
        const current = peerConnections.get(message.from) || pc;
        recordPeer(message.from, { error: "", note: relayNote(current), ...peerSnapshot(current) });
    } catch (error) {
        recordPeer(message.from, { error: error.message, connection: "error" });
    }
}

async function flushPendingIce(uid, pc) {
    for (const candidate of pendingIceCandidates.get(uid) || []) {
        try { await pc.addIceCandidate(new RTCIceCandidate(candidate)); } catch (_) {}
    }
    pendingIceCandidates.delete(uid);
}

function participantRoleLabel(role) {
    if (role === "translator") return "Translator";
    if (role === "caller") return "Customer 1";
    if (role === "receiver") return "Customer 2";
    return "Guest";
}

function remoteVideoVisible(video) {
    if (!(video?.srcObject instanceof MediaStream)) return video?.videoWidth > 0;
    if (video.videoWidth > 0) return true;
    return video.srcObject.getVideoTracks().some(track => track.readyState === "live" && track.enabled !== false);
}

function playRemoteVideo(video) {
    if (!video) return;
    video.muted = true;
    video.defaultMuted = true;
    video.playsInline = true;
    video.autoplay = true;
    video.setAttribute("muted", "");
    video.setAttribute("playsinline", "");
    video.setAttribute("webkit-playsinline", "");
    video.play().catch(() => {});
}

function attachRemoteTrack(uid, profile, track, stream) {
    ensureParticipantTile({ id: uid, role: profile?.role, displayName: profile?.displayName });
    const card = document.querySelector(`[data-peer="${uid}"]`);
    if (!card || !track) return;
    const video = card.querySelector("video");
    if (track.kind === "audio") {
        const audio = remoteAudioElement(card);
        const target = audio.srcObject instanceof MediaStream ? audio.srcObject : new MediaStream();
        if (audio.srcObject !== target) audio.srcObject = target;
        if (!target.getTracks().includes(track)) target.addTrack(track);
        audio.play().catch(() => {});
        // Starting speaker audio can pause a muted video on phones. Play it again.
        playRemoteVideo(video);
        recordPeer(uid, peerSnapshot(peerConnections.get(uid)));
        callExperience?.layout();
        return;
    }
    if (!video) return;
    const remoteStream = stream instanceof MediaStream && stream.getVideoTracks().includes(track)
        ? stream
        : (video.srcObject instanceof MediaStream ? video.srcObject : new MediaStream());
    if (!remoteStream.getTracks().includes(track)) remoteStream.addTrack(track);
    if (video.srcObject !== remoteStream) video.srcObject = remoteStream;
    const show = () => {
        card.classList.toggle("is-camera-on", remoteVideoVisible(video));
        playRemoteVideo(video);
        recordPeer(uid, peerSnapshot(peerConnections.get(uid)));
    };
    track.onunmute = show;
    track.onmute = show;
    track.onended = show;
    video.onresize = show;
    video.onloadedmetadata = show;
    show();
    callExperience?.layout();
}

function remoteAudioElement(card) {
    let audio = card.querySelector("audio.remote-audio");
    if (!audio) {
        audio = document.createElement("audio");
        audio.className = "remote-audio";
        audio.autoplay = true;
        audio.muted = false;
        card.appendChild(audio);
    }
    return audio;
}
function removeRemoteVideo(uid) {
    const card = document.querySelector(`[data-peer="${uid}"]`);
    const image = card?.querySelector("img.relay-camera");
    if (image?.dataset.objectUrl) URL.revokeObjectURL(image.dataset.objectUrl);
    card?.remove();
    callExperience?.layout();
}

async function startTranscription(callId) {
    if (!localStream?.getAudioTracks().length) return;
    $("transcriptionStatus").textContent = "Connecting…";
    try {
        await ensureTranscriptionCapture(); await openTranscriptionPipeline(callId, selectedProcessingMode);
    } catch (error) {
        if (selectedProcessingMode !== "baseline") {
            $("processingModeStatus").textContent = `${selectedProcessingMode} failed. Returning to baseline.`; selectedProcessingMode="baseline"; renderProcessingMode();
            try { await apiFetch(`/api/calls/${encodeURIComponent(callId)}/processing-mode`, {method:"PATCH",body:JSON.stringify({processingMode:"baseline"})}); await openTranscriptionPipeline(callId,"baseline"); return; } catch (fallback) { error=fallback; }
        }
        $("transcriptionStatus").textContent = `Transcription unavailable: ${error.message}`; stopTranscription(false);
    }
}

function downsampleTo16k(floats, sampleRate) {
    if (!sampleRate || sampleRate <= 16100) return floats;
    const ratio = sampleRate / 16000;
    const length = Math.floor(floats.length / ratio);
    const output = new Float32Array(length);
    for (let i = 0; i < length; i++) {
        const start = Math.floor(i * ratio);
        const end = Math.min(floats.length, Math.floor((i + 1) * ratio));
        let sum = 0;
        const count = Math.max(1, end - start);
        for (let j = start; j < start + count; j++) sum += floats[j] || 0;
        output[i] = sum / count;
    }
    return output;
}
async function ensureTranscriptionCapture() {
    if (transcriptionNode) return;
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    try { transcriptionAudioContext = new AudioCtx({ latencyHint: "interactive" }); }
    catch (_) { transcriptionAudioContext = new AudioCtx(); }
    transcriptionCaptureRate = transcriptionAudioContext.sampleRate > 16100 ? 16000 : transcriptionAudioContext.sampleRate;
    await transcriptionAudioContext.audioWorklet.addModule("/static/js/pcm-worklet.js");
    transcriptionSource=transcriptionAudioContext.createMediaStreamSource(new MediaStream(localStream.getAudioTracks())); transcriptionNode=new AudioWorkletNode(transcriptionAudioContext,"finispeak-pcm");
    transcriptionGain=transcriptionAudioContext.createGain(); transcriptionGain.gain.value=0; transcriptionSource.connect(transcriptionNode); transcriptionNode.connect(transcriptionGain).connect(transcriptionAudioContext.destination);
    if (transcriptionAudioContext.state !== "running") await transcriptionAudioContext.resume();
    if (transcriptionAudioContext.state !== "running") throw new Error("Microphone processing could not start. Click the page and try again.");
    transcriptionAudioContext.onstatechange=()=>{
        if (!transcriptionAudioContext || transcriptionAudioContext.state === "running" || !activeCallId) return;
        $("transcriptionStatus").textContent="Microphone processing paused. Click the page to resume.";
    };
    transcriptionNode.port.onmessage=event=>{ const floats=downsampleTo16k(event.data, transcriptionAudioContext.sampleRate), pcm=new Int16Array(floats.length); for(let i=0;i<floats.length;i++){const s=Math.max(-1,Math.min(1,floats[i]));pcm[i]=s<0?s*32768:s*32767;} if(transcriptionSwitching||!transcriptionSocket||transcriptionSocket.readyState!==WebSocket.OPEN) bufferTranscriptionAudio(pcm.buffer); else transcriptionSocket.send(pcm.buffer); };
}
function bufferTranscriptionAudio(buffer){
    transcriptionBufferedAudio.push(buffer); transcriptionBufferedBytes+=buffer.byteLength;
    const maxBufferedBytes=(transcriptionCaptureRate||16000)*2*75;
    while(!transcriptionSwitching&&transcriptionBufferedBytes>maxBufferedBytes&&transcriptionBufferedAudio.length>1){const discarded=transcriptionBufferedAudio.shift();transcriptionBufferedBytes-=discarded.byteLength;}
}
function flushTranscriptionAudio(){ if(!transcriptionSocket||transcriptionSocket.readyState!==WebSocket.OPEN)return; for(const buffer of transcriptionBufferedAudio)transcriptionSocket.send(buffer); transcriptionBufferedAudio=[];transcriptionBufferedBytes=0; }
async function openTranscriptionPipeline(callId,mode){
    const generation=++transcriptionGeneration, scheme=location.protocol==="https:"?"wss":"ws", socket=new WebSocket(`${scheme}://${location.host}/ws/transcription`); transcriptionSocket=socket;socket.binaryType="arraybuffer";
    return new Promise((resolve,reject)=>{let ready=false;socket.onopen=()=>socket.send(JSON.stringify({type:"start",callId,sampleRate:transcriptionCaptureRate||transcriptionAudioContext.sampleRate,processingMode:mode,generation,language:confirmedDetectedLanguage}));
      socket.onmessage=async event=>{const m=JSON.parse(event.data);if(m.generation!==undefined&&m.generation!==generation)return;if(m.type==="ready"){ready=true;transcriptionSwitching=false;renderProcessingMode();flushTranscriptionAudio();startBrowserStreamingPartials(mode);$("transcriptionStatus").textContent=`Capturing microphone · ${mode}`;$("processingModeStatus").textContent=`Running ${mode} for your microphone only.`;resolve();return;}if(m.type==="stopped"){transcriptionStopResolver?.();return;}if(m.type==="listening"){$("transcriptionStatus").textContent=`Listening 🎤 · ${mode}`;return;}if(m.type==="capture"){const buffered=Number(m.bufferedSeconds||0).toFixed(1),needed=Number(m.chunkSeconds||0).toFixed(1);$("transcriptionStatus").textContent=`Capturing speech ${buffered}s / ${needed}s · ${mode}`;return;}if(m.type==="processing"){$("transcriptionStatus").textContent=`Processing speech · ${mode}`;return;}if(m.type==="error"){const e=new Error(m.message);if(!ready){socket.close();reject(e);}else handleProcessingFailure(e);return;}if(m.type==="final"&&m.text?.trim()&&activeCallId===callId&&generation===transcriptionGeneration){try{await saveFinalTranscript(callId,m,mode,generation);}catch(error){console.error("Transcript save failed",error);$("transcriptionStatus").textContent=`Speech recognized, but saving failed: ${error.message}`;}}};
      socket.onerror=()=>{const e=new Error("Transcription connection error.");if(!ready){socket.close();reject(e);}else handleProcessingFailure(e);};socket.onclose=()=>{if(transcriptionSocket===socket)transcriptionSocket=null;};});
}
async function saveFinalTranscript(callId,m,mode,generation){
    const evidence=m.languageEvidence||null, stable=evidence?.primaryLanguage||m.language, confidence=normalizeLanguageConfidence(evidence?.primaryConfidence??m.languageConfidence);if(stable)updateDetectedLanguage(stable,confidence,evidence?.confirmed===true);
    const id=`${currentUser.uid}-${generation}-${m.sequence??0}`;
    const payload={id,language:m.language||null,languageConfidence:normalizeLanguageConfidence(m.languageConfidence),primaryLanguage:stable||null,primaryLanguageConfidence:confidence,languageSampleCount:Number(evidence?.sampleCount||1),languageConfirmationRequired:evidence?.requiresConfirmation===true,text:m.text.trim(),isFinal:true,processingMode:mode,processingGeneration:generation,performance:m.metrics||null,clientCreatedAt:Date.now(),captionLanguage:callExperience?.viewerLanguage?.()||null};
    const local={...payload,speakerId:currentUser?.uid,speakerRole:currentProfile?.role,speakerName:currentProfile?.displayName||currentUser?.displayName||"You",createdAt:new Date().toISOString(),localOnly:!transcriptConsentGranted};
    mergeLiveTranscript(local);
    clearSharedCaption();
    $("partialTranscript").classList.add("hidden");
    callExperience?.onPartial("");
    if(!transcriptConsentGranted){$("transcriptionStatus").textContent="Speech recognized on this device. Allow transcript saving to keep it.";showProcessingDiagnostics(m.metrics);return;}
    const result=await apiFetch(`/api/calls/${encodeURIComponent(callId)}/transcripts`,{method:"POST",headers:{"Idempotency-Key":id},body:JSON.stringify(payload)});
    if(result.transcript){mergeLiveTranscript(result.transcript);broadcastCallUpdate("transcript",{transcript:result.transcript});}
    if(result.speechTranscript){mergeLiveTranscript(result.speechTranscript);broadcastCallUpdate("transcript",{transcript:result.speechTranscript});}
    const sourceLanguage=m.language||stable;
    const savedSpeech=String(result.speechTranscript?.language||"").toLowerCase();
    if(savedSpeech!==String(callExperience?.viewerLanguage?.()||"").toLowerCase())callExperience?.requestTranslations(callId,id,sourceLanguage);
    showProcessingDiagnostics(m.metrics);
    $("transcriptionStatus").textContent=`Listening 🎤 · ${mode}`;
}
async function requestPipelineStop(){const socket=transcriptionSocket;if(!socket||socket.readyState!==WebSocket.OPEN){socket?.close();return;}await new Promise(resolve=>{let done=false;const finish=()=>{if(!done){done=true;transcriptionStopResolver=null;resolve();}};transcriptionStopResolver=finish;socket.send(JSON.stringify({type:"stop"}));setTimeout(finish,60000);});socket.close();}
async function switchProcessingMode(next){if(!activeCallId||next===selectedProcessingMode)return;const previous=selectedProcessingMode;transcriptionSwitching=true;stopBrowserStreamingPartials();renderProcessingMode();$("processingModeStatus").textContent=`Finishing buffered ${previous} audio…`;try{await requestPipelineStop();await apiFetch(`/api/calls/${encodeURIComponent(activeCallId)}/processing-mode`,{method:"PATCH",body:JSON.stringify({processingMode:next})});selectedProcessingMode=next;renderProcessingMode();await openTranscriptionPipeline(activeCallId,next);}catch(error){selectedProcessingMode="baseline";renderProcessingMode();$("processingModeStatus").textContent=`${next} failed. Returning to baseline.`;try{await apiFetch(`/api/calls/${encodeURIComponent(activeCallId)}/processing-mode`,{method:"PATCH",body:JSON.stringify({processingMode:"baseline"})});await openTranscriptionPipeline(activeCallId,"baseline");}catch(fallbackError){transcriptionSwitching=false;renderProcessingMode();$("processingModeStatus").textContent=`Transcription logging unavailable: ${fallbackError.message||error.message}`;$("transcriptionStatus").textContent="Call audio is still connected; logging is unavailable.";}}}
async function handleProcessingFailure(error){if(transcriptionSwitching||!activeCallId)return;$("processingModeStatus").textContent=error.message;if(selectedProcessingMode!=="baseline")await switchProcessingMode("baseline");}
function startBrowserStreamingPartials(){stopBrowserStreamingPartials();const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;if(!Recognition)return;const recognition=new Recognition();recognition.continuous=true;recognition.interimResults=true;if("processLocally" in recognition)recognition.processLocally=true;recognition.onresult=event=>{let partial="";for(let i=event.resultIndex;i<event.results.length;i++)if(!event.results[i].isFinal)partial+=event.results[i][0]?.transcript||"";partial=partial.trim();$("partialTranscript").textContent=partial?`Partial · ${partial}`:"";$("partialTranscript").classList.toggle("hidden",!partial);callExperience?.onPartial(partial);queueCaptionBroadcast(partial);};browserSpeechRecognition=recognition;try{recognition.start();}catch(_){}}
function stopBrowserStreamingPartials(){const recognition=browserSpeechRecognition;browserSpeechRecognition=null;try{recognition?.stop();}catch(_){}$("partialTranscript")?.classList.add("hidden");callExperience?.onPartial("");clearSharedCaption();}
function showProcessingDiagnostics(metrics){if(!metrics||!processingModesEnabled)return;const panel=$("processingDiagnostics");panel.classList.toggle("hidden",!(location.hostname==="localhost"||location.hostname==="127.0.0.1"));panel.textContent=`method=${metrics.method}\ncapture continuity=${Math.round((metrics.audioCaptureContinuity||0)*100)}%\nrecognition=${metrics.speechRecognitionLatencyMs}ms\ntranslation=n/a (logging only)\nend-to-end=${metrics.endToEndLatencyMs}ms\naccuracy=${metrics.transcriptionAccuracy??"n/a (no reference transcript)"}\ncpu=${metrics.cpuSeconds}s\nmax rss=${metrics.memoryMaxRss} ${metrics.memoryMaxRssUnit}\napi calls=${metrics.apiCalls}\nestimated cost=${metrics.estimatedCostUsd??"n/a (rate not configured)"}`;console.debug("[FiniSpeak processing diagnostics]",metrics);}

function languageRouteKey(callId, language) {
    return `${callId}:${String(language || "").toLowerCase()}`;
}

async function routeDetectedLanguage(callId, detectedLanguage, languageConfidence = null) {
    const result = await apiFetch("/api/routing/recommend", {
        method: "POST",
        body: JSON.stringify({ callId, detectedLanguage, languageConfidence })
    });
    const count = Number(result.count || 0);
    interpreterMatchesByLanguage.set(result.detectedLanguage, result.recommendations || []);
    renderInterpreterMatches();
    if (count) {
        $("callStatus").textContent = `${count} available interpreter${count === 1 ? "" : "s"} matched.`;
    } else {
        $("callStatus").textContent = `No available exact interpreter match yet.`;
    }
    return result;
}

function requestLanguageCatalog() {
    return [...new Set([
        ...detectedCallLanguages.keys(),
        ...taxonomy.languages,
        ...defaultTaxonomy.languages,
        ...Object.values(detectedLanguageNames),
    ].map(value => String(value || "").trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function openTranslatorRequest() {
    if (!activeCallId || activeTranslatorConnected) return;
    selectedRequestLanguages = new Set(detectedCallLanguages.keys());
    $("translatorLanguageSearch").value = "";
    $("translatorRequestError").classList.add("hidden");
    renderTranslatorRequestLanguages();
    const mobile = window.matchMedia("(max-width:700px)").matches;
    $("requestLanguageSearchPanel").open = !mobile;
    setRequestMatchView("list");
    renderRequestMatchCards();
    openModal("translatorRequestModal");
    loadAvailableRequestMatches().catch(error => console.warn("Available translators could not be loaded:", error));
}

let requestMatchRelaxed = false;
let requestMatchTimer = 0;

function scheduleRequestMatchLoad() {
    window.clearTimeout(requestMatchTimer);
    requestMatchTimer = window.setTimeout(() => {
        if ($("translatorRequestModal")?.classList.contains("hidden")) return;
        loadAvailableRequestMatches().catch(error => console.warn("Available translators could not be loaded:", error));
    }, 250);
}

async function fetchDiscoveryInterpreters(params) {
    const response = await fetch(`/api/discovery?${params}`);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "Could not load translators");
    return (payload.interpreters || []).filter(profile => profile.displayName);
}

function rankRequestMatches(profiles) {
    return [...profiles].sort((a, b) =>
        Number(Boolean(b.availability?.availableNow)) - Number(Boolean(a.availability?.availableNow))
        || Number(b.rating || 0) - Number(a.rating || 0)
        || Number(b.ratingCount || 0) - Number(a.ratingCount || 0));
}

async function loadAvailableRequestMatches() {
    const languages = [...selectedRequestLanguages];
    const params = new URLSearchParams({ available: "now", limit: "12", mode: "both" });
    languages.forEach(language => params.append("language", language));
    let profiles = await fetchDiscoveryInterpreters(params);
    requestMatchRelaxed = false;
    if (!profiles.length) {
        params.delete("available");
        profiles = await fetchDiscoveryInterpreters(params);
        requestMatchRelaxed = profiles.length > 0;
    }
    requestMatchProfiles = rankRequestMatches(profiles);
    const label = languages.join(" + ") || "Selected languages";
    interpreterMatchesByLanguage.clear();
    interpreterMatchesByLanguage.set(label, requestMatchProfiles);
    renderInterpreterMatches();
    renderRequestMatchCards();
}

async function loadRequestMatches() {
    const languages = [...selectedRequestLanguages];
    if (!activeCallId || !languages.length) {
        requestMatchProfiles = [];
        renderRequestMatchCards();
        return null;
    }
    const result = await apiFetch("/api/routing/recommend", {
        method: "POST",
        body: JSON.stringify({ callId: activeCallId, languages }),
    });
    requestMatchProfiles = result.recommendations || [];
    interpreterMatchesByLanguage.clear();
    interpreterMatchesByLanguage.set(languages.join(" + "), requestMatchProfiles);
    renderInterpreterMatches();
    renderRequestMatchCards();
    return result;
}

function bindTranslatorInvite(card, profile) {
    const name = profile.displayName || "Interpreter";
    card.dataset.translatorId = profile.id || "";
    card.setAttribute("aria-label", profile.id ? `Invite ${name} to this call` : name);
    card.title = profile.id ? `Invite ${name}` : "";
    if (!profile.id) card.disabled = true;
    if (profile.id && profile.id === invitedTranslatorId) card.classList.add("is-invited");
    card.addEventListener("click", (event) => {
        event.preventDefault();
        inviteMatchedTranslator(profile, card);
    });
}

async function inviteMatchedTranslator(profile, card) {
    if (!activeCallId || !profile?.id || activeTranslatorConnected || invitingTranslatorId) return;
    invitingTranslatorId = profile.id;
    if (card) {
        card.disabled = true;
        card.setAttribute("aria-busy", "true");
    }
    const languages = [...selectedRequestLanguages];
    if (!languages.length) detectedCallLanguages.forEach((_confidence, language) => languages.push(language));
    try {
        const updated = await apiFetch(`/api/calls/${encodeURIComponent(activeCallId)}/translator-request`, {
            method: "POST",
            body: JSON.stringify({
                translatorId: profile.id,
                languages,
                language: languages[0] || null,
            }),
        });
        const call = updated.call || {};
        invitedTranslatorId = call.invitedTranslatorId || profile.id;
        document.querySelectorAll(".interpreter-match.is-invited, .request-match-card.is-invited").forEach(other => {
            if (other.dataset.translatorId !== invitedTranslatorId) other.classList.remove("is-invited");
        });
        card?.classList.add("is-invited");
        $("callStatus").textContent = `Calling ${call.invitedTranslatorName || profile.displayName || "the translator"}… waiting for them to accept.`;
        if (!$("translatorRequestModal").classList.contains("hidden")) closeModal("translatorRequestModal");
    } catch (error) {
        $("callStatus").textContent = error.message || "Could not invite that translator.";
        const requestError = $("translatorRequestError");
        if (requestError && !$("translatorRequestModal").classList.contains("hidden")) {
            requestError.textContent = error.message || "Could not invite that translator.";
            requestError.classList.remove("hidden");
        }
    } finally {
        invitingTranslatorId = null;
        if (card) {
            card.disabled = Boolean(activeTranslatorConnected || !profile.id);
            card.removeAttribute("aria-busy");
        }
    }
}

function requestMatchCard(profile) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "request-match-card";
    const available = Boolean(profile.availability?.availableNow);
    const tags = [...(profile.languages || []), ...(profile.dialects || []), ...(profile.specialties || [])].slice(0, 5);
    const remote = profile.serviceOptions?.remote !== false;
    card.innerHTML = `<div class="request-match-avatar" aria-hidden="true"></div><div><div class="request-match-heading"><strong>${escapeHtml(profile.displayName || "Interpreter")}</strong><span class="availability-dot${available ? " available" : ""}" title="${available ? "Available now" : "Currently unavailable"}"></span></div>${ratingMarkup(profile.rating, profile.ratingCount)}<p class="card-bio">${escapeHtml(profile.bio || "Professional FiniSpeak interpreter profile.")}</p><div class="request-match-tags">${tags.map(tag => `<span>${escapeHtml(tag)}</span>`).join("")}</div><div class="request-match-meta"><span>${Number(profile.yearsExperience || 0)} years experience</span><span>${escapeHtml(profile.verificationStatus === "verified" ? "verified" : "unverified")}</span><span>${remote ? "Remote" : "In person"}</span></div></div>`;
    setProfileAvatar(card.querySelector(".request-match-avatar"), profile);
    bindTranslatorInvite(card, profile);
    return card;
}

function visibleRequestMatches() {
    const mode = $("requestMatchMode")?.value || "both";
    return requestMatchProfiles.filter(profile => {
        if (mode === "remote") return profile.serviceOptions?.remote !== false;
        if (mode === "nearby") return Boolean(profile.serviceLocation?.showOnMap);
        return true;
    });
}

function renderRequestMatchCards() {
    const list = $("requestBestMatchList");
    const more = $("requestMoreMatches");
    const moreList = $("requestMoreMatchList");
    if (!list || !more || !moreList) return;
    const matches = visibleRequestMatches();
    const top = matches.slice(0, 3);
    const rest = matches.slice(3);
    const online = top.filter(profile => profile.availability?.availableNow).length;
    list.replaceChildren(...(top.length
        ? top.map(requestMatchCard)
        : [Object.assign(document.createElement("p"), { className: "request-language-empty", textContent: "No translator matches these languages yet. Choose another language below." })]));
    $("requestBestMatchCount").textContent = !matches.length
        ? "None yet"
        : requestMatchRelaxed
            ? "No one is online"
            : `${online || top.length} online`;
    const hint = $("requestMatchHint");
    if (hint) hint.textContent = requestMatchRelaxed
        ? "No one is online for these languages. You can still click a matching translator to invite them."
        : "Click a translator to invite them to this call.";
    more.classList.toggle("hidden", rest.length === 0);
    more.querySelector("summary").textContent = `More translators (${rest.length})`;
    moreList.replaceChildren(...rest.map(requestMatchCard));
    if (requestMatchView !== "list") renderRequestMatchMap(matches);
}

function setRequestMatchView(view) {
    requestMatchView = ["list", "map", "split"].includes(view) ? view : "list";
    [["requestMatchList", "list"], ["requestMatchMapButton", "map"], ["requestMatchSplit", "split"]].forEach(([id, value]) => {
        const button = $(id);
        button.classList.toggle("active", requestMatchView === value);
        button.setAttribute("aria-pressed", String(requestMatchView === value));
    });
    const showMap = requestMatchView !== "list";
    $("requestMatchMapPanel").hidden = !showMap;
    if (showMap) renderRequestMatchMap(visibleRequestMatches());
}

function renderRequestMatchMap(profiles) {
    const panel = $("requestMatchMapPanel");
    if (!panel || panel.hidden || !window.L) return;
    if (!requestMatchMap) {
        requestMatchMap = L.map("requestMatchMapCanvas", { scrollWheelZoom: false }).setView([39.8, -98.6], 3);
        const tileUrl = document.documentElement.dataset.mapTileUrl || "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
        const attribution = document.documentElement.dataset.mapAttribution || '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
        L.tileLayer(tileUrl, { maxZoom: 19, attribution }).addTo(requestMatchMap);
        requestMatchMarkerLayer = L.layerGroup().addTo(requestMatchMap);
    }
    requestMatchMarkerLayer.clearLayers();
    const bounds = [];
    profiles.forEach(profile => {
        const location = profile.serviceLocation;
        if (!location?.showOnMap || location.latitude == null || location.longitude == null) return;
        const marker = L.marker([location.latitude, location.longitude], { icon: interpreterMarkerIcon(profile) });
        marker.bindPopup(`<strong>${escapeHtml(profile.displayName || "Interpreter")}</strong>`);
        marker.addTo(requestMatchMarkerLayer);
        bounds.push([location.latitude, location.longitude]);
    });
    requestAnimationFrame(() => {
        requestMatchMap.invalidateSize({ pan: false });
        if (bounds.length) requestMatchMap.fitBounds(bounds, { padding: [24, 24], maxZoom: 8 });
    });
}

function renderTranslatorRequestLanguages() {
    const detected = [...detectedCallLanguages.entries()].sort(([a], [b]) => a.localeCompare(b));
    $("detectedRequestLanguageCount").textContent = detected.length ? `${detected.length} found` : "Still listening";
    $("detectedRequestLanguages").innerHTML = detected.length
        ? detected.map(([language, confidence]) => `<span class="request-language-chip">${escapeHtml(language)}${confidence === null ? "" : ` · ${Math.round(confidence * 100)}%`}</span>`).join("")
        : '<span class="request-language-empty">No language detected yet. Search and choose languages below.</span>';
    renderTranslatorLanguageOptions();
}

function renderTranslatorLanguageOptions() {
    const query = $("translatorLanguageSearch").value.trim().toLowerCase();
    const options = requestLanguageCatalog().filter(language => language.toLowerCase().includes(query));
    const container = $("translatorLanguageOptions");
    container.innerHTML = options.length ? "" : '<span class="request-language-empty">No languages match that search.</span>';
    for (const language of options) {
        const label = document.createElement("label");
        label.className = `request-language-option${detectedCallLanguages.has(language) ? " detected" : ""}`;
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = selectedRequestLanguages.has(language);
        checkbox.value = language;
        checkbox.onchange = () => {
            if (checkbox.checked) selectedRequestLanguages.add(language);
            else selectedRequestLanguages.delete(language);
            $("translatorRequestError").classList.add("hidden");
            updateSelectedRequestLanguageCount();
            scheduleRequestMatchLoad();
        };
        const name = document.createElement("span");
        name.textContent = language;
        label.append(checkbox, name);
        container.appendChild(label);
    }
    updateSelectedRequestLanguageCount();
}

function updateSelectedRequestLanguageCount() {
    const count = selectedRequestLanguages.size;
    $("selectedRequestLanguageCount").textContent = `${count} selected`;
    $("submitTranslatorRequest").disabled = count === 0;
}

function renderInterpreterMatches() {
    const panel = $("interpreterMatches"), list = $("interpreterMatchList");
    const matches = new Map();
    for (const [language, profiles] of interpreterMatchesByLanguage) {
        for (const profile of profiles) {
            const existing = matches.get(profile.id);
            const confidence = normalizeLanguageConfidence(profile.matchConfidence) || 0;
            if (!existing || confidence > existing.confidence) matches.set(profile.id, { profile, confidence, language });
        }
    }
    const sorted = [...matches.values()].sort((a, b) => b.confidence - a.confidence).slice(0, 5);
    panel.classList.toggle("hidden", !sorted.length);
    $("interpreterMatchSummary").textContent = sorted.length ? `${sorted.length} available now` : "";
    list.innerHTML = "";
    for (const { profile, confidence, language } of sorted) {
        const card = document.createElement("button");
        card.type = "button";
        card.className = "interpreter-match";
        const tags = [...(profile.languages || []), ...(profile.dialects || []), ...(profile.specialties || [])].slice(0, 4);
        card.innerHTML = `<div class="interpreter-match-top"><div><strong>${escapeHtml(profile.displayName || "Interpreter")}</strong><small>Matched for ${escapeHtml(language)}${profile.rating ? ` · ★ ${escapeHtml(profile.rating)}` : ""}</small></div><span class="match-confidence">${Math.round(confidence * 100)}% match</span></div><div class="interpreter-match-tags">${tags.map(tag => `<span>${escapeHtml(tag)}</span>`).join("")}</div>`;
        bindTranslatorInvite(card, profile);
        list.appendChild(card);
    }
}

function normalizeLanguageConfidence(value) {
    if (value === null || value === undefined || value === "") return null;
    const confidence = Number(value);
    if (!Number.isFinite(confidence)) return null;
    return Math.max(0, Math.min(1, confidence > 1 && confidence <= 100 ? confidence / 100 : confidence));
}

function detectedLanguageLabel(language) {
    const value = String(language || "").trim();
    return detectedLanguageNames[value.toLowerCase()] || value || "Not detected yet";
}

function rememberDetectedLanguage(language, confidence) {
    if (!language) return;
    const languageLabel = detectedLanguageLabel(language);
    const normalizedConfidence = normalizeLanguageConfidence(confidence);
    const previousConfidence = detectedCallLanguages.get(languageLabel);
    if (!detectedCallLanguages.has(languageLabel) || (normalizedConfidence !== null && (previousConfidence === null || normalizedConfidence > previousConfidence))) {
        detectedCallLanguages.set(languageLabel, normalizedConfidence);
        if (!$("translatorRequestModal").classList.contains("hidden")) {
            selectedRequestLanguages.add(languageLabel);
            renderTranslatorRequestLanguages();
        }
    }
}

function resetDetectedLanguage() {
    languageConfirmationPending = false;
    confirmedDetectedLanguage = null;
    $("detectedLanguageCard").className = "language-detection pending";
    $("detectedLanguageValue").textContent = "Listening…";
    $("detectedLanguageConfidence").textContent = "Waiting for enough speech";
    $("languageConfirmation").classList.add("hidden");
    interpreterMatchesByLanguage.clear();
    invitedTranslatorId = null;
    detectedCallLanguages.clear();
    selectedRequestLanguages.clear();
    $("interpreterMatches").classList.add("hidden");
    $("interpreterMatchList").innerHTML = "";
}

function updateDetectedLanguage(language, confidence, confirmed = false) {
    confirmed = confirmed || String(confirmedDetectedLanguage || "").toLowerCase() === String(language || "").toLowerCase();
    const normalizedConfidence = normalizeLanguageConfidence(confidence);
    rememberDetectedLanguage(language, normalizedConfidence);
    const lowConfidence = normalizedConfidence === null || normalizedConfidence < 0.7;
    languageConfirmationPending = !confirmed;
    $("detectedLanguageCard").className = `language-detection${lowConfidence && !confirmed ? " low" : ""}`;
    $("detectedLanguageValue").textContent = detectedLanguageLabel(language);
    $("detectedLanguageConfidence").textContent = confirmed
        ? "Confirmed by participant"
        : normalizedConfidence === null
            ? "Confidence unavailable · please confirm"
            : `${Math.round(normalizedConfidence * 100)}% confidence · please confirm`;
    $("languageConfirmation").className = `language-confirmation${lowConfidence ? " low" : ""}${languageConfirmationPending ? "" : " hidden"}`;
    const code = String(language || "").toLowerCase();
    if (detectedLanguageNames[code]) $("confirmedLanguage").value = code;
    callExperience?.noteLanguages?.();
    $("requestTranslatorButton").disabled = activeTranslatorConnected;
    if (!activeTranslatorConnected) $("requestTranslatorButton").title = "";
}

async function confirmDetectedLanguage() {
    if (!activeCallId) return;
    const language = $("confirmedLanguage").value;
    confirmedDetectedLanguage = language;
    updateDetectedLanguage(language, 1, true);
    if (transcriptionSocket?.readyState === WebSocket.OPEN) {
        transcriptionSocket.send(JSON.stringify({ type: "language", language }));
    }
    const routeKey = languageRouteKey(activeCallId, language);
    routedLanguageCalls.delete(routeKey);
    routedLanguageCalls.add(routeKey);
    try {
        await routeDetectedLanguage(activeCallId, language, 1);
    } catch (error) {
        routedLanguageCalls.delete(routeKey);
        $("callStatus").textContent = `Language confirmed, but interpreter matching is unavailable: ${error.message}`;
    }
}

function stopTranscription(updateStatus = true) {
    stopBrowserStreamingPartials();
    if (transcriptionSocket) {
        try { if (transcriptionSocket.readyState === WebSocket.OPEN) transcriptionSocket.send(JSON.stringify({ type: "stop" })); } catch (_) {}
        try { transcriptionSocket.close(); } catch (_) {}
    }
    transcriptionSocket = null;
    try { transcriptionNode?.disconnect(); } catch (_) {}
    try { transcriptionSource?.disconnect(); } catch (_) {}
    try { transcriptionGain?.disconnect(); } catch (_) {}
    transcriptionNode = null; transcriptionSource = null; transcriptionGain = null;
    if (transcriptionAudioContext) transcriptionAudioContext.close().catch(() => {});
    transcriptionAudioContext = null;
    transcriptionSwitching=false;transcriptionBufferedAudio=[];transcriptionBufferedBytes=0;transcriptionStopResolver?.();transcriptionStopResolver=null;renderProcessingMode();
    if (updateStatus && $("transcriptionStatus")) $("transcriptionStatus").textContent = "Transcription stopped";
}

function transcriptTimeLabel(row) {
    const ms = profileTimestampMillis(row?.createdAt) || Number(row?.clientCreatedAt) || 0;
    if (!ms) return "";
    return new Date(ms).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

function speechSibling(rows, row, language) {
    const target = String(language || "").toLowerCase();
    return (rows || []).some(item => item.kind === "speech" && item.sourceTranscriptId === row?.id && String(item.language || "").toLowerCase() === target);
}

function renderTranscript(rows) {
    const list = $("transcriptList");
    if (!rows.length) {
        list.innerHTML = '<p class="transcript-empty">Transcript lines from Customer 1, Customer 2, and the translator will appear here.</p>';
        renderAudioTranscript(rows);
        return;
    }
    const localLanguage = [...rows].reverse().find(row => row.kind !== "speech" && row.speakerId === currentUser?.uid && row.language);
    if (localLanguage) updateDetectedLanguage(localLanguage.language, localLanguage.languageConfidence);
        updateParticipantLanguageBadges(rows);
    list.innerHTML = "";
    for (const row of rows) {
        const item = document.createElement("div");
        item.className = row.kind === "speech" ? "transcript-line is-speech" : "transcript-line";
        const speaker = document.createElement("div"); speaker.className = "transcript-speaker";
        const name = document.createElement("span"); name.textContent = row.speakerName || "Participant";
        const role = document.createElement("span"); role.className = "transcript-role"; role.textContent = formatTranscriptRole(row.speakerRole);
        const when = document.createElement("time"); when.className = "transcript-time"; when.dateTime = row.createdAt || ""; when.textContent = transcriptTimeLabel(row);
        const language = document.createElement("span"); language.className = "transcript-language";
        const confidence = normalizeLanguageConfidence(row.languageConfidence);
        language.textContent = row.language ? `${detectedLanguageLabel(row.language)}${row.kind === "speech" || confidence === null ? "" : ` · ${Math.round(confidence * 100)}%`}` : "Language pending";
        const state = document.createElement("span"); state.className = "transcript-state"; state.textContent = row.localOnly ? "On this device" : row.isFinal === false ? "Partial" : "Final";
        const text = document.createElement("p"); text.className = "transcript-text"; text.textContent = row.text || "";
        const viewerLanguage = callExperience?.viewerLanguage?.() || "en";
        const translated = row.kind === "speech" ? "" : (row.translations?.[viewerLanguage]?.text || "");
        const source = String(row.language || "").toLowerCase();
        const status = document.createElement("span"); status.className = "transcript-status";
        if (row.kind === "speech") status.textContent = "Speech transcript";
        else if (speechSibling(rows, row, viewerLanguage)) status.textContent = "Original";
        else if (translated && translated !== row.text) { status.textContent = "Translated"; }
        else if (source && source !== viewerLanguage) { status.className += " is-pending"; status.textContent = "Translating…"; callExperience?.ensureTranslation(row); }
        else status.textContent = "Original";
        speaker.append(name, role, when, language, state, status); item.append(speaker, text);
        if (translated && translated !== row.text && !speechSibling(rows, row, viewerLanguage)) { const translation = document.createElement("p"); translation.className = "transcript-translation"; translation.textContent = translated; item.append(translation); }
        list.appendChild(item);
    }
    list.scrollTop = list.scrollHeight;
    renderAudioTranscript(rows);
}

function updateParticipantLanguageBadges(rows) {
    const latestBySpeaker = new Map();
    for (const row of rows) {
        if (!row.language || row.kind === "speech") continue;
        rememberDetectedLanguage(row.language, row.languageConfidence);
        if (row.speakerId) latestBySpeaker.set(row.speakerId, row);
    }
    document.querySelectorAll(".video-card[data-speaker]").forEach(card => {
        const row = latestBySpeaker.get(card.dataset.speaker);
        let badge = card.querySelector(".video-language");
        if (!row) { badge?.remove(); return; }
        if (!badge) { badge = document.createElement("span"); badge.className = "video-language"; card.querySelector(".video-label")?.appendChild(badge); }
        const confidence = normalizeLanguageConfidence(row.languageConfidence);
        badge.textContent = `${detectedLanguageLabel(row.language)}${confidence === null ? "" : ` ${Math.round(confidence * 100)}%`}`;
    });
}

function formatTranscriptRole(role) {
    if (role === "caller") return "Customer 1";
    if (role === "receiver") return "Customer 2";
    if (role === "translator") return "Translator";
    if (role === "guest") return "Guest";
    if (role === "ai") return "AI interpreter";
    return role || "Participant";
}

async function requestTranslator(event) {
    event?.preventDefault();
    if (!activeCallId) return;
    const languages = [...selectedRequestLanguages];
    if (!languages.length) {
        $("translatorRequestError").textContent = "Choose at least one language to continue.";
        $("translatorRequestError").classList.remove("hidden");
        return;
    }
    const submit = $("submitTranslatorRequest");
    submit.disabled = true;
    submit.textContent = "Finding…";
    try {
        await loadAvailableRequestMatches();
        const count = requestMatchProfiles.length;
        $("callStatus").textContent = count
            ? `${Math.min(3, count)} translator${count === 1 ? "" : "s"} match ${languages.join(", ")}. Click one to invite them.`
            : `No translator matches ${languages.join(", ")} yet.`;
        $("requestLanguageSearchPanel").open = false;
        $("requestBestMatchList")?.scrollIntoView({ block: "nearest" });
    } catch (error) {
        $("translatorRequestError").textContent = error.message || "Translator matching is unavailable right now.";
        $("translatorRequestError").classList.remove("hidden");
        $("requestLanguageSearchPanel").open = true;
    } finally {
        submit.textContent = "Find translators";
        submit.disabled = selectedRequestLanguages.size === 0;
    }
}
function setToolLabel(id, label, pressed, title) {
    const button = $(id);
    if (!button) return;
    button.setAttribute("aria-pressed", String(pressed));
    button.title = title;
    button.setAttribute("aria-label", title);
    const text = button.querySelector(".tool-label");
    if (text) text.textContent = label;
}
function tracksInCall(kind) {
    const tracks = [];
    const add = track => {
        if (track?.kind === kind && track.readyState === "live" && !tracks.includes(track)) tracks.push(track);
    };
    for (const track of localStream?.getTracks?.() || []) add(track);
    for (const pc of peerConnections.values()) {
        for (const sender of pc.getSenders?.() || []) add(sender.track);
    }
    return tracks;
}

function playRemoteMedia() {
    document.querySelectorAll("#callView audio.remote-audio, #callView video").forEach(element => {
        if (element.classList?.contains("remote-audio")) element.muted = false;
        element.play?.().catch(() => {});
    });
}

function toggleMute() {
    const tracks = tracksInCall("audio");
    if (!tracks.length) return;
    const enabled = !tracks[0].enabled;
    for (const track of tracks) track.enabled = enabled;
    setToolLabel("muteButton", enabled ? "Mute" : "Unmute", !enabled, enabled ? "Mute microphone" : "Unmute microphone");
    syncAudioMute(!enabled);
    if (enabled) playRemoteMedia();
    callExperience?.persistPresence()?.catch(error => console.warn(error));
}
async function toggleCamera() {
    if (callExperience?.isAvatar?.()) {
        await callExperience.activateCamera();
        setCallPresentation("video");
        return;
    }
    const tracks = tracksInCall("video").filter(track => track.readyState === "live");
    if (!tracks.length) {
        const started = await restartLocalCamera();
        if (!started) {
            if ($("callStatus")) $("callStatus").textContent = "Camera is unavailable on this device.";
            setCallPresentation("audio");
            return;
        }
        setToolLabel("cameraButton", "Camera", false, "Turn camera off");
        setCallPresentation("video");
        callExperience?.persistPresence()?.catch(error => console.warn(error));
        return;
    }
    const enabled = !tracks[0].enabled;
    if (enabled) {
        for (const track of tracks) track.enabled = true;
        setCallPresentation("video");
    } else {
        setCallPresentation("audio");
        suppressCameraRestart = true;
        try {
            for (const track of tracks) {
                track.stop();
                localStream?.removeTrack(track);
            }
            for (const pc of peerConnections.values()) senderFor(pc, "video")?.replaceTrack(null).catch(() => {});
        } finally {
            suppressCameraRestart = false;
        }
    }
    setToolLabel("cameraButton", enabled ? "Camera" : "Camera off", !enabled, enabled ? "Turn camera off" : "Turn camera on");
    callExperience?.markCamera?.(enabled);
    callExperience?.persistPresence()?.catch(error => console.warn(error));
}
async function endCall() {
    const callId = activeCallId;
    lastSessionSnapshot = captureSessionSnapshot();
    rememberEndedCall(callId);
    cleanupCall(); show("dashboardView"); openDashboardPanel("summary");
    if (callId) {
        try {
            await apiFetch(`/api/calls/${encodeURIComponent(callId)}/leave`, { method: "POST", body: "{}" });
        } catch (error) {
            console.warn("Leaving the call on the server failed", error);
        }
    }
    loadConversationHistory();
}
function cleanupListeners() { callUnsubs.forEach(u => u()); callUnsubs = []; }
function cleanupCall(stopMedia = true) {
    const endingCallId = activeCallId;
    stopTranscription();
    if (signalingSocket?.readyState === WebSocket.OPEN) {
        for (const uid of peerConnections.keys()) try { sendSignal("hangup", uid, {}); } catch (_) { /* best effort */ }
    }
    if (signalingSocket) { signalingSocket.onclose = null; signalingSocket.close(); signalingSocket = null; }
    signalingReady = null; signalingCursor = 0; callMembershipKey = ""; pendingSignals.clear(); pendingIceCandidates.clear(); peerJobs.clear();
    window.clearTimeout(captionBroadcastTimer); captionBroadcastTimer = null; pendingCaptionText = ""; lastCaptionText = "";
    cleanupListeners(); peerConnections.forEach(pc => pc.close()); peerConnections.clear();
    peerProfiles.clear();
    callFacePhotos.clear();
    callFacePhotoRequests.clear();
    peerDebug.clear();
    rosterParticipants = [];
    rosterTranscripts = [];
    if ($("callRosterList")) { $("callRosterList").replaceChildren(); $("callRosterList").dataset.summary = ""; }
    if ($("callRosterStatus")) $("callRosterStatus").textContent = "Waiting for participants";
    stopCameraRelay();
    document.querySelectorAll("#callView img.relay-camera").forEach(image => {
        if (image.dataset.objectUrl) URL.revokeObjectURL(image.dataset.objectUrl);
    });
    document.querySelectorAll("[data-peer]").forEach(e => e.remove());
    if (stopMedia && localStream) {
        activeCallId = null;
        localStream.getTracks().forEach(t => t.stop());
        localStream = null;
        if ($("localVideo")) $("localVideo").srcObject = null;
        if ($("localCapture")) $("localCapture").srcObject = null;
    }
    callExperience?.cleanup();
    document.body.classList.remove("video-call");
    activeCallId = null; currentCallRole = null;
    activeTranslatorConnected = false;
    if (endingCallId) for (const key of [...routedLanguageCalls]) if (key.startsWith(`${endingCallId}:`)) routedLanguageCalls.delete(key);
    resetDetectedLanguage();
    $("requestTranslatorButton").disabled = false;
    $("requestTranslatorButton").title = "";
    $("muteButton").setAttribute("aria-pressed", "false");
    $("cameraButton").setAttribute("aria-pressed", "false");
}


function cleanupDashboardListeners() {
    dashboardUnsubs.forEach(unsub => unsub());
    dashboardUnsubs = [];
    pendingIncomingCall = null;
    if (!$("incomingCallModal")?.classList.contains("hidden")) closeModal("incomingCallModal");
}

function clearPendingIncomingCall() {
    pendingIncomingCall = null;
    if (!$("incomingCallModal")?.classList.contains("hidden")) closeModal("incomingCallModal");
}

function newestPendingCall(snapshot) {
    return snapshot.docs
        .filter(callDoc => callDoc.data().status === "ringing")
        .sort((left, right) => callMillis(right.data()) - callMillis(left.data()))[0] || null;
}

function handleDashboardListenerError(kind, error) {
    console.error(`[FiniSpeak incoming][${kind}] listener failed`, {
        code: error?.code || null,
        message: error?.message || String(error),
        online: navigator.onLine
    }, error);
    clearPendingIncomingCall();
    $("dashboardStatus").textContent = `Could not check for pending calls: ${error?.message || "Please refresh and try again."}`;
}

function startDashboardListeners() {
    cleanupDashboardListeners();
    if (!currentUser || !currentProfile) return;

    const refresh = async () => {
      const profile = currentProfile;
      if (!currentUser || !profile) return;
      if ($("dashboardMessages")?.classList.contains("hidden")) refreshChatBadge();
      try {
        let sessions = [];
        let pending = null;
        if (profile.role === "translator") {
          try {
            const rows = (await apiFetch("/api/calls/pending")).calls || [];
            pending = rows.find(call => call.purpose === "translator_chat" && call.receiverId === currentUser.uid && call.status === "ringing")
              || rows.find(call => call.invitedTranslatorId === currentUser.uid)
              || null;
          } catch (error) {
            console.warn("Pending interpreter calls unavailable", error);
          }
        }
        sessions = (await apiFetch("/api/sessions")).sessions || [];
        if (profile.role === "translator") renderScheduledSessionList(sessions);
        if (!pending) {
          pending = sessions.filter(call => call.receiverId === currentUser.uid && call.status === "ringing").sort((a, b) => callMillis(b) - callMillis(a))[0] || null;
        }
        if (!pending || activeCallId) {
                if (!activeCallId) {
                    try {
                        const invite = ((await apiFetch("/api/calls/invitations")).calls || [])[0];
                        if (invite) {
                            pendingIncomingCall = { ...invite, kind: "invite" };
                            $("incomingCallEyebrow").textContent = "Call invitation";
                            $("incomingCallTitle").textContent = `${invite.callerName || "Someone"} invited you`;
                            $("incomingCallDetails").textContent = "Accept to join this FiniSpeak call. Everyone already connected stays on the call.";
                            $("acceptIncomingCall").textContent = "Join call";
                            openModal("incomingCallModal");
                            return;
                        }
                    } catch (error) { console.warn("Call invitations unavailable", error); }
                }
                clearPendingIncomingCall();
                return;
            }
        if (["customer", "admin"].includes(profile.role)) {
            pendingIncomingCall = { ...pending, kind: "customer" };
            $("incomingCallEyebrow").textContent = "Incoming FiniSpeak call";
            $("incomingCallTitle").textContent = `${pendingIncomingCall.callerName || "A participant"} is calling you`;
            $("incomingCallDetails").textContent = "Accept to connect. Live transcription starts after you join the call.";
            $("acceptIncomingCall").textContent = "Accept call";
            openModal("incomingCallModal");
        } else if (profile.role === "translator") {
            const directChat = pending.purpose === "translator_chat" && pending.receiverId === currentUser.uid;
            if (directChat) {
                pendingIncomingCall = { ...pending, kind: "direct-translator" };
                $("incomingCallEyebrow").textContent = "Incoming translator chat";
                $("incomingCallTitle").textContent = `${pending.callerName || "Someone"} is calling you`;
                $("incomingCallDetails").textContent = "Accept to chat directly. No other customer is included in this call.";
                $("acceptIncomingCall").textContent = "Accept call";
                openModal("incomingCallModal");
                return;
            }
            const directInvite = pending.invitedTranslatorId && pending.invitedTranslatorId === currentUser.uid;
            if (!directInvite) {
                clearPendingIncomingCall();
                return;
            }
            pendingIncomingCall = { ...pending, kind: "translator" };
            $("incomingCallEyebrow").textContent = directInvite ? "Incoming FiniSpeak call" : "Interpretation request";
            $("incomingCallTitle").textContent = directInvite
                ? `${pending.callerName || "Someone"} is calling you`
                : "A call needs a translator";
            $("incomingCallDetails").textContent = directInvite
                ? `${pending.callerName || "Someone"} invited you to interpret this call. Accept to join as the translator.`
                : `${pending.callerName || "Customer 1"} and ${pending.receiverName || "Customer 2"} are requesting interpretation.`;
            $("translatorRequestStatus").textContent = "New interpretation request waiting — open it to join the call.";
            $("acceptIncomingCall").textContent = directInvite ? "Accept" : "Join Call";
            openModal("incomingCallModal");
        }
      } catch (error) { handleDashboardListenerError("poll", error); }
    };
    refresh();
    const timer = window.setInterval(refresh, 2500);
    dashboardUnsubs.push(() => window.clearInterval(timer));
}

async function acceptIncomingCall() {
    if (!pendingIncomingCall) return;
    const pending = pendingIncomingCall;
    pendingIncomingCall = null;
    closeModal("incomingCallModal");
    try {
        if (pending.kind === "invite") {
            await apiFetch(`/api/calls/${encodeURIComponent(pending.id)}/experience`, {
                method: "POST", body: JSON.stringify({ action: "accept-invite" })
            });
        } else if (["customer", "direct-translator"].includes(pending.kind)) {
            await apiFetch(`/api/calls/${encodeURIComponent(pending.id)}/state`, {
                method: "PATCH", body: JSON.stringify({ state: "connected" })
            });
        }
        await joinCall(pending.id);
    } catch (error) {
        $("dashboardStatus").textContent = error.message;
    }
}

async function declineIncomingCall() {
    if (!pendingIncomingCall) return;
    const pending = pendingIncomingCall;
    pendingIncomingCall = null;
    closeModal("incomingCallModal");
    try {
        if (pending.kind === "invite") {
            await apiFetch(`/api/calls/${encodeURIComponent(pending.id)}/experience`, {
                method: "POST", body: JSON.stringify({ action: "decline-invite" })
            });
        } else if (["customer", "direct-translator"].includes(pending.kind)) {
            await apiFetch(`/api/calls/${encodeURIComponent(pending.id)}/state`, {
                method: "PATCH", body: JSON.stringify({ state: "declined" })
            });
        } else if (pending.kind === "translator") {
            await apiFetch(`/api/calls/${encodeURIComponent(pending.id)}/translator-request`, {
                method: "POST", body: JSON.stringify({ decline: true })
            });
        }
    } catch (error) {
        $("dashboardStatus").textContent = error.message;
    }
}

async function loadConversationHistory() {
    if (!currentUser) return;
    const history = $("conversationHistory");
    history.innerHTML = '<p class="transcript-empty">Loading conversations…</p>';
    try {
        const payload = await apiFetch("/api/sessions");
        historyCalls.clear();
        (payload.sessions || []).forEach(call => historyCalls.set(call.id, call));
        const rows = [...historyCalls.values()]
            .filter(call => ["connected", "ended"].includes(call.status) || call.startedAt)
            .sort((a, b) => callMillis(b) - callMillis(a));
        renderConversationHistory(rows);
    } catch (error) {
        history.innerHTML = `<p class="status">Could not load conversation history: ${escapeHtml(error.message)}</p>`;
    }
}

function callMillis(call) {
    return profileTimestampMillis(call.endedAt) || profileTimestampMillis(call.startedAt) || profileTimestampMillis(call.createdAt) || 0;
}

function renderConversationHistory(rows) {
    const history = $("conversationHistory");
    if (!rows.length) {
        history.innerHTML = '<p class="transcript-empty">No previous conversations yet.</p>';
        return;
    }
    history.innerHTML = "";
    for (const call of rows) {
        const row = document.createElement("article");
        row.className = "conversation-row";
        const button = document.createElement("button");
        button.type = "button";
        button.className = "conversation-item";
        const other = currentProfile.role === "translator"
            ? `${call.callerName || "Customer 1"} ↔ ${call.receiverName || "Customer 2"}`
            : (currentUser.uid === call.callerId ? call.receiverName : call.callerName) || "FiniSpeak customer";
        const date = timestampDate(call.startedAt) || timestampDate(call.createdAt);
        const dateText = date ? date.toLocaleString() : "Previous call";
        button.innerHTML = `<strong>${escapeHtml(other)}</strong><span class="conversation-meta">${escapeHtml(dateText)} · View transcript</span>`;
        button.onclick = () => openHistoryTranscript(call);
        row.appendChild(button);
        if (call.status === "ended" && call.translatorId && currentProfile.role !== "translator") {
            const reviewButton = document.createElement("button");
            reviewButton.type = "button";
            reviewButton.className = "secondary conversation-review-button";
            reviewButton.textContent = "Review interpreter";
            reviewButton.onclick = () => openReviewModal(call);
            row.appendChild(reviewButton);
        }
        history.appendChild(row);
    }
}

function openReviewModal(call) {
    reviewCall = call;
    $("reviewRating").value = "5";
    $("reviewText").value = "";
    $("reviewStatus").textContent = "";
    openModal("reviewModal");
}

async function submitInterpreterReview(event) {
    event.preventDefault();
    if (!reviewCall?.translatorId) return;
    const button = $("submitReview");
    button.disabled = true;
    $("reviewStatus").textContent = "Submitting review…";
    try {
        await apiFetch(`/api/reviews/interpreters/${encodeURIComponent(reviewCall.translatorId)}`, {
            method: "POST",
            body: JSON.stringify({
                callId: reviewCall.id,
                rating: Number($("reviewRating").value),
                text: $("reviewText").value.trim()
            })
        });
        $("reviewStatus").textContent = "Thank you. Your review is now visible.";
        window.setTimeout(() => closeModal("reviewModal"), 700);
    } catch (error) {
        $("reviewStatus").textContent = error.message;
    } finally {
        button.disabled = false;
    }
}

let historyTranscriptRequest = 0;

async function openHistoryTranscript(call) {
    if (!call?.id || (activeCallId && document.body.classList.contains("in-call"))) return;
    const request = ++historyTranscriptRequest;
    historyTranscriptCall = call;
    renderKeyMoments(call);
    $("historyTranscriptTitle").textContent = "Call transcript";
    const date = timestampDate(call.startedAt) || timestampDate(call.createdAt);
    $("historyTranscriptMeta").textContent = date ? date.toLocaleString() : "Previous conversation";
    if ($("historyTranscriptPolicy")) $("historyTranscriptPolicy").textContent = "Finalized transcript text is saved only after someone on the call allows it. Raw microphone audio is not stored. Saved text is deleted after 90 days, and anyone on the call can delete it sooner.";
    const list = $("historyTranscriptList");
    list.innerHTML = '<p class="app-transcript-empty">Loading transcript…</p>';
    if ($("dashboardView")?.classList.contains("hidden")) show("dashboardView");
    openDashboardPanel("transcript");
    $("historyTranscriptTitle")?.focus();
    try {
        const payload = await apiFetch(`/api/calls/${encodeURIComponent(call.id)}/transcripts`);
        if (request !== historyTranscriptRequest) return;
        const rows = payload.transcripts || [];
        if (payload.policy?.statement && $("historyTranscriptPolicy")) $("historyTranscriptPolicy").textContent = payload.policy.statement;
        rows.sort((a, b) => (profileTimestampMillis(a.createdAt) || a.clientCreatedAt || 0) - (profileTimestampMillis(b.createdAt) || b.clientCreatedAt || 0));
        renderTranscriptInto(list, rows);
    } catch (error) {
        if (request !== historyTranscriptRequest) return;
        list.innerHTML = `<p class="app-transcript-empty">Could not load transcript: ${escapeHtml(error.message)}</p>`;
    }
}

function renderTranscriptInto(list, rows) {
    if (!rows.length) {
        list.innerHTML = '<p class="app-transcript-empty">No transcript was saved for this conversation.</p>';
        return;
    }
    list.replaceChildren();
    for (const row of rows) {
        const item = document.createElement("article");
        item.className = "app-transcript-line";
        if (row.kind === "speech") item.classList.add("is-speech");
        const speaker = document.createElement("div");
        speaker.className = "app-transcript-speaker";
        const name = document.createElement("span");
        name.className = "app-transcript-name";
        name.textContent = row.speakerName || "Participant";
        const role = document.createElement("span");
        role.className = "app-transcript-role";
        role.textContent = formatTranscriptRole(row.speakerRole);
        const when = document.createElement("time");
        when.className = "app-transcript-time";
        when.textContent = transcriptTimeLabel(row);
        const language = document.createElement("span");
        language.className = "app-transcript-language";
        language.textContent = row.kind === "speech" ? `${detectedLanguageLabel(row.language)} speech transcript` : detectedLanguageLabel(row.language || "");
        const text = document.createElement("p");
        text.className = "app-transcript-text";
        text.textContent = row.text || "";
        speaker.append(name, role, when, language);
        item.append(speaker, text);
        list.appendChild(item);
    }
}

let conceptCategory = "Education";
let lastSessionSnapshot = null;
let lastEndedCall = null;
let conceptMatchedProfile = null;

function setConceptCategory(name) {
    conceptCategory = name || "Education";
    document.querySelectorAll("[data-discovery-category], [data-concept-category], [data-audio-category], [data-landing-category]").forEach(button => {
        const value = button.dataset.discoveryCategory || button.dataset.conceptCategory || button.dataset.audioCategory || button.dataset.landingCategory;
        const active = value === conceptCategory;
        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", String(active));
    });
}

function openConceptCategory(name) {
    setConceptCategory(name);
    if (!currentUser) {
        openAuth(false, "customer");
        $("authStatus").textContent = "Log in to browse sessions by category.";
        return;
    }
    if ($("dashboardView")?.classList.contains("hidden")) show("dashboardView");
    if (name === "Education") openDashboardPanel("classroom");
    else if (name === "Personal") openDashboardPanel("home");
    else {
        openDashboardPanel("directory");
        if ($("directorySearch")) $("directorySearch").value = "Business";
        filterInterpreterDirectory();
    }
}

function renderConceptMapSheet(profile) {
    const sheet = $("conceptMapSheet");
    if (!sheet) return;
    if (!profile) { sheet.hidden = true; return; }
    sheet.hidden = false;
    sheet.dataset.profileId = profile.id || "";
    $("conceptSheetName").textContent = profile.displayName || "Interpreter";
    const rating = Number(profile.rating || 0);
    const filled = rating ? Math.max(1, Math.min(5, Math.round(rating))) : 5;
    $("conceptSheetStars").textContent = `${"★".repeat(filled)}${"☆".repeat(5 - filled)}`;
    const meta = [...(profile.dialects || []), ...(profile.specialties || []), ...(profile.languages || [])].filter(Boolean).slice(0, 2).join(" · ");
    $("conceptSheetMeta").textContent = meta || "Verified interpreter";
    setProfileAvatar($("conceptSheetAvatar"), profile);
}

function renderConceptProfile(profile) {
    const languages = $("conceptProfileLanguages");
    if (!languages) return;
    const badges = [...(profile.languages || []), ...(profile.dialects || [])].filter(Boolean).slice(0, 3);
    languages.innerHTML = badges.map(value => `<span>${escapeHtml(value)}</span>`).join("");
    const availability = profile.availability || {};
    const time = availability.start && availability.end
        ? `${formatAvailabilityTime(availability.start)} – ${formatAvailabilityTime(availability.end)}`
        : "11:00 AM – 12:00 PM";
    $("conceptProfileSchedule").textContent = time;
    const slotMeta = $("profileSlotMeta");
    if (slotMeta) {
        const detail = [...(profile.specialties || []), ...(profile.languages || [])].filter(Boolean).slice(0, 2).join(", ");
        slotMeta.textContent = detail || "Live session";
    }
    const today = new Date();
    $("conceptProfileWeek").innerHTML = Array.from({ length: 5 }, (_, offset) => {
        const date = new Date(today);
        date.setDate(today.getDate() + offset);
        const label = offset === 0 ? "Today" : String(date.getDate());
        return offset === 0 ? `<b>${label}</b>` : `<span>${label}</span>`;
    }).join("");
}

function formatSessionClock(date) {
    return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function updateReturnToCall() {
    $("returnToCall")?.classList.toggle("hidden", !activeCallId || document.body.classList.contains("in-call"));
}

function setCallPresentation(mode) {
    document.body.classList.toggle("video-call", mode === "video");
    $("audioVideoButton")?.setAttribute("aria-pressed", String(mode === "video"));
    syncAudioCallFaces();
}

function syncAudioMute(muted) {
    const button = $("audioMuteButton");
    if (!button) return;
    button.classList.toggle("is-muted", muted);
    button.setAttribute("aria-pressed", String(muted));
    button.setAttribute("aria-label", muted ? "Unmute microphone" : "Mute microphone");
}

function remoteCallFace() {
    const entry = [...peerProfiles.entries()].find(([, profile]) => profile?.displayName);
    if (entry) return { ...entry[1], id: entry[1].id || entry[0] };
    return activeDirectoryProfile || selectedInterpreterProfile || null;
}

function selfCallFace() {
    const id = currentUser?.uid || currentProfile?.id || currentProfile?.uid || currentInterpreterProfile?.id || currentInterpreterProfile?.uid || "";
    return {
        ...(currentProfile || {}),
        id,
        displayName: currentProfile?.displayName || "You",
        photoUrl: currentInterpreterProfile?.photoUrl || currentProfile?.photoUrl || ""
    };
}

function syncAudioCallFaces() {
    const other = remoteCallFace() || { displayName: "Waiting" };
    const self = selfCallFace();
    if ($("audioCallNameA")) $("audioCallNameA").textContent = other?.displayName || "Waiting";
    if ($("audioCallNameB")) $("audioCallNameB").textContent = self.displayName || "You";
    setProfileAvatar($("audioCallAvatarA"), other || { displayName: "Waiting" });
    setProfileAvatar($("audioCallAvatarB"), self);
    setProfileAvatar($("localFacePhoto"), self);
    document.querySelectorAll("[data-peer]").forEach(card => {
        const id = card.dataset.peer;
        setProfileAvatar(card.querySelector(".call-face-photo"), { ...(peerProfiles.get(id) || {}), id });
    });
    ensureCallFacePhoto(other);
    ensureCallFacePhoto(self);
}

function renderAudioTranscript(rows) {
    const list = $("audioTranscript");
    if (!list) return;
    if (!rows?.length) {
        list.innerHTML = '<p class="audio-transcript-empty">Live transcription appears here as people speak.</p>';
        return;
    }
    const viewerLanguage = callExperience?.viewerLanguage?.() || "en";
    list.replaceChildren();
    for (const row of rows) {
        const name = String(row.speakerName || "Speaker").trim().split(/\s+/)[0] || "Speaker";
        const line = document.createElement("div");
        line.className = "audio-line";
        const speaker = document.createElement("span");
        speaker.className = "audio-speaker";
        speaker.textContent = name;
        const when = document.createElement("time");
        when.className = "transcript-time";
        when.textContent = transcriptTimeLabel(row);
        const text = document.createElement("p");
        text.textContent = row.text || "";
        line.append(speaker, when, text);
        if (row.kind === "speech") line.classList.add("is-speech");
        list.appendChild(line);
        const translated = row.kind === "speech" || speechSibling(rows, row, viewerLanguage) ? "" : (row.translations?.[viewerLanguage]?.text || "");
        if (translated && translated !== row.text) {
            const extra = document.createElement("div");
            extra.className = "audio-line is-translation";
            const who = document.createElement("span");
            who.className = "audio-speaker";
            who.textContent = name;
            const copy = document.createElement("p");
            copy.textContent = translated;
            extra.append(who, copy);
            list.appendChild(extra);
        }
    }
    list.scrollTop = list.scrollHeight;
}

async function flagKeyMoment() {
    if (!activeCallId) {
        setConceptFlagChecked(false);
        if ($("conceptFlagStatus")) $("conceptFlagStatus").textContent = "Join a call before flagging a moment.";
        return;
    }
    const when = $("audioCallDuration")?.textContent || $("callDuration")?.textContent || "";
    const latest = [...rosterTranscripts].reverse().find(row => row.kind !== "speech" && row.text);
    const id = `moment-${Date.now()}`;
    try {
        const result = await apiFetch(`/api/calls/${encodeURIComponent(activeCallId)}/experience`, {
            method: "POST",
            body: JSON.stringify({
                action: "flag-moment",
                id,
                elapsedLabel: when,
                transcriptId: latest?.id || "",
                speakerName: latest?.speakerName || "",
                text: latest?.text || ""
            })
        });
        activeCallRecord = result.call;
        renderKeyMoments(result.call);
        $("audioFlagMoment")?.classList.add("is-flagged");
        setConceptFlagChecked(true);
        if ($("conceptFlagStatus")) $("conceptFlagStatus").textContent = "Flagged for follow-up.";
        if ($("callNotesStatus")) $("callNotesStatus").textContent = "Flagged moment saved for follow-up.";
    } catch (error) {
        setConceptFlagChecked(false);
        if ($("conceptFlagStatus")) $("conceptFlagStatus").textContent = error.message;
        if ($("callNotesStatus")) $("callNotesStatus").textContent = error.message;
    }
}

function renderKeyMoments(call) {
    const moments = Array.isArray(call?.keyMoments) ? call.keyMoments : [];
    const targets = new Set([$("keyMomentList")]);
    if (historyTranscriptCall?.id && historyTranscriptCall.id === call?.id) targets.add($("historyKeyMomentList"));
    if (lastCallRecord?.id && lastCallRecord.id === call?.id) targets.add($("summaryKeyMomentList"));
    for (const list of targets) fillKeyMomentList(list, moments, call?.id);
    if (call?.id === activeCallId && !moments.some(item => item.followUp !== false)) $("audioFlagMoment")?.classList.remove("is-flagged");
}

function fillKeyMomentList(list, moments, callId) {
    if (!list) return;
    list.replaceChildren();
    if (!moments.length) {
        const empty = document.createElement("li");
        empty.className = "key-moment-empty";
        empty.textContent = "Flagged moments show up here for follow-up.";
        list.appendChild(empty);
        return;
    }
    for (const moment of moments) {
        const item = document.createElement("li");
        item.classList.toggle("is-resolved", moment.followUp === false);
        const title = document.createElement("strong");
        const when = [moment.elapsedLabel, transcriptTimeLabel(moment)].filter(Boolean).join(" · ");
        title.textContent = when || "Flagged moment";
        const text = document.createElement("p");
        text.textContent = [moment.speakerName, moment.text].filter(Boolean).join(": ") || "Marked for follow-up.";
        item.append(title, text);
        if (moment.followUp !== false && callId) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "secondary";
            button.textContent = "Done";
            button.onclick = () => resolveKeyMoment(callId, moment.id);
            item.appendChild(button);
        } else if (moment.followUp === false) {
            const state = document.createElement("span");
            state.textContent = "Resolved";
            item.appendChild(state);
        }
        list.appendChild(item);
    }
}

async function resolveKeyMoment(callId, momentId) {
    const result = await apiFetch(`/api/calls/${encodeURIComponent(callId)}/experience`, {
        method: "POST",
        body: JSON.stringify({ action: "resolve-moment", id: momentId })
    });
    if (lastCallRecord?.id === result.call?.id) lastCallRecord = result.call;
    if (historyTranscriptCall?.id === result.call?.id) historyTranscriptCall = result.call;
    renderKeyMoments(result.call);
    setConceptFlagChecked((result.call?.keyMoments || []).some(item => item.followUp !== false));
}

function setConceptFlagChecked(checked) {
    const box = $("conceptFlagMoment");
    if (!box || box.checked === checked) return;
    box.dataset.syncing = "true";
    box.checked = checked;
    box.dataset.syncing = "false";
}

function resolveLatestKeyMoment() {
    const call = activeCallRecord || lastCallRecord;
    const latest = [...(call?.keyMoments || [])].reverse().find(item => item.followUp !== false);
    if (!activeCallId || !call?.id || !latest) {
        if ($("conceptFlagStatus") && !activeCallId) $("conceptFlagStatus").textContent = "Join a call before flagging a moment.";
        return;
    }
    resolveKeyMoment(call.id, latest.id);
}

function syncTranscriptConsent(call) {
    transcriptConsentGranted = call?.transcriptConsent?.granted === true;
    const box = $("transcriptConsent");
    if (box && document.activeElement !== box) box.checked = transcriptConsentGranted;
    const status = $("transcriptConsentStatus");
    const days = Number(call?.transcriptConsent?.retentionDays || 90);
    if (status) {
        status.textContent = transcriptConsentGranted
            ? `Finalized speech text is saved for people on this call. Raw audio is not stored. Text is deleted after ${days} days unless someone deletes it sooner.`
            : "Finalized speech stays on this device until someone on the call allows saving. Raw audio is not stored.";
    }
}

async function setTranscriptConsent(granted) {
    if (!activeCallId) return;
    try {
        const result = await apiFetch(`/api/calls/${encodeURIComponent(activeCallId)}/experience`, {
            method: "POST",
            body: JSON.stringify({ action: "set-transcript-consent", granted })
        });
        syncTranscriptConsent(result.call);
        if (granted) await flushLocalTranscripts(activeCallId);
    } catch (error) {
        if ($("transcriptConsent")) $("transcriptConsent").checked = transcriptConsentGranted;
        if ($("transcriptConsentStatus")) $("transcriptConsentStatus").textContent = error.message;
    }
}

async function flushLocalTranscripts(callId) {
    const pending = rosterTranscripts.filter(row => row.localOnly && row.kind !== "speech");
    for (const row of pending) {
        const result = await apiFetch(`/api/calls/${encodeURIComponent(callId)}/transcripts`, {
            method: "POST",
            headers: { "Idempotency-Key": row.id },
            body: JSON.stringify({
                id: row.id,
                language: row.language,
                languageConfidence: row.languageConfidence,
                primaryLanguage: row.primaryLanguage,
                primaryLanguageConfidence: row.primaryLanguageConfidence,
                languageSampleCount: row.languageSampleCount,
                languageConfirmationRequired: row.languageConfirmationRequired,
                text: row.text,
                isFinal: true,
                processingMode: row.processingMode,
                processingGeneration: row.processingGeneration,
                performance: row.performance,
                clientCreatedAt: row.clientCreatedAt,
                captionLanguage: callExperience?.viewerLanguage?.() || null
            })
        });
        if (result.transcript) mergeLiveTranscript(result.transcript);
        if (result.speechTranscript) mergeLiveTranscript(result.speechTranscript);
    }
}

async function deleteSavedTranscript(callId) {
    if (!callId) return;
    if (!window.confirm("Delete the saved transcript for this call? Live captions on this device stay until you leave.")) return;
    try {
        await apiFetch(`/api/calls/${encodeURIComponent(callId)}/transcripts`, { method: "DELETE" });
        if (activeCallId === callId) {
            rosterTranscripts = rosterTranscripts.filter(row => row.localOnly);
            renderTranscript(rosterTranscripts);
        }
        if (historyTranscriptCall?.id === callId) {
            $("historyTranscriptList").innerHTML = '<p class="app-transcript-empty">The saved transcript was deleted.</p>';
        }
        if ($("transcriptConsentStatus")) $("transcriptConsentStatus").textContent = "Saved transcript text was deleted.";
        if ($("historyTranscriptPolicy")) $("historyTranscriptPolicy").textContent = "Saved transcript text was deleted. Raw microphone audio was not stored.";
    } catch (error) {
        if ($("transcriptConsentStatus")) $("transcriptConsentStatus").textContent = error.message;
        if ($("historyTranscriptPolicy")) $("historyTranscriptPolicy").textContent = error.message;
    }
}

function formatInterpreterPrice(profile) {
    if (profile?.ratePerMinute === null || profile?.ratePerMinute === undefined || profile?.ratePerMinute === "") return "Price not published";
    const rate = Number(profile.ratePerMinute);
    if (!Number.isFinite(rate) || rate < 0) return "Price not published";
    return `$${rate.toFixed(2)} per minute`;
}

async function renderSessionInterpreter(call) {
    const card = $("sessionInterpreterCard");
    if (!card) return;
    const connected = call?.translationStatus === "connected" && call?.translatorId;
    const interpreterId = connected ? call.translatorId : (call?.invitedTranslatorId || "");
    if (!interpreterId) {
        card.hidden = true;
        return;
    }
    card.hidden = false;
    $("sessionInterpreterName").textContent = call.translatorName || call.invitedTranslatorName || "Interpreter";
    $("sessionInterpreterStatus").textContent = connected ? "On this call" : "Waiting to join";
    let profile = interpreterProfileCache.get(interpreterId) || null;
    if (!profile) {
        try {
            profile = await apiFetch(`/api/translators/${encodeURIComponent(interpreterId)}`);
            if (profile?.id || profile?.uid) interpreterProfileCache.set(interpreterId, profile);
            rememberCallFacePhoto(interpreterId, profile?.displayName, profile?.photoUrl);
            syncAudioCallFaces();
        } catch (error) {
            profile = null;
        }
    }
    const languages = [...(profile?.languages || []), ...(profile?.dialects || [])].filter(Boolean);
    $("sessionInterpreterLanguages").textContent = languages.length ? languages.join(", ") : (call.language || "Languages not published");
    const rating = profile?.rating;
    const count = Number(profile?.ratingCount || 0);
    $("sessionInterpreterRating").textContent = rating == null ? "No reviews yet" : `${Number(rating).toFixed(1)} · ${count} review${count === 1 ? "" : "s"}`;
    $("sessionInterpreterPrice").textContent = formatInterpreterPrice(profile);
}

function bookFromAudioCall() {
    const profile = activeDirectoryProfile || selectedInterpreterProfile || [...peerProfiles.values()].find(item => item?.id);
    if (profile) activeDirectoryProfile = profile;
    show("dashboardView");
    openDashboardPanel("schedule");
}

function rememberEndedCall(callId) {
    if (!callId) return;
    const other = [...peerProfiles.values()].find(profile => profile?.id);
    lastEndedCall = {
        id: callId,
        translatorId: selectedInterpreterProfile?.id || activeDirectoryProfile?.id || other?.id || ""
    };
}

function captureSessionSnapshot() {
    const otherProfile = remoteCallFace();
    const lines = [...($("transcriptList")?.querySelectorAll(".transcript-line") || [])].slice(-6).map(line => line.innerText.trim()).filter(Boolean);
    const startedMs = callExperience?.startedAt?.() || Date.now();
    const start = new Date(Number.isFinite(startedMs) ? startedMs : Date.now());
    return {
        selfName: currentProfile?.displayName || "You",
        selfPhoto: lookupCallFacePhoto(selfCallFace()) || "",
        otherName: otherProfile?.displayName || "Participant",
        otherPhoto: lookupCallFacePhoto(otherProfile) || "",
        tutorName: selectedInterpreterProfile?.displayName || activeDirectoryProfile?.displayName || otherProfile?.displayName || "Your interpreter",
        language: (selectedInterpreterProfile?.languages || activeDirectoryProfile?.languages || otherProfile?.languages || [])[0] || "Session",
        when: `${formatSessionClock(start)} – ${formatSessionClock(new Date())}`,
        lines
    };
}

async function ensureDirectoryProfiles() {
    if (directoryProfiles.length) return directoryProfiles;
    try { directoryProfiles = await fetchDirectoryProfiles(); } catch (error) { console.warn("Concept directory load failed:", error); }
    return directoryProfiles;
}

function paintConceptAvatar(element, profile, fallback) {
    if (!element) return;
    if (!profile) { element.textContent = fallback || "FS"; element.style.backgroundImage = ""; return; }
    setProfileAvatar(element, profile);
}

function renderLessonScreen() {
    ensureDirectoryProfiles().then(profiles => {
        const tutor = activeDirectoryProfile || profiles[0];
        if (!tutor) return;
        conceptMatchedProfile = tutor;
        paintConceptAvatar($("conceptTutorAvatar"), tutor, "IG");
        $("conceptTutorName").textContent = tutor.displayName || "Your tutor";
        const rating = Number(tutor.rating || 4.9);
        $("conceptTutorStars").innerHTML = `${"★".repeat(Math.max(1, Math.round(rating)))} <span>${rating.toFixed(1)}</span>`;
        $("conceptTutorBadge").textContent = tutor.verificationStatus === "verified" ? "Verified" : "Tutor";
        $("conceptLessonTopic").textContent = (tutor.specialties || [])[0] || "Intermediate Vocabulary";
    });
}

function renderScheduleScreen() {
    const month = $("conceptScheduleMonth");
    const grid = $("conceptScheduleGrid");
    if (!month || !grid) return;
    const now = new Date();
    month.textContent = now.toLocaleString(undefined, { month: "long", year: "numeric" });
    const year = now.getFullYear();
    const monthIndex = now.getMonth();
    const first = new Date(year, monthIndex, 1).getDay();
    const days = new Date(year, monthIndex + 1, 0).getDate();
    const labels = ["S", "M", "T", "W", "T", "F", "S"];
    grid.replaceChildren();
    labels.forEach(label => {
        const cell = document.createElement("span");
        cell.textContent = label;
        grid.appendChild(cell);
    });
    for (let blank = 0; blank < first; blank += 1) grid.appendChild(document.createElement("span"));
    for (let day = 1; day <= days; day += 1) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = String(day);
        if (day === now.getDate()) button.className = "active";
        button.onclick = () => {
            grid.querySelectorAll("button").forEach(item => item.classList.toggle("active", item === button));
            refreshScheduleSlot();
        };
        grid.appendChild(button);
    }
    const profile = activeDirectoryProfile || selectedInterpreterProfile;
    $("conceptSlotMeta").textContent = profile ? [...(profile.specialties || []), ...(profile.languages || [])].filter(Boolean).slice(0, 2).join(", ") || "Live session" : "Legal, Business";
}

function utcSessionTimestamp(date) {
    const pad = value => String(value).padStart(2, "0");
    return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())}`;
}

function scheduleSelection() {
    const minutes = Number(document.querySelector("#conceptSchedulePanel [data-duration].active")?.dataset.duration || 60);
    const dayText = document.querySelector("#conceptScheduleGrid button.active")?.textContent;
    const start = new Date();
    if (dayText) start.setDate(Number(dayText));
    start.setHours(11, 0, 0, 0);
    return { start, minutes };
}

function refreshScheduleSlot() {
    const label = $("conceptSlotLabel");
    if (!label || !$("conceptSchedulePanel")) return;
    const { start, minutes } = scheduleSelection();
    const end = new Date(start.getTime() + minutes * 60000);
    const fmt = value => value.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    const prefix = start.toDateString() === new Date().toDateString() ? "" : `${start.getDate()} · `;
    label.textContent = `${prefix}${fmt(start)} – ${fmt(end)}`;
}

function renderGoalScreen() {
    const profile = activeDirectoryProfile || conceptMatchedProfile || directoryProfiles[0];
    if (!profile) return;
    conceptMatchedProfile = profile;
    $("conceptGoalName").textContent = profile.displayName || "Interpreter";
    paintConceptAvatar($("conceptGoalAvatar"), profile, "AC");
}

function renderLiveScreen() {
    const profile = activeDirectoryProfile || conceptMatchedProfile;
    if (!profile) return;
    $("conceptLiveName").textContent = profile.displayName || "Interpreter";
    paintConceptAvatar($("conceptLiveAvatarA"), profile, "AC");
    paintConceptAvatar($("conceptLiveAvatarB"), { displayName: currentProfile?.displayName || "You" }, "You");
}

function scoreProfile(profile) {
    const language = ($("conceptMatchLanguage")?.value || "").toLowerCase();
    const goal = ($("conceptMatchGoal")?.value || "").toLowerCase();
    const blob = [profile.displayName, profile.bio, ...(profile.languages || []), ...(profile.dialects || []), ...(profile.specialties || [])].filter(Boolean).join(" ").toLowerCase();
    let score = 72 + Math.min(12, Number(profile.rating || 0) * 2);
    if (language && blob.includes(language)) score += 12;
    goal.split(/\s+/).filter(word => word.length > 3).forEach(word => { if (blob.includes(word)) score += 4; });
    if (profile.verificationStatus === "verified") score += 6;
    return Math.min(99, Math.round(score));
}

function renderAutoMatchScreen() {
    const list = $("conceptMatchList");
    if (!list) return;
    ensureDirectoryProfiles().then(profiles => {
        const ranked = [...profiles].sort((a, b) => scoreProfile(b) - scoreProfile(a)).slice(0, 2);
        conceptMatchedProfile = ranked[0] || null;
        if (!ranked.length) {
            list.innerHTML = '<p class="transcript-empty">No interpreters are available to match yet.</p>';
            return;
        }
        list.innerHTML = ranked.map(profile => {
            const tags = [...(profile.specialties || []), ...(profile.languages || [])].filter(Boolean).slice(0, 2);
            const quote = profile.bio ? `"${profile.bio.slice(0, 42)}${profile.bio.length > 42 ? "…" : ""}"` : "Highly recommended";
            return `<article class="concept-match-card"><div class="concept-avatar">${escapeHtml(profileInitials(profile.displayName))}</div><div><strong>${escapeHtml(profile.displayName || "Interpreter")}</strong><div class="concept-stars">${"★".repeat(Math.max(1, Math.round(Number(profile.rating || 5))))}</div><div class="concept-lang-badges">${tags.map(tag => `<span>${escapeHtml(tag)}</span>`).join("")}</div><p>${escapeHtml(quote)}</p></div><span class="match-score">${scoreProfile(profile)}% Match</span></article>`;
        }).join("");
        ranked.forEach((profile, index) => paintConceptAvatar(list.querySelectorAll(".concept-avatar")[index], profile));
    });
}

function renderSummaryScreen() {
    const snapshot = lastSessionSnapshot;
    if (!snapshot) return;
    $("conceptSummaryLeft").textContent = snapshot.otherName;
    $("conceptSummaryRight").textContent = snapshot.selfName;
    $("conceptSummaryTutor").textContent = snapshot.tutorName;
    $("conceptSummaryLanguage").textContent = snapshot.language;
    if (snapshot.when) $("conceptSummaryWhen").textContent = snapshot.when;
    paintConceptAvatar($("conceptSummaryAvatarA"), { displayName: snapshot.otherName, photoUrl: snapshot.otherPhoto }, "FS");
    paintConceptAvatar($("conceptSummaryAvatarB"), { displayName: snapshot.selfName, photoUrl: snapshot.selfPhoto }, "You");
    paintConceptAvatar($("conceptSummaryTutorAvatar"), { displayName: snapshot.tutorName }, "CC");
    if (snapshot.lines.length) {
        $("conceptTranscriptHits").innerHTML = snapshot.lines.map(line => `<p>${escapeHtml(line)}</p>`).join("");
    }
}

function renderEducationScreen() {
    const list = $("educationHistory");
    if (!list) return;
    const rows = [...historyCalls.values()].sort((a, b) => callMillis(b) - callMillis(a)).slice(0, 4);
    if (!rows.length) return;
    list.innerHTML = rows.map(call => {
        const other = (currentUser?.uid === call.callerId ? call.receiverName : call.callerName) || call.translatorName || "FiniSpeak session";
        const date = timestampDate(call.startedAt) || timestampDate(call.createdAt);
        const when = date ? date.toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" }) : "Recent";
        return `<article><div><strong>${escapeHtml(other)}</strong><small>${escapeHtml(when)}</small></div><div><strong>${escapeHtml(call.language || "Session")}</strong><small>${escapeHtml(call.status || "Completed")}</small></div></article>`;
    }).join("");
}

function bindConceptScreens() {
    const activateGroup = selector => {
        document.querySelectorAll(selector).forEach(button => {
            button.onclick = () => {
                button.parentElement.querySelectorAll("button").forEach(item => {
                    const active = item === button;
                    item.classList.toggle("active", active);
                    item.setAttribute("aria-pressed", String(active));
                });
                if (button.closest("#conceptSchedulePanel")) refreshScheduleSlot();
            };
        });
    };
    activateGroup("[data-duration]");
    activateGroup("[data-goal-duration]");
    activateGroup("[data-live-duration]");
    activateGroup("[data-lesson-topic]");
    $("conceptTutorProfile").onclick = () => { if (conceptMatchedProfile || activeDirectoryProfile) openPublicProfile(conceptMatchedProfile || activeDirectoryProfile); };
    $("conceptBookLesson").onclick = () => openDashboardPanel("schedule");
    $("conceptRequestInstant").onclick = () => {
        if (activeDirectoryProfile) startDirectTranslatorChat();
        else showCallDialPad();
    };
    $("conceptConfirmSchedule").onclick = async () => {
        const status = $("conceptScheduleStatus");
        const profile = activeDirectoryProfile || selectedInterpreterProfile;
        if (!currentUser) { status.textContent = "Sign in to schedule a session."; return; }
        if (!profile?.id) { status.textContent = "Choose an interpreter first."; return; }
        const kind = $("conceptSessionType")?.value || "Audio";
        const { start, minutes } = scheduleSelection();
        if (start.getTime() <= Date.now()) { status.textContent = "That time has already passed. Choose a later day."; return; }
        status.textContent = "Scheduling…";
        try {
            await apiFetch("/api/sessions", {
                method: "POST",
                body: JSON.stringify({
                    translatorId: profile.id,
                    language: (profile.languages || [])[0] || "Spanish",
                    dialect: (profile.dialects || [])[0] || "",
                    specialty: (profile.specialties || [])[0] || "",
                    purpose: `${kind} session, ${minutes} min`,
                    scheduledAt: utcSessionTimestamp(start)
                })
            });
            refreshScheduleSlot();
            status.textContent = `Session scheduled for ${$("conceptSlotLabel").textContent}. ${profile.displayName || "The interpreter"} will be notified.`;
        } catch (error) {
            status.textContent = error.message || "Could not schedule the session.";
        }
    };
    $("conceptGoalBook").onclick = () => {
        if ($("conceptMatchGoal")) $("conceptMatchGoal").value = $("conceptGoalInput").value;
        openDashboardPanel("match");
    };
    $("conceptLiveBook").onclick = () => openDashboardPanel("schedule");
    $("conceptQuickBook").onclick = () => {
        if (conceptMatchedProfile) activeDirectoryProfile = conceptMatchedProfile;
        openDashboardPanel("schedule");
    };
    $("conceptMatchProfile").onclick = () => { if (conceptMatchedProfile) openPublicProfile(conceptMatchedProfile); };
    $("conceptRerunMatch").onclick = () => renderAutoMatchScreen();
    $("conceptMatchLanguage").onchange = () => renderAutoMatchScreen();
    $("conceptMatchGoal").oninput = () => renderAutoMatchScreen();
    $("openIntelligenceHub").onclick = () => openDashboardPanel("intelligence");
    $("educationBookParent").onclick = () => {
        $("conceptGoalInput").value = "Parent meeting";
        openDashboardPanel("goal");
    };
    $("educationLiveSupport").onclick = () => openDashboardPanel("live");
    $("conceptViewTranscript").onclick = () => {
        if (lastEndedCall?.id) openHistoryTranscript(lastEndedCall);
        else openDashboardPanel("live");
    };
    $("conceptEmailSummary").onclick = () => {
        const body = lastSessionSnapshot?.lines?.join("\n") || $("conceptLiveTranscript")?.innerText || "FiniSpeak session summary";
        window.location.href = `mailto:?subject=${encodeURIComponent("FiniSpeak session summary")}&body=${encodeURIComponent(body)}`;
    };
    $("conceptBookAgain").onclick = () => openDashboardPanel("directory");
    $("conceptContinueSession").onclick = () => openDashboardPanel("lesson");
    $("conceptTranscriptSearch").oninput = () => {
        const query = $("conceptTranscriptSearch").value.trim().toLowerCase();
        const lines = lastSessionSnapshot?.lines || [...$("conceptLiveTranscript").querySelectorAll("p")].map(item => item.textContent);
        const hits = lines.filter(line => !query || line.toLowerCase().includes(query));
        $("conceptTranscriptHits").innerHTML = hits.map(line => `<p>${escapeHtml(line)}</p>`).join("");
    };
    document.querySelectorAll("[data-rate]").forEach(button => {
        button.onclick = () => {
            const value = Number(button.dataset.rate);
            document.querySelectorAll("[data-rate]").forEach(star => star.classList.toggle("active", Number(star.dataset.rate) <= value));
            if ($("reviewRating")) $("reviewRating").value = String(value);
            if (lastEndedCall?.translatorId) openReviewModal(lastEndedCall);
        };
    });
    $("conceptRequestCall").onclick = () => $("profileChatTranslator").click();
    $("conceptScheduleSession").onclick = () => {
        if (!currentUser) {
            openAuth(false, "customer");
            $("authStatus").textContent = "Log in to schedule a session.";
            return;
        }
        show("dashboardView");
        openDashboardPanel("schedule");
    };
}

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value ?? "";
    return div.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

boot();
