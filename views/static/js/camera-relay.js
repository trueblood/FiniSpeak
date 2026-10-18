export function parseRelayFrame(buffer) {
    const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
    if (bytes.length < 8 || bytes[0] !== 0x46 || bytes[1] !== 0x53 || bytes[2] !== 0x31) return null;
    const length = bytes[3];
    const start = 4 + length;
    if (!length || bytes.length < start + 3) return null;
    const uid = new TextDecoder().decode(bytes.subarray(4, start));
    if (bytes[start] !== 0xff || bytes[start + 1] !== 0xd8) return null;
    return { uid, jpeg: bytes.subarray(start) };
}

export function cameraCaptureSize(width, height) {
    const longest = Math.max(width || 0, height || 0);
    if (!longest) return { width: 0, height: 0 };
    const scale = Math.min(1, 640 / longest);
    const even = value => Math.max(2, Math.round((value * scale) / 2) * 2);
    return { width: even(width), height: even(height) };
}

export function createCameraRelay({ callId, url, getSource, onFrame, onState, onClock }) {
    let socket = null;
    let reconnect = 0;
    let timer = 0;
    let closed = false;
    let capturing = false;
    let lastEnabled = null;
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d", { alpha: false });

    function setOpen(open) {
        onState?.(open);
    }

    function connect() {
        if (closed) return;
        const next = new WebSocket(url);
        next.binaryType = "arraybuffer";
        socket = next;
        next.onopen = () => {
            if (socket !== next) return;
            lastEnabled = null;
            next.send(JSON.stringify({ type: "join", callId }));
        };
        next.onmessage = event => {
            if (socket !== next) return;
            if (typeof event.data === "string") {
                let message = null;
                try { message = JSON.parse(event.data); } catch (_) { message = null; }
                if (message?.type === "ready") setOpen(true);
                if (message?.type === "closed") stop();
                return;
            }
            const parsed = parseRelayFrame(event.data);
            if (parsed) onFrame?.(parsed.uid, parsed.jpeg);
        };
        next.onerror = () => {};
        next.onclose = () => {
            if (socket !== next) return;
            setOpen(false);
            if (!closed) reconnect = window.setTimeout(connect, 1000);
        };
    }

    function tick() {
        if (closed) return;
        onClock?.();
        if (!context) return;
        const source = getSource?.() || {};
        const element = source.element;
        const width = element?.videoWidth || element?.width || 0;
        const height = element?.videoHeight || element?.height || 0;
        const enabled = Boolean(source.enabled && width > 0 && height > 0);
        if (socket?.readyState === WebSocket.OPEN && enabled !== lastEnabled) {
            lastEnabled = enabled;
            if (!enabled) socket.send(JSON.stringify({ type: "camera", enabled: false }));
        }
        if (!enabled || capturing || socket?.readyState !== WebSocket.OPEN) return;
        const size = cameraCaptureSize(width, height);
        if (!size.width || !size.height) return;
        if (canvas.width !== size.width) canvas.width = size.width;
        if (canvas.height !== size.height) canvas.height = size.height;
        context.drawImage(element, 0, 0, size.width, size.height);
        capturing = true;
        canvas.toBlob(blob => {
            capturing = false;
            if (!blob || blob.size > 100000 || socket?.readyState !== WebSocket.OPEN || closed) return;
            blob.arrayBuffer().then(buffer => {
                if (socket?.readyState === WebSocket.OPEN) socket.send(buffer);
            }).catch(() => {});
        }, "image/jpeg", 0.55);
    }

    function stop() {
        closed = true;
        window.clearInterval(timer);
        window.clearTimeout(reconnect);
        setOpen(false);
        const current = socket;
        socket = null;
        try { current?.close(); } catch (_) {}
    }

    function reconnectNow() {
        if (closed) return;
        window.clearTimeout(reconnect);
        reconnect = 0;
        setOpen(false);
        const current = socket;
        socket = null;
        try { current?.close(); } catch (_) {}
        connect();
    }

    connect();
    timer = window.setInterval(tick, 125);
    if (closed) window.clearInterval(timer);
    return { stop, reconnect: reconnectNow };
}
