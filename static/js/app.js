import { initializeApp } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js";
import { getAuth, createUserWithEmailAndPassword, signInWithEmailAndPassword, signOut, onAuthStateChanged, updateProfile } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js";
import { getFirestore, doc, setDoc, getDoc, collection, query, where, getDocs, addDoc, updateDoc, onSnapshot, serverTimestamp, deleteField } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-firestore.js";
import { getStorage, ref as storageRef, uploadBytes, getDownloadURL } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-storage.js";

const $ = (id) => document.getElementById(id);
const views = ["heroView", "authView", "dashboardView", "profileView", "callView"];
const show = (id) => views.forEach(v => $(v).classList.toggle("hidden", v !== id));
let auth, db, storage, currentUser, currentProfile, currentInterpreterProfile, signupMode = false;
let localStream = null, activeCallId = null, callUnsubs = [], peerConnections = new Map();
let transcriptionSocket = null, transcriptionAudioContext = null, transcriptionSource = null, transcriptionNode = null, currentCallRole = null;
let dashboardUnsubs = [], pendingIncomingCall = null, historyCalls = new Map();
let directoryProfiles = [], activeDirectoryProfile = null;
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
const profilePhotoTypes = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp"
};

async function boot() {
    bindUI();
    loadFeaturedProfiles();
    try {
        const response = await fetch("/api/firebase-config");
        const config = await response.json();
        if (!response.ok) throw new Error(config.error || "Firebase configuration missing");
        const firebaseApp = initializeApp(config);
        auth = getAuth(firebaseApp);
        db = getFirestore(firebaseApp);
        storage = config.storageBucket ? getStorage(firebaseApp) : null;
        onAuthStateChanged(auth, handleAuthState);
    } catch (error) {
        $("status").textContent = `${error.message}. Add the Firebase web values to .env.`;
    }
}

function bindUI() {
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
    $("startCall").onclick = () => {
        if (!currentUser) return openAuth(false, "customer");
        show("dashboardView");
        openDashboardPanel("home");
    };
    $("landingCta").onclick = () => openAuth(true, "customer");
    $("translatorSignup").onclick = () => openAuth(true, "translator");
    $("homeNav").onclick = () => show("heroView");
    $("browseNav").onclick = openInterpreterDirectory;
    $("browseHero").onclick = openInterpreterDirectory;
    $("authNav").onclick = async () => currentUser ? signOut(auth) : openAuth(false, "customer");
    $("authToggle").onclick = () => setAuthMode(!signupMode);
    $("authForm").onsubmit = submitAuth;
    $("callForm").onsubmit = createCall;
    $("copyCallId").onclick = () => navigator.clipboard.writeText(activeCallId || "");
    $("muteButton").onclick = toggleMute;
    $("cameraButton").onclick = toggleCamera;
    $("requestTranslatorButton").onclick = requestTranslator;
    $("endCallButton").onclick = endCall;
    $("acceptIncomingCall").onclick = acceptIncomingCall;
    $("declineIncomingCall").onclick = declineIncomingCall;
    $("closeTranscriptModal").onclick = () => $("transcriptModal").classList.add("hidden");
    document.querySelectorAll("[data-dashboard-panel]").forEach(button => button.addEventListener("click", () => openDashboardPanel(button.dataset.dashboardPanel)));
    document.querySelectorAll("[data-open-panel]").forEach(button => button.addEventListener("click", () => openDashboardPanel(button.dataset.openPanel)));
    $("profileForm").onsubmit = saveProfile;
    $("interpreterProfileForm").onsubmit = (e) => saveInterpreterProfile(e, false);
    $("saveInterpreterDraft").onclick = (e) => saveInterpreterProfile(e, true);
    $("interpreterPhoto").onchange = previewInterpreterPhoto;
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
    $("settingsSignOut").onclick = async () => signOut(auth);
    $("directorySearch").addEventListener("input", filterInterpreterDirectory);
    $("directoryRating").addEventListener("change", filterInterpreterDirectory);
    $("directorySort").addEventListener("change", filterInterpreterDirectory);
    $("directoryAvailable").addEventListener("change", filterInterpreterDirectory);
    $("backToDirectory").onclick = openInterpreterDirectory;
    $("profileStartCall").onclick = () => {
        if (!currentUser) {
            openAuth(false, "customer");
            $("authStatus").textContent = "Log in when you are ready to start a call with an interpreter.";
            return;
        }
        show("dashboardView");
        openDashboardPanel("home");
        $("receiverEmail")?.focus();
    };
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

function openAuth(signup, role) { setAuthMode(signup); $("role").value = role; show("authView"); }
function setAuthMode(signup) {
    signupMode = signup;
    $("authTitle").textContent = signup ? "Create account" : "Sign in";
    $("authSubmit").textContent = signup ? "Create account" : "Sign in";
    $("authToggle").textContent = signup ? "Already have an account? Sign in" : "Need an account? Create one";
    $("nameField").classList.toggle("hidden", !signup); $("roleField").classList.toggle("hidden", !signup);
}


async function submitAuth(e) {
    e.preventDefault(); $("authStatus").textContent = "Working…";
    try {
        const email = $("email").value.trim(), password = $("password").value;
        if (signupMode) {
            const result = await createUserWithEmailAndPassword(auth, email, password);
            const name = $("displayName").value.trim() || email.split("@")[0];
            const role = $("role").value;
            const normalizedEmail = email.toLowerCase();
            await updateProfile(result.user, { displayName: name });
            await setDoc(doc(db, "users", result.user.uid), { uid: result.user.uid, email: normalizedEmail, displayName: name, role, createdAt: serverTimestamp() });
            await setDoc(doc(db, "emailDirectory", normalizedEmail), { uid: result.user.uid, displayName: name, role, email: normalizedEmail, updatedAt: serverTimestamp() });
            if (role === "translator") {
                await setDoc(doc(db, "translators", result.user.uid), {
                    uid: result.user.uid, displayName: name, email: normalizedEmail,
                    onboardingStatus: "draft", verificationStatus: "unverified",
                    languages: [], dialects: [], specialties: [], credentials: [],
                    yearsExperience: 0, availability: { days: [], start: "", end: "", availableNow: false },
                    rating: null, ratingCount: 0, createdAt: serverTimestamp(), updatedAt: serverTimestamp()
                }, { merge: true });
            }
        } else await signInWithEmailAndPassword(auth, email, password);
        $("authStatus").textContent = "";
    } catch (error) { $("authStatus").textContent = error.message; }
}

async function handleAuthState(user) {
    currentUser = user;
    $("authNav").textContent = user ? "Log out" : "Log in";
    if (!user) {
        currentProfile = null;
        currentInterpreterProfile = null;
        cleanupDashboardListeners();
        cleanupCall();
        show("heroView");
        return;
    }

    // Authentication and dashboard loading are intentionally separated. A
    // missing/older profile document must never leave an authenticated user
    // stuck on the login screen.
    try {
        const userRef = doc(db, "users", user.uid);
        const translatorRef = doc(db, "translators", user.uid);
        const [userSnap, translatorSnap] = await Promise.all([
            getDoc(userRef),
            getDoc(translatorRef).catch(() => null)
        ]);

        const fallbackProfile = {
            uid: user.uid,
            email: (user.email || "").toLowerCase(),
            displayName: user.displayName || user.email || "FiniSpeak user",
            role: translatorSnap?.exists() ? "translator" : "customer"
        };
        currentProfile = userSnap.exists() ? { ...fallbackProfile, ...userSnap.data() } : fallbackProfile;

        // Older translator accounts may predate the role field in /users.
        // The translator profile is authoritative for those accounts.
        if (translatorSnap?.exists()) currentProfile.role = "translator";
        currentInterpreterProfile = currentProfile.role === "translator" && translatorSnap?.exists()
            ? translatorSnap.data()
            : null;

        // Repair/migrate the signed-in user's basic profile when possible.
        if (!userSnap.exists() || (currentProfile.role === "translator" && userSnap.data()?.role !== "translator")) {
            await setDoc(userRef, {
                uid: user.uid,
                email: fallbackProfile.email,
                displayName: currentProfile.displayName,
                role: currentProfile.role,
                updatedAt: serverTimestamp()
            }, { merge: true }).catch(error => console.warn("Profile migration skipped:", error));
        }

        hydrateDashboardProfile();
        const isTranslator = currentProfile.role === "translator";
        $("interpreterProfileNav").classList.toggle("hidden", !isTranslator);
        $("customerTools").classList.toggle("hidden", isTranslator);
        $("translatorTools").classList.toggle("hidden", !isTranslator);

        // Show the dashboard before loading optional translator/profile data so
        // a Firestore/profile problem cannot block navigation after login.
        openDashboardPanel("home");
        show("dashboardView");
        $("authStatus").textContent = "";

        if (isTranslator) {
            try {
                await loadTaxonomy();
                if (currentInterpreterProfile) hydrateInterpreterProfile(currentInterpreterProfile);
                else await loadInterpreterProfile();
            } catch (error) {
                console.error("Interpreter profile load failed:", error);
                $("translatorRequestStatus").textContent = `Dashboard loaded, but the interpreter profile could not be loaded: ${error.message}`;
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
        $("interpreterProfileNav").classList.add("hidden");
        $("translatorTools").classList.add("hidden");
        $("customerTools").classList.remove("hidden");
        openDashboardPanel("home");
        show("dashboardView");
        $("dashboardStatus").textContent = `Signed in, but some account data could not load: ${error.message}`;
        $("authStatus").textContent = "";
    }
}


function hydrateDashboardProfile() {
    const name = currentProfile.displayName || currentProfile.email || "FiniSpeak";
    const roleLabel = currentProfile.role === "translator" ? "Translator" : "Customer";
    $("welcomeName").textContent = name;
    $("accountRole").textContent = `${roleLabel} account`;
    $("sidebarName").textContent = name;
    $("sidebarRole").textContent = roleLabel;
    $("profileInitials").textContent = name.split(/\s+/).filter(Boolean).slice(0,2).map(part => part[0]).join("").toUpperCase() || "FS";
    $("profileDisplayName").value = currentProfile.displayName || "";
    $("profileEmail").value = currentProfile.email || currentUser?.email || "";
    $("profileRole").value = roleLabel;
    $("settingsEmail").textContent = currentProfile.email || currentUser?.email || "";
}

function openDashboardPanel(panel) {
    const ids = { home: "dashboardHome", directory: "dashboardDirectory", profile: "dashboardProfile", interpreter: "dashboardInterpreter", settings: "dashboardSettings" };
    Object.entries(ids).forEach(([key, id]) => $(id).classList.toggle("hidden", key !== panel));
    document.querySelectorAll("[data-dashboard-panel]").forEach(button => {
        const active = button.dataset.dashboardPanel === panel;
        button.classList.toggle("active", active);
        if (active) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current");
    });
    if (panel === "directory") loadInterpreterDirectory();
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
        const profiles = await fetchPublicProfiles();
        profiles.sort((a, b) => Number(b.rating || 0) - Number(a.rating || 0) || Number(b.ratingCount || 0) - Number(a.ratingCount || 0));
        renderFeaturedProfiles(profiles);
    } catch (error) {
        console.error("Featured profiles failed:", error);
        container.innerHTML = '<div class="directory-empty">Featured profiles are temporarily unavailable.</div>';
    }
}

function renderFeaturedProfiles(profiles) {
    const container = $("featuredInterpreters");
    if (!profiles.length) {
        container.innerHTML = '<div class="directory-empty">Featured interpreter profiles are coming soon.</div>';
        return;
    }
    container.replaceChildren(...profiles.map(profile => {
        const card = document.createElement("article");
        card.className = "interpreter-card featured-interpreter-card";
        const tags = [...(profile.languages || []), ...(profile.specialties || [])].slice(0, 3);
        card.innerHTML = `
            <div class="directory-avatar">${escapeHtml(profileInitials(profile.displayName))}</div>
            <div>
                <div class="interpreter-card-header"><div><h3>${escapeHtml(profile.displayName)}</h3>${ratingMarkup(profile.rating, profile.ratingCount)}</div><span class="availability-dot${profile.availability?.availableNow ? " available" : ""}" title="${profile.availability?.availableNow ? "Available now" : "Currently unavailable"}"></span></div>
                <p class="card-bio">${escapeHtml(profile.bio || "Professional FiniSpeak interpreter profile.")}</p>
                <div class="directory-tags">${tags.map(tag => `<span class="directory-tag">${escapeHtml(tag)}</span>`).join("")}</div>
                <button class="text-button featured-profile-login" type="button">View profile</button>
            </div>`;
        setProfileAvatar(card.querySelector(".directory-avatar"), profile);
        card.querySelector(".featured-profile-login").onclick = () => openPublicProfile(profile);
        return card;
    }));
}

async function loadInterpreterDirectory() {
    const container = $("interpreterDirectory");
    container.innerHTML = '<div class="directory-loading"><span class="button-spinner" aria-hidden="true"></span>Loading profiles…</div>';
    $("directoryResultCount").textContent = "Loading interpreters…";
    try {
        directoryProfiles = await fetchPublicProfiles();
        filterInterpreterDirectory();
    } catch (error) {
        console.error("Interpreter directory failed:", error);
        $("directoryResultCount").textContent = "Directory unavailable";
        container.innerHTML = `<div class="directory-empty">Could not load interpreter profiles: ${escapeHtml(error.message)}</div>`;
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
    renderInterpreterDirectory(profiles);
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
        card.setAttribute("aria-label", `View ${profile.displayName}'s interpreter profile`);
        const languages = [...(profile.languages || []), ...(profile.dialects || [])].slice(0, 3);
        const specialties = (profile.specialties || []).slice(0, 2);
        const tags = [...languages, ...specialties];
        card.innerHTML = `
            <div class="directory-avatar">${escapeHtml(profileInitials(profile.displayName))}</div>
            <div>
                <div class="interpreter-card-header"><div><h3>${escapeHtml(profile.displayName)}</h3>${ratingMarkup(profile.rating, profile.ratingCount)}</div><span class="availability-dot${profile.availability?.availableNow ? " available" : ""}" title="${profile.availability?.availableNow ? "Available now" : "Currently unavailable"}"></span></div>
                <p class="card-bio">${escapeHtml(profile.bio || "Professional FiniSpeak interpreter profile.")}</p>
                <div class="directory-tags">${tags.map(tag => `<span class="directory-tag">${escapeHtml(tag)}</span>`).join("")}</div>
                <div class="directory-meta"><span>${Number(profile.yearsExperience || 0)} years experience</span><span>${escapeHtml((profile.verificationStatus || "unverified").replace(/_/g, " "))}</span></div>
            </div>`;
        setProfileAvatar(card.querySelector(".directory-avatar"), profile);
        card.onclick = () => openPublicProfile(profile);
        return card;
    }));
}

async function openPublicProfile(profile) {
    activeDirectoryProfile = profile;
    const available = Boolean(profile.availability?.availableNow);
    $("publicProfileName").textContent = profile.displayName || "Interpreter";
    $("publicProfileHeadline").textContent = profile.specialties?.length
        ? `${profile.specialties.slice(0, 2).join(" · ")} interpreter`
        : `${(profile.languages || []).slice(0, 2).join(" · ") || "Professional"} interpreter`;
    $("publicProfileAvailability").textContent = available ? "Available now" : "Currently unavailable";
    $("publicProfileAvailability").classList.toggle("available", available);
    $("publicProfileRating").innerHTML = ratingMarkup(profile.rating, profile.ratingCount);
    $("publicProfileBio").textContent = profile.bio || "This interpreter has not added a professional bio yet.";
    setProfileAvatar($("publicProfileAvatar"), profile);
    renderProfileTags($("publicProfileLanguages"), "Languages", [...(profile.languages || []), ...(profile.dialects || [])]);
    renderProfileTags($("publicProfileSpecialties"), "Specialties", profile.specialties || []);
    $("publicProfileExperience").textContent = `${Number(profile.yearsExperience || 0)} years`;
    $("publicProfileCredentials").textContent = (profile.credentials || []).join(", ") || "Not listed";
    $("publicProfileVerification").textContent = profileVerificationLabel(profile);
    $("publicProfileSchedule").textContent = formatAvailabilitySchedule(profile.availability, "Schedule not listed");
    $("publicProfileReviewSummary").innerHTML = ratingMarkup(profile.rating, profile.ratingCount);
    $("publicProfileReviews").innerHTML = "<p>Detailed community feedback will appear here as reviews are added.</p>";
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

function setProfileAvatar(element, profile) {
    element.textContent = profileInitials(profile.displayName);
    element.style.backgroundImage = "";
    if (profile.photoUrl && /^https:\/\//i.test(profile.photoUrl)) {
        element.style.backgroundImage = `url("${profile.photoUrl.replace(/"/g, "%22")}")`;
        element.textContent = "";
    }
}

function profileInitials(name = "") {
    return name.split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join("").toUpperCase() || "FS";
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
    if (!displayName) { status.textContent = "Enter a display name."; return; }
    status.textContent = "Saving…";
    try {
        await updateProfile(currentUser, { displayName });
        await setDoc(doc(db, "users", currentUser.uid), { displayName, updatedAt: serverTimestamp() }, { merge: true });
        const email = (currentProfile.email || currentUser.email || "").toLowerCase();
        if (email) await setDoc(doc(db, "emailDirectory", email), { uid: currentUser.uid, displayName, role: currentProfile.role, email, updatedAt: serverTimestamp() }, { merge: true });
        currentProfile = { ...currentProfile, displayName };
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
        await Promise.all(Object.keys(taxonomyUI).map(async kind => {
            const snapshot = await getDocs(collection(db, taxonomyCollections[kind]));
            const values = snapshot.docs
                .map(document => document.data())
                .filter(item => item.active !== false && item.name)
                .map(item => item.name);
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
            const ref = doc(db, taxonomyCollections[kind], id);
            const snap = await getDoc(ref);
            if (!snap.exists()) await setDoc(ref, {
                name,
                nameLower: normalized,
                active: true,
                seeded: false,
                createdBy: currentUser.uid,
                createdAt: serverTimestamp()
            });
            const stored = snap.exists() ? (snap.data().name || name) : name;
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
    $("interpreterPhone").value = p.phone || "";
    $("interpreterBio").value = p.bio || "";
    setSelectedTags("languages", p.languages || []);
    setSelectedTags("dialects", p.dialects || []);
    setSelectedTags("specialties", p.specialties || []);
    $("interpreterYears").value = p.yearsExperience ?? "";
    $("interpreterCredentials").value = (p.credentials || []).join("\n");
    $("interpreterCredentialStatus").value = p.credentialStatus || "unsubmitted";
    const availability = p.availability || {};
    document.querySelectorAll('input[name="availabilityDay"]').forEach(input => input.checked = (availability.days || []).includes(input.value));
    $("availabilityStart").value = availability.start || "";
    $("availabilityEnd").value = availability.end || "";
    $("interpreterAvailableNow").checked = Boolean(availability.availableNow);
    setInterpreterPhoto(p.photoUrl || "");
    updateInterpreterCompletion();
    renderTranslatorDashboard();
}

async function loadInterpreterProfile() {
    const ref = doc(db, "translators", currentUser.uid);
    const snap = await getDoc(ref);
    if (!snap.exists()) {
        // Translator role exists but its onboarding document does not yet. This
        // can happen with accounts created before interpreter onboarding.
        const starter = {
            uid: currentUser.uid,
            displayName: currentProfile.displayName || currentUser.displayName || "",
            email: (currentUser.email || "").toLowerCase(),
            onboardingStatus: "draft",
            verificationStatus: "unverified",
            languages: [], dialects: [], specialties: [], credentials: [],
            yearsExperience: 0,
            availability: { days: [], start: "", end: "", availableNow: false },
            rating: null, ratingCount: 0,
            createdAt: serverTimestamp(), updatedAt: serverTimestamp()
        };
        await setDoc(ref, starter, { merge: true });
        currentInterpreterProfile = starter;
    } else {
        currentInterpreterProfile = snap.data();
    }
    hydrateInterpreterProfile(currentInterpreterProfile);
}

function renderTranslatorDashboard() {
    if (currentProfile?.role !== "translator") return;
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
    if (currentProfile?.role !== "translator") return;
    const toggle = $("dashboardAvailableNow");
    const availableNow = toggle.checked;
    $("dashboardAvailabilityLabel").textContent = availableNow ? "Available now" : "Unavailable";
    $("translatorRequestStatus").textContent = "Updating availability…";
    try {
        const availability = { ...(currentInterpreterProfile?.availability || {}), availableNow };
        await setDoc(doc(db, "translators", currentUser.uid), { availability, updatedAt: serverTimestamp() }, { merge: true });
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
    return {
        displayName: $("interpreterFullName").value.trim(),
        phone: $("interpreterPhone").value.trim(),
        bio: $("interpreterBio").value.trim(),
        languages: [...selectedTags.languages],
        dialects: [...selectedTags.dialects],
        specialties: [...selectedTags.specialties],
        yearsExperience: Number($("interpreterYears").value || 0),
        credentials: splitList($("interpreterCredentials").value),
        credentialStatus: $("interpreterCredentialStatus").value,
        availability: {
            days: [...document.querySelectorAll('input[name="availabilityDay"]:checked')].map(input => input.value),
            start: $("availabilityStart").value,
            end: $("availabilityEnd").value,
            availableNow: $("interpreterAvailableNow").checked
        }
    };
}

function interpreterCompletion(data = interpreterFormData()) {
    const checks = [data.displayName, data.bio, data.languages.length, data.specialties.length, Number.isFinite(data.yearsExperience), data.availability.days.length];
    return Math.round((checks.filter(Boolean).length / checks.length) * 100);
}

function updateInterpreterCompletion(data = interpreterFormData()) {
    const pct = interpreterCompletion(data);
    $("interpreterProgressBar").style.width = `${pct}%`;
    $("interpreterProgressText").textContent = pct === 100 ? "Your required interpreter profile information is complete." : `${pct}% complete · Add the remaining required information.`;
    $("interpreterCompletionBadge").textContent = pct === 100 ? "Profile complete" : "Not complete";
    $("interpreterCompletionBadge").classList.toggle("pending-badge", pct !== 100);
    return pct;
}

function setInterpreterSaveLoading(loading, draft = false) {
    const profileButton = $("saveInterpreterProfile");
    const draftButton = $("saveInterpreterDraft");
    const activeButton = draft ? draftButton : profileButton;
    profileButton.disabled = loading;
    draftButton.disabled = loading;
    profileButton.setAttribute("aria-busy", String(loading && !draft));
    draftButton.setAttribute("aria-busy", String(loading && draft));

    if (loading) {
        const spinner = document.createElement("span");
        spinner.className = "button-spinner";
        spinner.setAttribute("aria-hidden", "true");
        activeButton.replaceChildren(spinner, document.createTextNode(draft ? "Saving draft…" : "Saving profile…"));
        return;
    }

    profileButton.textContent = "Save interpreter profile";
    draftButton.textContent = "Save draft";
}

async function saveInterpreterProfile(e, draft = false) {
    e?.preventDefault?.();
    if (currentProfile?.role !== "translator") return;
    const status = $("interpreterProfileStatus");
    const data = interpreterFormData();
    const completion = interpreterCompletion(data);
    if (!draft && completion < 100) { status.textContent = "Complete all required interpreter fields before finishing onboarding."; updateInterpreterCompletion(data); return; }
    status.textContent = "Saving interpreter profile…";
    setInterpreterSaveLoading(true, draft);
    try {
        let photoUrl = currentInterpreterProfile?.photoUrl || "";
        let photoUploadError = null;
        const file = $("interpreterPhoto").files?.[0];
        if (file) {
            if (!storage) {
                photoUploadError = new Error("Firebase Storage is not configured");
            } else try {
                const extension = profilePhotoTypes[file.type];
                const photoRef = storageRef(storage, `interpreter-profiles/${currentUser.uid}/profile.${extension}`);
                await uploadBytes(photoRef, file, {
                    contentType: file.type,
                    cacheControl: "public,max-age=3600"
                });
                photoUrl = await getDownloadURL(photoRef);
            } catch (error) {
                photoUploadError = error;
                console.error("Interpreter photo upload failed:", error);
            }
        }
        const payload = {
            ...data, uid: currentUser.uid, email: (currentProfile.email || currentUser.email || "").toLowerCase(), photoUrl,
            onboardingStatus: completion === 100 ? "complete" : "draft",
            verificationStatus: currentInterpreterProfile?.verificationStatus || "unverified",
            rating: currentInterpreterProfile?.rating ?? null, ratingCount: currentInterpreterProfile?.ratingCount || 0,
            updatedAt: serverTimestamp()
        };
        await setDoc(doc(db, "translators", currentUser.uid), payload, { merge: true });
        if (data.displayName && data.displayName !== currentProfile.displayName) {
            await updateProfile(currentUser, { displayName: data.displayName });
            await setDoc(doc(db, "users", currentUser.uid), { displayName: data.displayName, updatedAt: serverTimestamp() }, { merge: true });
            const email = payload.email;
            if (email) await setDoc(doc(db, "emailDirectory", email), { displayName: data.displayName, updatedAt: serverTimestamp() }, { merge: true });
            currentProfile = { ...currentProfile, displayName: data.displayName };
            hydrateDashboardProfile();
        }
        currentInterpreterProfile = { ...currentInterpreterProfile, ...payload, photoUrl };
        if (!photoUploadError) {
            $("interpreterPhoto").value = "";
            setInterpreterPhoto(photoUrl);
        }
        updateInterpreterCompletion(data);
        renderTranslatorDashboard();
        if (photoUploadError) {
            status.textContent = `Profile saved, but the photo could not upload: ${photoUploadError.message}. Your selected photo is still here to retry.`;
        } else {
            status.textContent = completion === 100 ? "Interpreter profile saved. Your onboarding information is complete." : "Draft saved. You can finish onboarding later.";
        }
    } catch (error) {
        status.textContent = `Could not save interpreter profile: ${error.message}`;
    } finally {
        setInterpreterSaveLoading(false, draft);
    }
}

async function createCall(e) {
    e.preventDefault(); $("dashboardStatus").textContent = "Finding customer…";
    try {
        const receiverEmail = $("receiverEmail").value.trim().toLowerCase();
        if (!receiverEmail) throw new Error("Enter Customer 2's FiniSpeak email.");
        // Prefer the lightweight email directory created by newer registrations.
        // Older FiniSpeak accounts may predate that collection, so fall back to
        // the users collection instead of incorrectly reporting that they do not exist.
        const directorySnap = await getDoc(doc(db, "emailDirectory", receiverEmail));
        let receiver = directorySnap.exists() ? directorySnap.data() : null;

        if (!receiver) {
            const usersQuery = query(
                collection(db, "users"),
                where("email", "==", receiverEmail)
            );
            const usersSnap = await getDocs(usersQuery);
            if (!usersSnap.empty) receiver = usersSnap.docs[0].data();
        }

        if (!receiver) throw new Error("No FiniSpeak customer found with that email address.");
        if (receiver.role !== "customer") throw new Error("That email address is not registered to a customer account.");
        if (receiver.uid === currentUser.uid) throw new Error("You cannot call yourself.");
        const ref = await addDoc(collection(db, "calls"), {
            callerId: currentUser.uid, receiverId: receiver.uid, translatorId: null,
            status: "ringing", translationStatus: "not_requested", createdAt: serverTimestamp(), startedAt: null, endedAt: null,
            callerName: currentProfile.displayName || currentProfile.email, receiverName: receiver.displayName || receiver.email || receiverEmail
        });
        await joinCall(ref.id);
    } catch (error) { $("dashboardStatus").textContent = error.message; }
}

async function joinCall(callId) {
    try {
        const callRef = doc(db, "calls", callId), snap = await getDoc(callRef);
        if (!snap.exists()) throw new Error("Call not found.");
        const call = snap.data();
        const role = currentProfile.role;
        const allowedCustomer = [call.callerId, call.receiverId].includes(currentUser.uid);
        if (role !== "translator" && !allowedCustomer) throw new Error("You are not a participant in this call.");
        if (role === "translator") {
            if (call.translatorId && call.translatorId !== currentUser.uid) throw new Error("Another translator has already joined.");
            await updateDoc(callRef, { translatorId: currentUser.uid, translationStatus: "connected" });
        }
        activeCallId = callId; show("callView"); $("callIdLabel").textContent = callId;
        $("requestTranslatorButton").classList.toggle("hidden", role === "translator");
        await startMedia();
        currentCallRole = role === "translator" ? "translator" : (currentUser.uid === call.callerId ? "caller" : "receiver");
        await setDoc(doc(db, "calls", callId, "participants", currentUser.uid), {
            uid: currentUser.uid, displayName: currentProfile.displayName || currentProfile.email,
            role: currentCallRole, joinedAt: serverTimestamp()
        });
        watchCall(callId);
        await startTranscription(callId);
    } catch (error) { $("dashboardStatus").textContent = error.message; show("dashboardView"); }
}

async function startMedia() {
    if (localStream) return;
    localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
    $("localVideo").srcObject = localStream;
}

function watchCall(callId) {
    cleanupListeners();
    callUnsubs.push(onSnapshot(doc(db, "calls", callId), snap => {
        if (!snap.exists()) return;
        const call = snap.data();
        $("callTitle").textContent = call.status === "ended" ? "Call ended" : "Live conversation";
        $("callStatus").textContent = call.status === "ringing" ? "Calling… waiting for the other customer to accept." : call.status === "declined" ? "Call declined." : call.translationStatus === "requested" ? "Waiting for a translator to join…" : call.translatorId ? "Translator connected" : "Customer call connected";
        if (["ended", "declined"].includes(call.status)) { cleanupCall(); show("dashboardView"); loadConversationHistory(); }
    }));
    callUnsubs.push(onSnapshot(collection(db, "calls", callId, "participants"), snap => {
        const ids = new Set();
        snap.forEach(d => { if (d.id !== currentUser.uid) { ids.add(d.id); ensurePeer(callId, d.id, d.data()); } });
        for (const [uid, pc] of peerConnections) if (!ids.has(uid)) { pc.close(); peerConnections.delete(uid); removeRemoteVideo(uid); }
    }));
    callUnsubs.push(onSnapshot(collection(db, "calls", callId, "transcripts"), snap => {
        const rows = snap.docs.map(d => ({ id: d.id, ...d.data() }));
        rows.sort((a, b) => {
            const aMs = a.createdAt?.toMillis?.() || a.clientCreatedAt || 0;
            const bMs = b.createdAt?.toMillis?.() || b.clientCreatedAt || 0;
            return aMs - bMs;
        });
        renderTranscript(rows);
    }));
}

async function ensurePeer(callId, remoteUid, profile) {
    if (peerConnections.has(remoteUid)) return;
    const politeOfferer = currentUser.uid.localeCompare(remoteUid) < 0;
    const pc = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
    peerConnections.set(remoteUid, pc);
    localStream.getTracks().forEach(track => pc.addTrack(track, localStream));
    pc.ontrack = e => attachRemoteVideo(remoteUid, profile.displayName || profile.role, e.streams[0]);
    const pairId = [currentUser.uid, remoteUid].sort().join("__");
    const pairRef = doc(db, "calls", callId, "connections", pairId);
    const myCandidates = collection(pairRef, `${currentUser.uid}_candidates`);
    const theirCandidates = collection(pairRef, `${remoteUid}_candidates`);
    pc.onicecandidate = e => { if (e.candidate) addDoc(myCandidates, e.candidate.toJSON()); };
    callUnsubs.push(onSnapshot(theirCandidates, snap => snap.docChanges().forEach(c => { if (c.type === "added") pc.addIceCandidate(new RTCIceCandidate(c.doc.data())).catch(console.error); })));

    if (politeOfferer) {
        const offer = await pc.createOffer(); await pc.setLocalDescription(offer);
        await setDoc(pairRef, { offer: { type: offer.type, sdp: offer.sdp }, offerer: currentUser.uid }, { merge: true });
        callUnsubs.push(onSnapshot(pairRef, async s => { const data = s.data(); if (data?.answer && !pc.currentRemoteDescription) await pc.setRemoteDescription(new RTCSessionDescription(data.answer)); }));
    } else {
        callUnsubs.push(onSnapshot(pairRef, async s => {
            const data = s.data();
            if (data?.offer && !pc.currentRemoteDescription) {
                await pc.setRemoteDescription(new RTCSessionDescription(data.offer));
                const answer = await pc.createAnswer(); await pc.setLocalDescription(answer);
                await setDoc(pairRef, { answer: { type: answer.type, sdp: answer.sdp }, answerer: currentUser.uid }, { merge: true });
            }
        }));
    }
}

function attachRemoteVideo(uid, name, stream) {
    let card = document.querySelector(`[data-peer="${uid}"]`);
    if (!card) {
        card = document.createElement("article"); card.className = "video-card"; card.dataset.peer = uid;
        card.innerHTML = `<video autoplay playsinline></video><div class="video-label"></div>`;
        $("videoGrid").appendChild(card);
    }
    card.querySelector("video").srcObject = stream; card.querySelector(".video-label").textContent = name;
}
function removeRemoteVideo(uid) { document.querySelector(`[data-peer="${uid}"]`)?.remove(); }

async function startTranscription(callId) {
    stopTranscription();
    if (!localStream?.getAudioTracks().length) return;
    const status = $("transcriptionStatus");
    status.textContent = "Connecting…";

    try {
        const token = await currentUser.getIdToken();
        transcriptionAudioContext = new (window.AudioContext || window.webkitAudioContext)();
        const sampleRate = transcriptionAudioContext.sampleRate;
        const processorCode = `
            class FiniSpeakPCMProcessor extends AudioWorkletProcessor {
                process(inputs) {
                    const channel = inputs[0] && inputs[0][0];
                    if (channel) this.port.postMessage(new Float32Array(channel));
                    return true;
                }
            }
            registerProcessor('finispeak-pcm', FiniSpeakPCMProcessor);
        `;
        const blobUrl = URL.createObjectURL(new Blob([processorCode], { type: "application/javascript" }));
        await transcriptionAudioContext.audioWorklet.addModule(blobUrl);
        URL.revokeObjectURL(blobUrl);

        transcriptionSource = transcriptionAudioContext.createMediaStreamSource(new MediaStream(localStream.getAudioTracks()));
        transcriptionNode = new AudioWorkletNode(transcriptionAudioContext, "finispeak-pcm");
        // Keep the worklet alive without feeding microphone audio to the speakers.
        const silentGain = transcriptionAudioContext.createGain();
        silentGain.gain.value = 0;
        transcriptionSource.connect(transcriptionNode);
        transcriptionNode.connect(silentGain).connect(transcriptionAudioContext.destination);

        const scheme = location.protocol === "https:" ? "wss" : "ws";
        transcriptionSocket = new WebSocket(`${scheme}://${location.host}/ws/transcription`);
        transcriptionSocket.binaryType = "arraybuffer";
        transcriptionSocket.onopen = () => {
            transcriptionSocket.send(JSON.stringify({ type: "start", token, callId, sampleRate }));
        };
        transcriptionSocket.onmessage = async (event) => {
            const message = JSON.parse(event.data);
            if (message.type === "ready") { status.textContent = "Transcription connected — speak normally…"; return; }
            if (message.type === "listening") { status.textContent = "Listening 🎤"; return; }
            if (message.type === "processing") { status.textContent = "Processing speech…"; return; }
            if (message.type === "error") { status.textContent = `Transcription: ${message.message}`; return; }
            if (message.type === "final" && message.text?.trim() && activeCallId === callId) {
                status.textContent = "Listening 🎤";
                await addDoc(collection(db, "calls", callId, "transcripts"), {
                    speakerId: currentUser.uid,
                    speakerRole: currentCallRole,
                    speakerName: currentProfile.displayName || currentProfile.email,
                    language: message.language || null,
                    text: message.text.trim(),
                    isFinal: true,
                    createdAt: serverTimestamp(),
                    clientCreatedAt: Date.now()
                });
            }
        };
        transcriptionSocket.onerror = () => { status.textContent = "Transcription connection error — check Flask Terminal"; };
        transcriptionSocket.onclose = () => { if (activeCallId === callId) status.textContent = "Transcription stopped"; };

        transcriptionNode.port.onmessage = (event) => {
            if (!transcriptionSocket || transcriptionSocket.readyState !== WebSocket.OPEN) return;
            const floats = event.data;
            const pcm = new Int16Array(floats.length);
            for (let i = 0; i < floats.length; i++) {
                const sample = Math.max(-1, Math.min(1, floats[i]));
                pcm[i] = sample < 0 ? sample * 32768 : sample * 32767;
            }
            transcriptionSocket.send(pcm.buffer);
        };
    } catch (error) {
        status.textContent = `Transcription unavailable: ${error.message}`;
        stopTranscription(false);
    }
}

function stopTranscription(updateStatus = true) {
    if (transcriptionSocket) {
        try { if (transcriptionSocket.readyState === WebSocket.OPEN) transcriptionSocket.send(JSON.stringify({ type: "stop" })); } catch (_) {}
        try { transcriptionSocket.close(); } catch (_) {}
    }
    transcriptionSocket = null;
    try { transcriptionNode?.disconnect(); } catch (_) {}
    try { transcriptionSource?.disconnect(); } catch (_) {}
    transcriptionNode = null; transcriptionSource = null;
    if (transcriptionAudioContext) transcriptionAudioContext.close().catch(() => {});
    transcriptionAudioContext = null;
    if (updateStatus && $("transcriptionStatus")) $("transcriptionStatus").textContent = "Transcription stopped";
}

function renderTranscript(rows) {
    const list = $("transcriptList");
    if (!rows.length) {
        list.innerHTML = '<p class="transcript-empty">Transcript lines from Customer 1, Customer 2, and the translator will appear here.</p>';
        return;
    }
    list.innerHTML = "";
    for (const row of rows) {
        const item = document.createElement("div"); item.className = "transcript-line";
        const speaker = document.createElement("div"); speaker.className = "transcript-speaker";
        const name = document.createElement("span"); name.textContent = row.speakerName || "Participant";
        const role = document.createElement("span"); role.className = "transcript-role"; role.textContent = formatTranscriptRole(row.speakerRole);
        const text = document.createElement("p"); text.className = "transcript-text"; text.textContent = row.text || "";
        speaker.append(name, role); item.append(speaker, text); list.appendChild(item);
    }
    list.scrollTop = list.scrollHeight;
}

function formatTranscriptRole(role) {
    if (role === "caller") return "Customer 1";
    if (role === "receiver") return "Customer 2";
    if (role === "translator") return "Translator";
    return role || "Participant";
}

async function requestTranslator() {
    if (!activeCallId) return;
    await updateDoc(doc(db, "calls", activeCallId), { translationStatus: "requested" });
    $("callStatus").textContent = "Translator requested. Available translators will receive a request.";
}
function toggleMute() { const t = localStream?.getAudioTracks()[0]; if (!t) return; t.enabled = !t.enabled; $("muteButton").textContent = t.enabled ? "Mute" : "Unmute"; }
function toggleCamera() { const t = localStream?.getVideoTracks()[0]; if (!t) return; t.enabled = !t.enabled; $("cameraButton").textContent = t.enabled ? "Camera Off" : "Camera On"; }
async function endCall() { if (activeCallId) await updateDoc(doc(db, "calls", activeCallId), { status: "ended", endedAt: serverTimestamp() }); cleanupCall(); show("dashboardView"); loadConversationHistory(); }
function cleanupListeners() { callUnsubs.forEach(u => u()); callUnsubs = []; }
function cleanupCall(stopMedia = true) {
    stopTranscription();
    cleanupListeners(); peerConnections.forEach(pc => pc.close()); peerConnections.clear();
    document.querySelectorAll("[data-peer]").forEach(e => e.remove());
    if (stopMedia && localStream) { localStream.getTracks().forEach(t => t.stop()); localStream = null; $("localVideo").srcObject = null; }
    activeCallId = null; currentCallRole = null;
}


function cleanupDashboardListeners() {
    dashboardUnsubs.forEach(unsub => unsub());
    dashboardUnsubs = [];
    pendingIncomingCall = null;
    $("incomingCallModal")?.classList.add("hidden");
}

function startDashboardListeners() {
    cleanupDashboardListeners();
    if (!currentUser || !currentProfile) return;

    if (currentProfile.role === "customer") {
        const incoming = query(collection(db, "calls"), where("receiverId", "==", currentUser.uid), where("status", "==", "ringing"));
        dashboardUnsubs.push(onSnapshot(incoming, snap => {
            const callDoc = snap.docs[0];
            if (!callDoc || activeCallId) { if (!pendingIncomingCall) $("incomingCallModal").classList.add("hidden"); return; }
            pendingIncomingCall = { id: callDoc.id, ...callDoc.data(), kind: "customer" };
            $("incomingCallEyebrow").textContent = "Incoming FiniSpeak call";
            $("incomingCallTitle").textContent = `${pendingIncomingCall.callerName || "A customer"} is calling you`;
            $("incomingCallDetails").textContent = "Accept to connect. Live transcription starts after you join the call.";
            $("acceptIncomingCall").textContent = "Accept";
            $("incomingCallModal").classList.remove("hidden");
        }));
    } else if (currentProfile.role === "translator") {
        const requests = query(collection(db, "calls"), where("translationStatus", "==", "requested"));
        dashboardUnsubs.push(onSnapshot(requests, snap => {
            const callDoc = snap.docs.find(d => !d.data().translatorId && d.data().status !== "ended");
            if (!callDoc || activeCallId) { if (!pendingIncomingCall) $("incomingCallModal").classList.add("hidden"); return; }
            pendingIncomingCall = { id: callDoc.id, ...callDoc.data(), kind: "translator" };
            $("incomingCallEyebrow").textContent = "Interpretation request";
            $("incomingCallTitle").textContent = "A call needs a translator";
            $("incomingCallDetails").textContent = `${pendingIncomingCall.callerName || "Customer 1"} and ${pendingIncomingCall.receiverName || "Customer 2"} are requesting interpretation.`;
            $("translatorRequestStatus").textContent = "New interpretation request waiting — open it to join the call.";
            $("acceptIncomingCall").textContent = "Join Call";
            $("incomingCallModal").classList.remove("hidden");
        }));
    }
}

async function acceptIncomingCall() {
    if (!pendingIncomingCall) return;
    const pending = pendingIncomingCall;
    pendingIncomingCall = null;
    $("incomingCallModal").classList.add("hidden");
    try {
        const callRef = doc(db, "calls", pending.id);
        if (pending.kind === "customer") {
            await updateDoc(callRef, { status: "connected", startedAt: serverTimestamp() });
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
    $("incomingCallModal").classList.add("hidden");
    try {
        if (pending.kind === "customer") {
            await updateDoc(doc(db, "calls", pending.id), { status: "declined", endedAt: serverTimestamp() });
        }
        // Translator declines only this visible request locally. Another translator can still accept it.
    } catch (error) {
        $("dashboardStatus").textContent = error.message;
    }
}

async function loadConversationHistory() {
    if (!currentUser || !db) return;
    const history = $("conversationHistory");
    history.innerHTML = '<p class="transcript-empty">Loading conversations…</p>';
    try {
        const fields = currentProfile.role === "translator" ? ["translatorId"] : ["callerId", "receiverId"];
        const snapshots = await Promise.all(fields.map(field => getDocs(query(collection(db, "calls"), where(field, "==", currentUser.uid)))));
        historyCalls.clear();
        snapshots.forEach(snapshot => snapshot.forEach(d => historyCalls.set(d.id, { id: d.id, ...d.data() })));
        const rows = [...historyCalls.values()]
            .filter(call => ["connected", "ended"].includes(call.status) || call.startedAt)
            .sort((a, b) => callMillis(b) - callMillis(a));
        renderConversationHistory(rows);
    } catch (error) {
        history.innerHTML = `<p class="status">Could not load conversation history: ${escapeHtml(error.message)}</p>`;
    }
}

function callMillis(call) {
    return call.endedAt?.toMillis?.() || call.startedAt?.toMillis?.() || call.createdAt?.toMillis?.() || 0;
}

function renderConversationHistory(rows) {
    const history = $("conversationHistory");
    if (!rows.length) {
        history.innerHTML = '<p class="transcript-empty">No previous conversations yet.</p>';
        return;
    }
    history.innerHTML = "";
    for (const call of rows) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "conversation-item";
        const other = currentProfile.role === "translator"
            ? `${call.callerName || "Customer 1"} ↔ ${call.receiverName || "Customer 2"}`
            : (currentUser.uid === call.callerId ? call.receiverName : call.callerName) || "FiniSpeak customer";
        const date = call.startedAt?.toDate?.() || call.createdAt?.toDate?.();
        const dateText = date ? date.toLocaleString() : "Previous call";
        button.innerHTML = `<strong>${escapeHtml(other)}</strong><span class="conversation-meta">${escapeHtml(dateText)} · View transcript</span>`;
        button.onclick = () => openHistoryTranscript(call);
        history.appendChild(button);
    }
}

async function openHistoryTranscript(call) {
    $("historyTranscriptTitle").textContent = "Call transcript";
    const date = call.startedAt?.toDate?.() || call.createdAt?.toDate?.();
    $("historyTranscriptMeta").textContent = date ? date.toLocaleString() : "Previous conversation";
    const list = $("historyTranscriptList");
    list.innerHTML = '<p class="transcript-empty">Loading transcript…</p>';
    $("transcriptModal").classList.remove("hidden");
    try {
        const snap = await getDocs(collection(db, "calls", call.id, "transcripts"));
        const rows = snap.docs.map(d => ({ id: d.id, ...d.data() }));
        rows.sort((a, b) => (a.createdAt?.toMillis?.() || a.clientCreatedAt || 0) - (b.createdAt?.toMillis?.() || b.clientCreatedAt || 0));
        renderTranscriptInto(list, rows);
    } catch (error) {
        list.innerHTML = `<p class="status">Could not load transcript: ${escapeHtml(error.message)}</p>`;
    }
}

function renderTranscriptInto(list, rows) {
    if (!rows.length) {
        list.innerHTML = '<p class="transcript-empty">No transcript was saved for this conversation.</p>';
        return;
    }
    list.innerHTML = "";
    for (const row of rows) {
        const item = document.createElement("div"); item.className = "transcript-line";
        const speaker = document.createElement("div"); speaker.className = "transcript-speaker";
        const name = document.createElement("span"); name.textContent = row.speakerName || "Participant";
        const role = document.createElement("span"); role.className = "transcript-role"; role.textContent = formatTranscriptRole(row.speakerRole);
        const text = document.createElement("p"); text.className = "transcript-text"; text.textContent = row.text || "";
        speaker.append(name, role); item.append(speaker, text); list.appendChild(item);
    }
}

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value ?? "";
    return div.innerHTML;
}

boot();
