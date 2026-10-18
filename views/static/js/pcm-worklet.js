class FiniSpeakPCMProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.pending = new Float32Array(4096);
        this.pendingLength = 0;
    }

    process(inputs) {
        const channel = inputs[0] && inputs[0][0];
        if (!channel) return true;
        let offset = 0;
        while (offset < channel.length) {
            const available = this.pending.length - this.pendingLength;
            const count = Math.min(available, channel.length - offset);
            this.pending.set(channel.subarray(offset, offset + count), this.pendingLength);
            this.pendingLength += count;
            offset += count;
            if (this.pendingLength === this.pending.length) {
                this.port.postMessage(this.pending, [this.pending.buffer]);
                this.pending = new Float32Array(4096);
                this.pendingLength = 0;
            }
        }
        return true;
    }
}

registerProcessor("finispeak-pcm", FiniSpeakPCMProcessor);
