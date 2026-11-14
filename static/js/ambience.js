/**
 * « Revivre mon rêve » : micro-vidéo et ambiance sonore générées dans le navigateur.
 *
 * - Image en plein écran animée lentement (effet « Ken Burns »), récit affiché
 *   phrase par phrase.
 * - Ambiance sonore synthétisée en direct avec la Web Audio API, selon l'émotion
 *   du rêve : accords, textures de bruit filtré, notes de cloche, pulsations.
 *   Aucun fichier audio, aucun appel d'API, aucun droit d'auteur.
 */
(() => {
  "use strict";

  const trigger = document.getElementById("relive-button");
  const overlay = document.getElementById("relive-overlay");
  if (!trigger || !overlay) return;

  const closeButton = document.getElementById("relive-close");
  const soundButton = document.getElementById("relive-sound");
  const caption = document.getElementById("relive-caption");
  const emotion = overlay.dataset.emotion || "neutre";
  const story = (overlay.dataset.story || "").trim();

  /* ---------------------------------------------------------------------------
   * Paramètres sonores par émotion.
   * Fréquences en hertz : accord de la nappe, note grave, type d'onde, filtre,
   * bruit (vent / pluie / grondement), cloches, tremolo.
   * ------------------------------------------------------------------------- */
  const PRESETS = {
    heureux: {
      chord: [261.63, 329.63, 392.0, 493.88], // do majeur 7
      bass: 130.81, wave: "triangle", cutoff: 1800,
      noise: 0.015, noiseFreq: 3000, bells: [523.25, 659.25, 783.99, 987.77], bellEvery: 2.2,
      tremolo: 0,
    },
    stressant: {
      chord: [110.0, 116.54, 164.81], // la, si bémol : dissonance
      bass: 55.0, wave: "sawtooth", cutoff: 500,
      noise: 0.04, noiseFreq: 200, bells: [], bellEvery: 0,
      tremolo: 5.5,
    },
    triste: {
      chord: [220.0, 261.63, 329.63], // la mineur
      bass: 110.0, wave: "sine", cutoff: 900,
      noise: 0.03, noiseFreq: 5000, bells: [440.0, 523.25], bellEvery: 5,
      tremolo: 0,
    },
    colere: {
      chord: [98.0, 146.83, 155.56],
      bass: 49.0, wave: "sawtooth", cutoff: 380,
      noise: 0.06, noiseFreq: 120, bells: [], bellEvery: 0,
      tremolo: 2.5,
    },
    surprenant: {
      chord: [293.66, 415.3, 523.25], // quarte augmentée : étrangeté
      bass: 146.83, wave: "triangle", cutoff: 2200,
      noise: 0.012, noiseFreq: 6000, bells: [1174.66, 1396.91, 1661.22, 1975.53], bellEvery: 0.9,
      tremolo: 0,
    },
    neutre: {
      chord: [196.0, 293.66], // quinte
      bass: 98.0, wave: "sine", cutoff: 1200,
      noise: 0.025, noiseFreq: 800, bells: [], bellEvery: 0,
      tremolo: 0,
    },
  };

  let audio = null; // { context, master, nodes, timers }
  let captionTimer = null;
  let lastFocus = null;

  function createNoise(context) {
    const length = context.sampleRate * 2;
    const buffer = context.createBuffer(1, length, context.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < length; i += 1) data[i] = Math.random() * 2 - 1;
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.loop = true;
    return source;
  }

  /** Simule une réverbération simple : écho filtré qui se répète en s'atténuant. */
  function createSpace(context) {
    const input = context.createGain();
    const delay = context.createDelay(1.5);
    const feedback = context.createGain();
    const tone = context.createBiquadFilter();
    delay.delayTime.value = 0.42;
    feedback.gain.value = 0.45;
    tone.type = "lowpass";
    tone.frequency.value = 2400;
    input.connect(delay).connect(tone).connect(feedback).connect(delay);
    const output = context.createGain();
    input.connect(output);
    tone.connect(output);
    return { input, output };
  }

  function startAmbience() {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return null;
    const preset = PRESETS[emotion] || PRESETS.neutre;
    // Créé dans le geste de l'utilisateur : indispensable sur Safari iOS.
    const context = new AudioCtx();
    if (context.state === "suspended") context.resume().catch(() => {});
    const now = context.currentTime;

    const master = context.createGain();
    master.gain.setValueAtTime(0, now);
    master.gain.linearRampToValueAtTime(0.5, now + 3); // apparition en douceur
    const space = createSpace(context);
    space.output.connect(master).connect(context.destination);

    const nodes = [];
    const timers = [];

    // Nappe : accord légèrement désaccordé, filtre qui « respire » lentement.
    const pad = context.createBiquadFilter();
    pad.type = "lowpass";
    pad.frequency.value = preset.cutoff;
    pad.Q.value = 0.7;
    const breath = context.createOscillator();
    const breathDepth = context.createGain();
    breath.frequency.value = 0.07;
    breathDepth.gain.value = preset.cutoff * 0.35;
    breath.connect(breathDepth).connect(pad.frequency);
    breath.start();
    nodes.push(breath);

    const padGain = context.createGain();
    padGain.gain.value = 0.11;
    pad.connect(padGain).connect(space.input);

    // Tremolo (rêves tendus) : le volume de la nappe pulse.
    if (preset.tremolo) {
      const lfo = context.createOscillator();
      const depth = context.createGain();
      lfo.frequency.value = preset.tremolo;
      depth.gain.value = 0.06;
      lfo.connect(depth).connect(padGain.gain);
      lfo.start();
      nodes.push(lfo);
    }

    [...preset.chord, preset.bass].forEach((frequency, index) => {
      [-4, 4].forEach((cents) => {
        const osc = context.createOscillator();
        osc.type = index === preset.chord.length ? "sine" : preset.wave;
        osc.frequency.value = frequency;
        osc.detune.value = cents;
        osc.connect(pad);
        osc.start();
        nodes.push(osc);
      });
    });

    // Texture de bruit filtré : vent, pluie ou grondement selon le filtre.
    if (preset.noise) {
      const noise = createNoise(context);
      const filter = context.createBiquadFilter();
      const gain = context.createGain();
      filter.type = preset.noiseFreq > 1500 ? "highpass" : "lowpass";
      filter.frequency.value = preset.noiseFreq;
      gain.gain.value = preset.noise;
      noise.connect(filter).connect(gain).connect(master);
      noise.start();
      nodes.push(noise);
    }

    // Cloches : notes brèves, à intervalles un peu irréguliers.
    if (preset.bells.length) {
      const ring = () => {
        const t = context.currentTime;
        const osc = context.createOscillator();
        const env = context.createGain();
        osc.type = "sine";
        osc.frequency.value = preset.bells[Math.floor(Math.random() * preset.bells.length)];
        env.gain.setValueAtTime(0, t);
        env.gain.linearRampToValueAtTime(0.07, t + 0.02);
        env.gain.exponentialRampToValueAtTime(0.0001, t + 3);
        osc.connect(env).connect(space.input);
        osc.start(t);
        osc.stop(t + 3.1);
        timers.push(setTimeout(ring, (preset.bellEvery * (0.6 + Math.random() * 0.8)) * 1000));
      };
      timers.push(setTimeout(ring, 1200));
    }

    return { context, master, nodes, timers };
  }

  function stopAmbience() {
    if (!audio) return;
    const { context, master, nodes, timers } = audio;
    timers.forEach(clearTimeout);
    const now = context.currentTime;
    master.gain.cancelScheduledValues(now);
    master.gain.setValueAtTime(master.gain.value, now);
    master.gain.linearRampToValueAtTime(0, now + 0.8); // disparition en douceur
    setTimeout(() => {
      nodes.forEach((node) => {
        try {
          node.stop();
        } catch {
          /* déjà arrêté */
        }
      });
      context.close();
    }, 900);
    audio = null;
  }

  /* --- Récit affiché phrase par phrase ------------------------------------- */
  function playCaptions() {
    const sentences = story.match(/[^.!?…]+[.!?…]*/g) || [story];
    let index = 0;
    const next = () => {
      caption.classList.remove("is-visible");
      captionTimer = setTimeout(() => {
        const sentence = sentences[index].trim();
        caption.textContent = sentence;
        caption.classList.add("is-visible");
        index = (index + 1) % sentences.length;
        // Temps de lecture : environ 70 ms par caractère, 3,5 s minimum.
        captionTimer = setTimeout(next, Math.max(3500, sentence.length * 70));
      }, 600);
    };
    next();
  }

  function updateSoundButton() {
    const on = Boolean(audio);
    soundButton.setAttribute("aria-pressed", String(on));
    soundButton.innerHTML = on
      ? '<i class="bi bi-volume-up" aria-hidden="true"></i><span class="visually-hidden">Couper le son</span>'
      : '<i class="bi bi-volume-mute" aria-hidden="true"></i><span class="visually-hidden">Activer le son</span>';
  }

  function open() {
    lastFocus = document.activeElement;
    overlay.hidden = false;
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => overlay.classList.add("is-open"));
    audio = startAmbience();
    updateSoundButton();
    playCaptions();
    closeButton.focus();
  }

  function close() {
    stopAmbience();
    clearTimeout(captionTimer);
    overlay.classList.remove("is-open");
    document.body.style.overflow = "";
    setTimeout(() => {
      overlay.hidden = true;
    }, 400);
    if (lastFocus) lastFocus.focus();
  }

  trigger.addEventListener("click", open);
  closeButton.addEventListener("click", close);
  soundButton.addEventListener("click", () => {
    if (audio) stopAmbience();
    else audio = startAmbience();
    updateSoundButton();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !overlay.hidden) close();
  });
})();
