let audioCtx: AudioContext | null = null;
let osc: OscillatorNode | null = null;
let gainNode: GainNode | null = null;
let sirenInterval: any = null;
let isPlaying = false;

export function isSirenActive(): boolean {
  return isPlaying;
}

export function startEmergencySiren() {
  if (isPlaying) return;
  try {
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioContextClass) return;
    audioCtx = new AudioContextClass();
    osc = audioCtx.createOscillator();
    gainNode = audioCtx.createGain();

    osc.type = 'sawtooth';
    gainNode.gain.setValueAtTime(0.06, audioCtx.currentTime);
    osc.frequency.setValueAtTime(750, audioCtx.currentTime);

    let high = true;
    sirenInterval = setInterval(() => {
      if (!osc || !audioCtx) return;
      high = !high;
      try {
        osc.frequency.exponentialRampToValueAtTime(high ? 750 : 480, audioCtx.currentTime + 0.35);
      } catch (e) {}
    }, 450);

    osc.connect(gainNode);
    gainNode.connect(audioCtx.destination);
    osc.start();
    isPlaying = true;
  } catch (err) {
    console.warn('Web Audio siren initialization prevented:', err);
  }
}

export function stopEmergencySiren() {
  if (sirenInterval) {
    clearInterval(sirenInterval);
    sirenInterval = null;
  }
  if (osc) {
    try {
      osc.stop();
      osc.disconnect();
    } catch (e) {}
    osc = null;
  }
  if (gainNode) {
    try {
      gainNode.disconnect();
    } catch (e) {}
    gainNode = null;
  }
  if (audioCtx) {
    try {
      audioCtx.close();
    } catch (e) {}
    audioCtx = null;
  }
  isPlaying = false;
}
