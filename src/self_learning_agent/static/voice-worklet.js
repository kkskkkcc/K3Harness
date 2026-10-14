// Collect PCM only while the user has explicitly started recording.
class AgentPCMRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(2048);
    this.offset = 0;
    this.active = true;
    this.port.onmessage = (event) => {
      if (event.data === "stop") {
        this.active = false;
        if (this.offset) this.port.postMessage(this.buffer.slice(0, this.offset));
        this.port.postMessage("stopped");
      }
    };
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!this.active || !channel) return true;
    for (const sample of channel) {
      this.buffer[this.offset++] = sample;
      if (this.offset === this.buffer.length) {
        this.port.postMessage(this.buffer.slice());
        this.offset = 0;
      }
    }
    // Audio outputs remain zero: never play microphone feedback.
    return true;
  }
}
registerProcessor("agent-pcm-recorder", AgentPCMRecorder);
