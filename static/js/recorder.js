/**
 * Enregistrement d'un rêve au micro et envoi au serveur.
 *
 * Étapes : demande d'accès au micro → enregistrement (MediaRecorder) avec
 * minuteur et arrêt automatique à la durée maximale → réécoute → envoi en
 * fetch (FormData) → redirection vers la page de suivi du rêve.
 *
 * Mesure aussi la durée des fichiers importés, pour que le serveur puisse
 * refuser les récits trop longs.
 */
(() => {
  "use strict";

  const root = document.getElementById("recorder");
  if (!root) return;

  const maxSeconds = Number(root.dataset.maxSeconds);
  const uploadUrl = root.dataset.uploadUrl;
  const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]").value;

  const el = (id) => document.getElementById(id);
  const alertBox = el("recorder-alert");
  const timer = el("recorder-timer");
  const progress = el("recorder-progress");
  const btnStart = el("btn-start");
  const btnStop = el("btn-stop");
  const btnRestart = el("btn-restart");
  const btnSend = el("btn-send");
  const review = el("recorder-review");
  const preview = el("recorder-preview");

  // Formats proposés au navigateur, par ordre de préférence (Chrome/Firefox : webm, Safari : mp4).
  const MIME_TYPES = [
    ["audio/webm;codecs=opus", "webm"],
    ["audio/webm", "webm"],
    ["audio/mp4", "m4a"],
    ["audio/ogg;codecs=opus", "ogg"],
  ];

  let recorder = null;
  let stream = null;
  let chunks = [];
  let startedAt = 0;
  let tickHandle = null;
  let recording = null; // { blob, extension, duration }

  const show = (node, visible) => node.classList.toggle("d-none", !visible);

  function showAlert(message, level = "danger") {
    alertBox.className = `alert alert-${level}`;
    alertBox.textContent = message;
  }

  function hideAlert() {
    alertBox.className = "alert d-none";
    alertBox.textContent = "";
  }

  function formatTime(seconds) {
    const s = Math.floor(seconds);
    return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }

  function pickMimeType() {
    return MIME_TYPES.find(([type]) => MediaRecorder.isTypeSupported(type)) || ["", "webm"];
  }

  function tick() {
    const elapsed = (Date.now() - startedAt) / 1000;
    timer.textContent = formatTime(elapsed);
    progress.style.width = `${Math.min((elapsed / maxSeconds) * 100, 100)}%`;
    if (elapsed >= maxSeconds) {
      stopRecording();
      showAlert("Durée maximale atteinte : l'enregistrement a été arrêté automatiquement.", "info");
    }
  }

  async function startRecording() {
    hideAlert();
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      const denied = error.name === "NotAllowedError" || error.name === "SecurityError";
      showAlert(
        denied
          ? "L'accès au micro a été refusé. Autorisez-le dans les réglages du navigateur, ou importez un fichier."
          : "Aucun micro n'a été trouvé. Branchez un micro ou importez un fichier.",
      );
      return;
    }

    const [mimeType, extension] = pickMimeType();
    recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    chunks = [];
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    });
    recorder.addEventListener("stop", () => {
      const duration = (Date.now() - startedAt) / 1000;
      const blob = new Blob(chunks, { type: recorder.mimeType || mimeType });
      recording = { blob, extension, duration };
      preview.src = URL.createObjectURL(blob);
      stream.getTracks().forEach((track) => track.stop());
      show(btnStop, false);
      show(review, true);
    });

    recorder.start(1000);
    startedAt = Date.now();
    tickHandle = setInterval(tick, 250);
    show(btnStart, false);
    show(btnStop, true);
    btnStop.focus();
  }

  function stopRecording() {
    clearInterval(tickHandle);
    if (recorder && recorder.state !== "inactive") recorder.stop();
  }

  function restart() {
    hideAlert();
    if (preview.src) URL.revokeObjectURL(preview.src);
    preview.removeAttribute("src");
    recording = null;
    timer.textContent = "00:00";
    progress.style.width = "0%";
    show(review, false);
    show(btnStart, true);
    btnStart.focus();
  }

  async function send() {
    if (!recording) return;
    if (recording.duration < 1) {
      showAlert("L'enregistrement est trop court. Racontez votre rêve puis réessayez.");
      return;
    }

    const formData = new FormData();
    formData.append("audio", recording.blob, `reve.${recording.extension}`);
    formData.append("audio_duration", recording.duration.toFixed(1));

    btnSend.disabled = true;
    btnRestart.disabled = true;
    btnSend.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Envoi en cours…';
    showAlert("Envoi de votre rêve…", "info");

    try {
      const response = await fetch(uploadUrl, {
        method: "POST",
        body: formData,
        headers: { "X-CSRFToken": csrfToken, Accept: "application/json" },
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.redirect_url) {
        window.location.assign(data.redirect_url);
        return;
      }
      showAlert((data.errors || ["Une erreur est survenue. Réessayez dans un instant."]).join(" "));
    } catch {
      showAlert("Connexion impossible. Vérifiez votre connexion internet puis réessayez.");
    }
    btnSend.disabled = false;
    btnRestart.disabled = false;
    btnSend.innerHTML = '<i class="bi bi-send"></i> Envoyer mon rêve';
  }

  // Durée des fichiers importés, lue depuis leurs métadonnées.
  const fileInput = document.querySelector("#upload-form input[type=file]");
  const durationInput = el("upload-duration");
  fileInput?.addEventListener("change", () => {
    durationInput.value = "";
    const file = fileInput.files[0];
    if (!file) return;
    const probe = new Audio();
    probe.preload = "metadata";
    probe.addEventListener("loadedmetadata", () => {
      if (Number.isFinite(probe.duration)) durationInput.value = probe.duration.toFixed(1);
      URL.revokeObjectURL(probe.src);
    });
    probe.src = URL.createObjectURL(file);
  });
  el("upload-form")?.addEventListener("submit", () => {
    const button = el("btn-upload");
    button.disabled = true;
    button.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Envoi en cours…';
  });

  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    show(el("recorder-unsupported"), true);
    show(el("recorder-controls"), false);
    return;
  }

  btnStart.addEventListener("click", startRecording);
  btnStop.addEventListener("click", stopRecording);
  btnRestart.addEventListener("click", restart);
  btnSend.addEventListener("click", send);
})();
