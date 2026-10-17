export const PUBLIC_ICE_SERVERS = [{ urls: ["stun:stun.l.google.com:19302", "stun:stun.cloudflare.com:3478"] }];

function usableServer(server) {
    if (!server || server.urls == null) return false;
    if (Array.isArray(server.urls)) return server.urls.length > 0;
    return String(server.urls).length > 0;
}

export function normalizeIceConfiguration(payload) {
    const servers = Array.isArray(payload?.iceServers) ? payload.iceServers.filter(usableServer) : [];
    return {
        iceServers: servers.length ? servers : PUBLIC_ICE_SERVERS.map(server => ({ urls: [...server.urls] })),
        relay: Boolean(payload?.relay)
    };
}

export function liveReceiver(pc, kind) {
    return (pc?.getReceivers?.() || []).some(receiver => {
        const track = receiver.track;
        return track?.kind === kind && track.readyState === "live" && track.muted === false && track.enabled !== false;
    });
}

export function isOfferer(localId, remoteId) {
    return String(localId) < String(remoteId);
}

export function offerResponse(signalingState, { offerer = false, makingOffer = false } = {}) {
    if (offerer && (makingOffer || signalingState === "have-local-offer")) return "ignore";
    if (signalingState === "stable" || signalingState === "have-remote-offer") return "answer";
    if (signalingState === "have-local-offer" || signalingState === "have-local-pranswer") return "rollback";
    return "restart";
}

function enqueue(pc, task) {
    const previous = pc._signalQueue || Promise.resolve();
    const next = previous.then(task, task);
    pc._signalQueue = next.then(() => undefined, () => undefined);
    return next;
}

export function attachMeshHandlers(pc, { offerer, send, onTrack, onError }) {
    pc._offerer = Boolean(offerer);
    pc._makingOffer = false;
    pc.onnegotiationneeded = () => {
        if (!pc._offerer) return;
        sendOffer(pc, send).catch(error => onError?.(error));
    };
    pc.onicecandidate = event => {
        if (!event.candidate) return;
        Promise.resolve(send("ice", event.candidate.toJSON())).catch(error => onError?.(error));
    };
    pc.ontrack = event => onTrack?.(event.track, event.streams?.[0]);
    return pc;
}

async function sendOfferNow(pc, send, { iceRestart = false } = {}) {
    if (!pc || pc._makingOffer || pc._offerer === false || pc.signalingState !== "stable") return false;
    pc._makingOffer = true;
    try {
        const offer = await pc.createOffer(iceRestart ? { iceRestart: true } : undefined);
        if (pc.signalingState !== "stable") return false;
        await pc.setLocalDescription(offer);
        await send("offer", { type: pc.localDescription.type, sdp: pc.localDescription.sdp });
        return true;
    } finally {
        pc._makingOffer = false;
    }
}

export function sendOffer(pc, send, options) {
    return enqueue(pc, () => sendOfferNow(pc, send, options));
}

export function resendLocalOffer(pc, send) {
    return enqueue(pc, async () => {
        if (pc?._offerer === false || pc?.signalingState !== "have-local-offer" || !pc.localDescription) return false;
        await send("offer", { type: pc.localDescription.type, sdp: pc.localDescription.sdp });
        return true;
    });
}

async function applyMeshSignalNow(pc, message, send) {
    if (!pc || !message) return;
    if (message.type === "offer") {
        const payload = message.payload || {};
        const sameOffer = pc.signalingState === "stable"
            && pc.currentRemoteDescription?.type === "offer"
            && pc.currentRemoteDescription?.sdp === payload.sdp;
        if (sameOffer) {
            if (pc.localDescription?.type === "answer") {
                await send("answer", { type: pc.localDescription.type, sdp: pc.localDescription.sdp });
            }
            return;
        }
        const action = offerResponse(pc.signalingState, { offerer: pc._offerer, makingOffer: pc._makingOffer });
        if (action === "ignore") return;
        if (action === "rollback") {
            try {
                await pc.setLocalDescription({ type: "rollback" });
            } catch (_) {
                return "restart";
            }
            if (pc.signalingState !== "stable") return "restart";
        } else if (action === "restart") {
            return "restart";
        }
        await pc.setRemoteDescription(new RTCSessionDescription(payload));
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        await send("answer", { type: pc.localDescription.type, sdp: pc.localDescription.sdp });
        return;
    }
    if (message.type === "answer") {
        if (pc.signalingState !== "have-local-offer") return;
        await pc.setRemoteDescription(new RTCSessionDescription(message.payload));
        return;
    }
    if (message.type === "ice") {
        if (!message.payload) return;
        if (!pc.remoteDescription) return "queue";
        await pc.addIceCandidate(new RTCIceCandidate(message.payload));
    }
}

export function applyMeshSignal(pc, message, send) {
    return enqueue(pc, () => applyMeshSignalNow(pc, message, send));
}
