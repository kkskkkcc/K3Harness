// Produce the PCM WAV expected by SenseVoice, without cloud speech APIs.
globalThis.AgentVoiceCodec = {
  toWav(chunks, sampleRate) {
    const total = chunks.reduce((size, chunk) => size + chunk.length, 0);
    if (!total || sampleRate < 16000) throw new Error("没有采集到有效音频，请检查麦克风。");
    const samples = new Float32Array(total);
    let offset = 0;
    for (const chunk of chunks) { samples.set(chunk, offset); offset += chunk.length; }
    const outputRate = 16000;
    const count = Math.floor(total * outputRate / sampleRate);
    const buffer = new ArrayBuffer(44 + count * 2);
    const view = new DataView(buffer);
    const write = (pos, text) => [...text].forEach((ch, i) => view.setUint8(pos + i, ch.charCodeAt(0)));
    write(0, "RIFF"); view.setUint32(4, 36 + count * 2, true);
    write(8, "WAVE"); write(12, "fmt "); view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, outputRate, true); view.setUint32(28, outputRate * 2, true);
    view.setUint16(32, 2, true); view.setUint16(34, 16, true);
    write(36, "data"); view.setUint32(40, count * 2, true);
    for (let i = 0; i < count; i++) {
      const start = Math.floor(i * sampleRate / outputRate);
      const end = Math.min(total, Math.floor((i + 1) * sampleRate / outputRate));
      let sum = 0;
      for (let j = start; j < end; j++) sum += samples[j];
      const value = Math.max(-1, Math.min(1, sum / Math.max(1, end - start)));
      view.setInt16(44 + i * 2, value < 0 ? value * 32768 : value * 32767, true);
    }
    return new Blob([buffer], { type: "audio/wav" });
  },
};
