(() => {
  const recordButton = document.querySelector("#voice-record");
  const deviceButton = document.querySelector("#voice-devices");
  const deviceSelect = document.querySelector("#voice-input-device");
  const autoSendToggle = document.querySelector("#voice-autosend");
  const playbackToggle = document.querySelector("#voice-playback");
  const speakerButton = document.querySelector("#voice-speaker-test");
  const statusText = document.querySelector("#voice-status");
  const player = document.querySelector("#voice-player");
  let stream, context, node, source, chunks = [], timer, elapsedTimer;
  let asrAvailable = false, ttsAvailable = false, starting = false, stopping = false;
  let playbackBusy = false, playbackURL = null;

  function note(text) { statusText.textContent = text; }
  function updateControls() {
    const busy = state.sending || state.transcribing || state.modelSwitching || state.finalized;
    recordButton.disabled = starting || stopping || busy || playbackBusy || !asrAvailable;
    deviceButton.disabled = busy || state.recording || starting || stopping;
    deviceSelect.disabled = deviceButton.disabled;
    speakerButton.disabled = busy || state.recording || playbackBusy || !ttsAvailable;
    playbackToggle.disabled = !ttsAvailable;
    recordButton.textContent = state.recording ? "停止并识别" : "开始录音";
    recordButton.classList.toggle("recording", state.recording);
  }

  async function checkAudio() {
    try {
      const audio = await apiRequest("/v1/audio/status");
      asrAvailable = Boolean(audio.enabled && audio.asr?.available);
      ttsAvailable = Boolean(audio.enabled && audio.tts?.available);
      note(asrAvailable
        ? "语音已就绪。选择 K03S 麦克风，点击开始录音后请说话；识别完成默认自动发送。"
        : audio.message || "K3 语音服务尚未就绪，文字聊天仍可用。");
    } catch (error) { note(`语音服务检查失败：${error.message}`); }
    updateControls();
  }

  async function devices() {
    const selected = deviceSelect.value;
    const list = (await navigator.mediaDevices.enumerateDevices()).filter((device) => device.kind === "audioinput");
    deviceSelect.replaceChildren(new Option("系统默认麦克风", ""));
    for (const device of list) {
      if (device.deviceId && device.deviceId !== "default") {
        deviceSelect.append(new Option(device.label || `麦克风 ${deviceSelect.options.length}`, device.deviceId));
      }
    }
    if ([...deviceSelect.options].some((item) => item.value === selected)) deviceSelect.value = selected;
  }

  function mediaCheck() {
    if (!navigator.mediaDevices?.getUserMedia || !window.isSecureContext) {
      throw new Error("请用 Edge/Chrome 打开 http://127.0.0.1:18000/；普通远端 HTTP 页面不能录音。");
    }
  }

  async function selectDevices() {
    deviceButton.disabled = true;
    let permissionStream;
    try {
      mediaCheck();
      permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      await devices();
      note("请在麦克风列表选择 K03S。若名称是 USB Audio Device，请对照 Windows 声音设置。");
    } catch (error) { note(`无法打开麦克风：${error.message}`); }
    finally { permissionStream?.getTracks().forEach((track) => track.stop()); updateControls(); }
  }

  async function releaseMicrophone() {
    clearTimeout(timer); clearInterval(elapsedTimer);
    stream?.getTracks().forEach((track) => track.stop());
    source?.disconnect(); node?.disconnect();
    if (context && context.state !== "closed") await context.close();
    stream = context = source = node = null;
  }

  async function startRecording() {
    if (state.sending || state.transcribing || state.modelSwitching || state.finalized || starting || playbackBusy) return;
    starting = true; state.recording = true; setSending(state.sending);
    try {
      mediaCheck();
      player.pause();
      const constraints = { channelCount: 1, echoCancellation: true, noiseSuppression: true };
      if (deviceSelect.value) constraints.deviceId = { exact: deviceSelect.value };
      stream = await navigator.mediaDevices.getUserMedia({ audio: constraints });
      context = new AudioContext({ sampleRate: 16000 });
      await context.resume();
      await context.audioWorklet.addModule("/static/voice-worklet.js");
      source = context.createMediaStreamSource(stream);
      node = new AudioWorkletNode(context, "agent-pcm-recorder", { channelCount: 1 });
      chunks = [];
      node.port.onmessage = (event) => { if (event.data instanceof Float32Array) chunks.push(event.data); };
      source.connect(node); node.connect(context.destination);
      await devices();
      const microphone = stream.getAudioTracks()[0]?.label || "已选麦克风";
      const startedAt = Date.now();
      const tick = () => note(`请开始说话 · ${microphone} · 已录音 ${Math.floor((Date.now() - startedAt) / 1000)} 秒（最多 20 秒）`);
      tick(); elapsedTimer = setInterval(tick, 500);
      timer = setTimeout(stopRecording, 20000);
    } catch (error) {
      await releaseMicrophone(); state.recording = false;
      note(`录音失败：${error.message}`);
    } finally { starting = false; setSending(state.sending); }
  }

  async function stopRecording() {
    if (!state.recording || starting || stopping) return;
    stopping = true; clearTimeout(timer); clearInterval(elapsedTimer); updateControls();
    try {
      const sampleRate = context.sampleRate;
      await new Promise((resolve, reject) => {
        const deadline = setTimeout(() => reject(new Error("录音停止超时，请重新录制。")), 2000);
        node.port.onmessage = (event) => {
          if (event.data instanceof Float32Array) chunks.push(event.data);
          if (event.data === "stopped") { clearTimeout(deadline); resolve(); }
        };
        node.port.postMessage("stop");
      });
      await releaseMicrophone();
      state.recording = false; state.transcribing = true; setSending(state.sending);
      note("录音结束，正在由 K3 识别…");
      const count = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      const energy = chunks.reduce((sum, chunk) => sum + chunk.reduce((acc, value) => acc + value * value, 0), 0);
      if (count < sampleRate * 0.3 || Math.sqrt(energy / Math.max(1, count)) < 0.0001) {
        throw new Error("录音太短或没有声音，请选对 K03S 麦克风并说话至少一秒。");
      }
      const wav = AgentVoiceCodec.toWav(chunks, sampleRate);
      chunks = [];
      const form = new FormData(); form.append("file", wav, "microphone.wav");
      const response = await fetch("/v1/audio/transcribe", { method: "POST", body: form });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || `识别失败 (${response.status})`);
      const existingDraft = elements.messageInput.value.trim();
      elements.messageInput.value = [existingDraft, result.text].filter(Boolean).join("\n");
      resizeComposer(); updateContextMeter();
      if (autoSendToggle.checked && !existingDraft) {
        note(`识别完成：${result.text}。正在发送…`);
        state.transcribing = false;
        setSending(false);
        await sendMessage(result.text);
      } else {
        note(existingDraft
          ? `识别完成：${result.text}。输入框已有草稿，请核对后点击发送。`
          : `识别完成：${result.text}。请核对后点击发送。`);
      }
    } catch (error) { note(`语音识别失败：${error.message}`); showToast(error.message, "error"); }
    finally {
      await releaseMicrophone(); chunks = [];
      stopping = false; state.recording = false; state.transcribing = false;
      setSending(state.sending); elements.messageInput.focus();
    }
  }

  async function speak(text) {
    if (playbackBusy || state.recording || !ttsAvailable) return;
    playbackBusy = true; updateControls(); note("K3 正在合成语音回复…");
    try {
      player.pause();
      const response = await fetch("/v1/audio/synthesize", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice_id: "zf_xiaobei" }),
      });
      if (!response.ok) {
        const result = await response.json(); throw new Error(result.detail || `语音合成失败 (${response.status})`);
      }
      if (playbackURL) URL.revokeObjectURL(playbackURL);
      playbackURL = URL.createObjectURL(await response.blob());
      player.src = playbackURL; player.hidden = false;
      try { await player.play(); note("正在播放 K3 合成的回复，声音从本机输出设备播放。"); }
      catch (_) { note("语音已生成，请点击下方播放按钮。浏览器可能阻止自动播放。"); }
    } catch (error) { note(`语音输出失败：${error.message}`); showToast(error.message, "error"); }
    finally { playbackBusy = false; updateControls(); }
  }

  recordButton.addEventListener("click", () => state.recording ? stopRecording() : startRecording());
  deviceButton.addEventListener("click", selectDevices);
  speakerButton.addEventListener("click", () => speak("你好，K3 语音测试已就绪。需要你说话时，网页会显示请开始说话。"));
  document.addEventListener("agent-controls-change", updateControls);
  document.addEventListener("agent-reply", (event) => { if (playbackToggle.checked) speak(event.detail); });
  window.addEventListener("pagehide", () => {
    stream?.getTracks().forEach((track) => track.stop());
    context?.close(); if (playbackURL) URL.revokeObjectURL(playbackURL);
  });
  checkAudio();
})();
