const view = document.querySelector("#view");
const state = {
  route: { name: "list" },
  projects: [],
  project: null,
  settings: null,
  error: "",
  notice: "",
  loading: false,
  busy: false,
};

let pollTimer = null;

const LLM_NAME = { local: "локальный разбор текста", anthropic: "Claude", openai: "GPT-4o" };
const TTS_NAME = { edge: "edge-tts", piper: "Piper", elevenlabs: "ElevenLabs" };
const VIDEO_NAME = { kenburns: "Ken Burns", runway: "Runway", kling: "Kling", luma: "Luma" };
const PRESET_TITLE = {
  youtube: "YouTube 16:9",
  shorts: "Shorts и Reels 9:16",
  feed: "Лента 1:1",
};

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (key === "html") node.innerHTML = value;
    else node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) {
    if (child == null) continue;
    node.append(child);
  }
  return node;
}

function parseRoute() {
  const hash = (location.hash || "#/").replace(/^#/, "");
  const parts = hash.split("/").filter(Boolean);
  if (parts[0] === "new") return { name: "new" };
  if (parts[0] === "settings") return { name: "settings" };
  if (parts[0] === "project" && parts[1]) return { name: "project", id: parts[1] };
  return { name: "list" };
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = "Запрос не выполнен";
    try {
      const data = await response.json();
      if (typeof data.detail === "string") detail = data.detail;
      else if (Array.isArray(data.detail)) detail = data.detail.map((item) => item.msg || "").filter(Boolean).join("; ") || detail;
    } catch (_err) {
      /* ответ без JSON */
    }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

function stopPoll() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

function formatDate(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function banner(text, kind) {
  return el("div", { class: kind ? `banner ${kind}` : "banner", text });
}

function setNav() {
  document.querySelectorAll("[data-nav]").forEach((link) => {
    const name = link.getAttribute("data-nav");
    const active = name === "settings" ? state.route.name === "settings" : state.route.name !== "settings";
    link.classList.toggle("active", active);
  });
}

async function refresh() {
  state.route = parseRoute();
  stopPoll();
  state.error = "";
  state.notice = "";
  setNav();
  if (state.route.name === "list") return loadList();
  if (state.route.name === "new") return render();
  if (state.route.name === "settings") return loadSettings();
  if (state.route.name === "project") return loadProject(state.route.id);
  return render();
}

async function loadList() {
  state.loading = true;
  render();
  try {
    state.projects = await api("/api/projects");
  } catch (err) {
    state.error = err.message;
  } finally {
    state.loading = false;
    render();
  }
}

async function loadProject(id) {
  state.loading = true;
  state.project = null;
  render();
  try {
    state.project = await api(`/api/projects/${id}`);
  } catch (err) {
    state.error = err.message;
  } finally {
    state.loading = false;
    render();
    if (state.project && state.project.status === "rendering") ensurePoll(id);
  }
}

async function loadSettings() {
  state.loading = true;
  render();
  try {
    state.settings = await api("/api/settings");
  } catch (err) {
    state.error = err.message;
  } finally {
    state.loading = false;
    render();
  }
}

function ensurePoll(id) {
  stopPoll();
  pollTimer = setInterval(async () => {
    if (state.route.name !== "project" || state.route.id !== id) {
      stopPoll();
      return;
    }
    try {
      const project = await api(`/api/projects/${id}`);
      const previous = state.project && state.project.status;
      state.project = project;
      if (project.status === "rendering") {
        const bar = document.getElementById("progress-bar");
        const label = document.getElementById("progress-label");
        if (bar) bar.style.width = `${project.progress || 0}%`;
        if (label) label.textContent = project.progress_label || "Собираем выпуск";
        if (previous !== "rendering") render();
      } else {
        stopPoll();
        render();
      }
    } catch (err) {
      state.error = err.message;
      stopPoll();
      render();
    }
  }, 1000);
}

function render() {
  setNav();
  view.replaceChildren();
  if (state.loading) {
    view.append(el("p", { class: "hint", text: "Загружаем…" }));
    return;
  }
  if (state.route.name === "list") view.append(listView());
  else if (state.route.name === "new") view.append(newView());
  else if (state.route.name === "settings") view.append(settingsView());
  else if (state.route.name === "project") view.append(projectView());
}

function listView() {
  const wrap = el("section", { class: "stack" });
  wrap.append(el("div", { class: "row" }, [
    el("div", {}, [
      el("h1", { text: "Выпуски" }),
      el("p", { class: "lede", text: "Текст и несколько кадров. Дальше — сценарий, озвучка и три ролика." }),
    ]),
    el("a", { class: "button", href: "#/new", text: "Новый выпуск" }),
  ]));
  if (state.error) wrap.append(banner(state.error));
  if (!state.projects.length) {
    wrap.append(el("div", { class: "empty" }, [
      el("div", { class: "sprocket" }),
      el("h2", { text: "Пока пусто" }),
      el("p", { class: "lede", text: "Здесь появятся выпуски. Загрузите текст и три–пять кадров — сервис разложит их на сцены и соберёт YouTube, Shorts и квадрат для ленты." }),
      el("a", { class: "button", href: "#/new", text: "Собрать первый выпуск" }),
    ]));
    return wrap;
  }
  const list = el("div", { class: "list" });
  for (const project of state.projects) {
    list.append(el("a", { class: "card project-link", href: `#/project/${project.id}` }, [
      el("div", {}, [
        el("strong", { text: project.title }),
        el("div", {}, [el("small", { text: `${formatDate(project.created_at)} · кадров: ${project.image_count}` })]),
      ]),
      el("span", { class: `chip chip-${project.status}`, text: project.status_label }),
    ]));
  }
  wrap.append(list);
  return wrap;
}

function newView() {
  const form = el("form", { class: "form" });
  const title = el("input", { type: "text", name: "title", maxlength: "120", required: "required", placeholder: "Утро на набережной" });
  const script = el("textarea", {
    name: "script_text",
    required: "required",
    placeholder: "Утром город ещё не шумит. На набережной пахнет рекой и свежим хлебом.\n\nЯ беру камеру и иду туда, где свет ложится на воду.\n\nК полудню кадры уже есть — осталось собрать из них одну историю.",
  });
  script.style.minHeight = "180px";
  const imageInput = el("input", { class: "file-hidden", type: "file", accept: "image/jpeg,image/png,image/webp", multiple: "multiple" });
  const thumbs = el("div", { class: "thumbs" });
  const imageHint = el("p", { class: "hint", text: "Нужно 3–5 файлов: jpg, png или webp." });
  imageInput.addEventListener("change", () => {
    thumbs.replaceChildren();
    const files = [...imageInput.files];
    imageHint.textContent = files.length
      ? `Выбрано ${files.length}. Нужно от 3 до 5.`
      : "Нужно 3–5 файлов: jpg, png или webp.";
    for (const file of files.slice(0, 5)) {
      const img = el("img", { alt: file.name });
      img.src = URL.createObjectURL(file);
      thumbs.append(img);
    }
  });
  const music = el("input", { class: "file-hidden", type: "file", accept: "audio/mpeg,audio/wav,audio/mp4,audio/aac,audio/ogg,audio/flac,.mp3,.wav,.m4a,.aac,.ogg,.flac" });
  const musicName = el("p", { class: "hint", text: "Необязательно. Если файла нет, ролик будет только с голосом." });
  music.addEventListener("change", () => {
    musicName.textContent = music.files[0] ? music.files[0].name : "Необязательно. Если файла нет, ролик будет только с голосом.";
  });
  const errorBox = el("div");
  const submit = el("button", { type: "submit", text: "Собрать сценарий" });
  form.append(
    el("div", {}, [el("h1", { text: "Новый выпуск" }), el("p", { class: "lede", text: "Загрузите исходники. Режиссёрский сценарий можно поправить до сборки." })]),
    el("label", {}, ["Название", title]),
    el("label", {}, ["Текст сценария", script]),
    el("div", { class: "drop" }, [
      el("strong", { text: "Кадры" }),
      el("label", { class: "button ghost", text: "Выбрать изображения" }, [imageInput]),
      imageHint,
      thumbs,
    ]),
    el("div", { class: "drop" }, [
      el("strong", { text: "Фоновая музыка" }),
      el("label", { class: "button ghost", text: "Выбрать файл" }, [music]),
      musicName,
    ]),
    errorBox,
    el("div", { class: "actions" }, [submit, el("a", { class: "button ghost", href: "#/", text: "Отмена" })]),
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.replaceChildren();
    const files = [...imageInput.files];
    if (files.length < 3 || files.length > 5) {
      errorBox.append(banner("Нужно от 3 до 5 изображений"));
      return;
    }
    const body = new FormData();
    body.append("title", title.value.trim());
    body.append("script_text", script.value.trim());
    for (const file of files) body.append("images", file);
    if (music.files[0]) body.append("music", music.files[0]);
    submit.disabled = true;
    submit.textContent = "Собираем сценарий…";
    try {
      const created = await api("/api/projects", { method: "POST", body });
      try {
        await api(`/api/projects/${created.id}/script`, { method: "POST" });
      } catch (err) {
        location.hash = `#/project/${created.id}`;
        return;
      }
      location.hash = `#/project/${created.id}`;
    } catch (err) {
      errorBox.append(banner(err.message));
      submit.disabled = false;
      submit.textContent = "Собрать сценарий";
    }
  });
  return form;
}

function projectView() {
  const wrap = el("section", { class: "stack" });
  if (state.error && !state.project) {
    wrap.append(el("h1", { text: "Выпуск" }), banner(state.error));
    return wrap;
  }
  const project = state.project;
  if (!project) return wrap;
  wrap.append(el("div", { class: "row" }, [
    el("div", {}, [
      el("h1", { text: project.title }),
      el("p", { class: "hint", text: formatDate(project.created_at) }),
    ]),
    el("span", { class: `chip chip-${project.status}`, text: project.status_label }),
  ]));
  if (project.images && project.images.length) {
    const refs = el("div", { class: "refs" });
    for (const image of project.images) refs.append(el("img", { src: image.url, alt: image.filename }));
    wrap.append(refs);
  }
  if (state.error) wrap.append(banner(state.error));
  if (project.error && project.status === "failed") wrap.append(banner(project.error));
  if (project.note) wrap.append(banner(project.note, "ok"));
  if (project.status === "rendering") {
    wrap.append(progressBlock(project));
  }
  if (project.status === "done" && project.outputs && project.outputs.length) {
    wrap.append(outputsBlock(project));
  }
  if (project.status === "draft") {
    wrap.append(banner("Сценарий ещё не собран.", "warn"));
    const button = el("button", { type: "button", text: "Собрать сценарий" });
    button.addEventListener("click", () => rebuild(project.id, button));
    wrap.append(el("div", { class: "actions" }, [button]));
  }
  if (project.scenes && project.scenes.length && project.status !== "rendering") {
    wrap.append(sceneEditor(project));
  }
  return wrap;
}

function progressBlock(project) {
  const bar = el("span", { id: "progress-bar" });
  bar.style.width = `${project.progress || 0}%`;
  return el("div", { class: "panel" }, [
    el("h2", { text: "Собираем выпуск" }),
    el("p", { id: "progress-label", class: "hint", text: project.progress_label || "Запускаем сборку" }),
    el("div", { class: "progress" }, [bar]),
    el("p", { class: "hint", text: "Можно оставить страницу открытой: по готовности здесь появятся три ролика." }),
  ]);
}

function outputsBlock(project) {
  const grid = el("div", { class: "outputs" });
  const order = ["youtube", "shorts", "feed"];
  const outputs = [...project.outputs].sort((a, b) => order.indexOf(a.preset) - order.indexOf(b.preset));
  for (const output of outputs) {
    const video = el("video", { controls: "controls", preload: "metadata", src: output.url });
    grid.append(el("article", { class: "output" }, [
      el("h3", { text: PRESET_TITLE[output.preset] || output.preset }),
      el("p", { class: "hint", text: `${output.width}×${output.height}` }),
      video,
      el("a", { class: "button", href: `${output.url}?download=1`, text: "Скачать" }),
    ]));
  }
  return el("div", { class: "stack" }, [el("h2", { text: "Три файла" }), grid]);
}

function sceneEditor(project) {
  const form = el("form", { class: "stack" });
  const engine = LLM_NAME[project.script_engine] || project.script_engine || "";
  form.append(el("div", {}, [
    el("h2", { text: "Режиссёрский сценарий" }),
    el("p", { class: "hint", text: engine ? `Источник: ${engine}. Длительность, кадр и озвучку можно поправить.` : "Длительность, кадр и озвучку можно поправить." }),
  ]));
  project.scenes.forEach((scene, index) => {
    const duration = el("input", {
      type: "number",
      min: "1",
      max: "120",
      step: "0.5",
      value: String(scene.duration),
      class: "duration",
      "data-field": "duration",
    });
    const visual = el("textarea", { "data-field": "visual_prompt", text: scene.visual_prompt });
    const voice = el("textarea", { "data-field": "voiceover", text: scene.voiceover });
    form.append(el("article", { class: "scene", "data-scene": String(index) }, [
      el("div", { class: "scene-head" }, [
        el("span", { class: "num", text: String(scene.scene).padStart(2, "0") }),
        el("label", {}, ["Длительность, сек", duration]),
      ]),
      el("label", {}, ["Что в кадре", visual]),
      el("label", {}, ["Озвучка", voice]),
    ]));
  });
  const errorBox = el("div");
  const save = el("button", { type: "submit", text: "Утвердить и собрать" });
  const again = el("button", { class: "ghost", type: "button", text: "Собрать заново" });
  again.addEventListener("click", () => rebuild(project.id, again));
  form.append(
    el("p", { class: "hint", text: "Кадр не короче озвучки: если реплика длиннее указанной длительности, ролик продлевается по голосу." }),
    errorBox,
    el("div", { class: "actions" }, [save, again]),
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.replaceChildren();
    const scenes = [...form.querySelectorAll("[data-scene]")].map((card, index) => ({
      scene: index + 1,
      duration: Number(card.querySelector("[data-field=duration]").value),
      visual_prompt: card.querySelector("[data-field=visual_prompt]").value.trim(),
      voiceover: card.querySelector("[data-field=voiceover]").value.trim(),
    }));
    if (scenes.some((scene) => !scene.visual_prompt || !scene.voiceover || !(scene.duration >= 1))) {
      errorBox.append(banner("Заполните длительность, кадр и озвучку в каждой сцене"));
      return;
    }
    save.disabled = true;
    save.textContent = "Запускаем сборку…";
    try {
      await api(`/api/projects/${project.id}/scenes`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(scenes),
      });
      state.project = await api(`/api/projects/${project.id}/approve`, { method: "POST" });
      state.loading = false;
      render();
      ensurePoll(project.id);
    } catch (err) {
      errorBox.append(banner(err.message));
      save.disabled = false;
      save.textContent = "Утвердить и собрать";
    }
  });
  return form;
}

async function rebuild(id, button) {
  button.disabled = true;
  const previous = button.textContent;
  button.textContent = "Собираем сценарий…";
  try {
    state.project = await api(`/api/projects/${id}/script`, { method: "POST" });
    state.error = "";
    render();
  } catch (err) {
    state.error = err.message;
    button.disabled = false;
    button.textContent = previous;
    render();
  }
}

function settingsView() {
  const wrap = el("section", { class: "stack" });
  wrap.append(el("h1", { text: "Настройки" }), el("p", { class: "lede", text: "Ключи лежат в локальной базе или в .env и не пишутся в журнал. Пустое поле не затирает сохранённый ключ — отметьте «Удалить», если его нужно убрать." }));
  if (state.error) wrap.append(banner(state.error));
  if (state.notice) wrap.append(banner(state.notice, "ok"));
  const settings = state.settings;
  if (!settings) return wrap;
  const system = settings.system || {};
  const gpu = system.gpu || {};
  const gpuText = gpu.available
    ? `GPU: ${gpu.name}, ${gpu.memory_gb} ГБ${gpu.memory_gb >= 12 ? " — порог локальной озвучки пройден" : " — меньше 12 ГБ, авто выберет API, если есть ключ"}`
    : "GPU не найден (nvidia-smi или torch). Автовыбор озвучки пойдёт в API, если задан ключ ElevenLabs, иначе Piper или edge-tts.";
  const effective = system.effective || {};
  const effText = `Сейчас будет использовано: ${nameOf(LLM_NAME, effective.llm)}, ${nameOf(TTS_NAME, effective.tts)}, видео — ${nameOf(VIDEO_NAME, effective.video)}.`;
  if (!system.ffmpeg) wrap.append(banner("FFmpeg не найден в PATH. Сборка ролика не запустится, пока он не установлен."));
  wrap.append(el("div", { class: "panel" }, [
    el("p", { text: gpuText }),
    el("p", { class: "hint", text: `Piper: ${system.piper ? "найден" : "не найден"}. edge-tts: ${system.edge_tts ? "доступен" : "не установлен"}.` }),
    el("p", { text: effText }),
  ]));

  const form = el("form", { class: "stack" });
  const llmMode = select("llm_mode", [["local", "Локально"], ["api", "API"]], settings.llm_mode);
  const llmProvider = select("llm_provider", [["anthropic", "Claude"], ["openai", "GPT-4o"]], settings.llm_provider);
  const ttsMode = select("tts_mode", [["auto", "Авто"], ["local", "Локально"], ["api", "ElevenLabs"]], settings.tts_mode);
  const videoMode = select("video_mode", [["local", "Картинки и Ken Burns"], ["api", "Генерация B-roll"]], settings.video_mode);
  const videoProvider = select("video_provider", [["runway", "Runway"], ["kling", "Kling"], ["luma", "Luma"]], settings.video_provider);
  form.append(
    el("div", { class: "panel" }, [
      el("h2", { text: "Языковая модель" }),
      el("p", { class: "hint", text: "С ключом и режимом API сценарий всегда запрашивается у модели. Без ключа текст режется на сцены локально." }),
      el("div", { class: "grid-2" }, [
        el("label", {}, ["Режим", llmMode]),
        el("label", {}, ["Провайдер", llmProvider]),
      ]),
      secretField("anthropic_api_key", "Ключ Anthropic", settings.anthropic_api_key_set),
      secretField("openai_api_key", "Ключ OpenAI", settings.openai_api_key_set),
    ]),
    el("div", { class: "panel" }, [
      el("h2", { text: "Озвучка" }),
      el("p", { class: "hint", text: "Авто: при GPU от 12 ГБ — Piper, если он установлен, иначе edge-tts. Без такого GPU — ElevenLabs, если есть ключ, иначе снова Piper или edge-tts." }),
      el("label", {}, ["Режим", ttsMode]),
      secretField("elevenlabs_api_key", "Ключ ElevenLabs", settings.elevenlabs_api_key_set),
      el("label", {}, ["Voice ID, в том числе клонированный голос", el("input", { name: "elevenlabs_voice_id", type: "text", value: settings.elevenlabs_voice_id || "", autocomplete: "off" })]),
    ]),
    el("div", { class: "panel" }, [
      el("h2", { text: "Видео" }),
      el("p", { class: "hint", text: "По умолчанию загруженные картинки идут через Ken Burns. B-roll вызывается, только если выбран API и есть ключ. Без ключа выпуск не останавливается." }),
      el("div", { class: "grid-2" }, [
        el("label", {}, ["Режим", videoMode]),
        el("label", {}, ["Провайдер", videoProvider]),
      ]),
      secretField("runway_api_key", "Ключ Runway", settings.runway_api_key_set),
      secretField("kling_api_key", "Ключ Kling", settings.kling_api_key_set),
      secretField("luma_api_key", "Ключ Luma", settings.luma_api_key_set),
    ]),
    el("div", { class: "actions" }, [el("button", { type: "submit", text: "Сохранить" })]),
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      llm_mode: form.llm_mode.value,
      llm_provider: form.llm_provider.value,
      tts_mode: form.tts_mode.value,
      video_mode: form.video_mode.value,
      video_provider: form.video_provider.value,
      elevenlabs_voice_id: form.elevenlabs_voice_id.value.trim(),
    };
    for (const name of ["anthropic_api_key", "openai_api_key", "elevenlabs_api_key", "runway_api_key", "kling_api_key", "luma_api_key"]) {
      const clear = form.elements[`${name}_clear`];
      const value = form.elements[name].value.trim();
      if (clear && clear.checked) payload[name] = "";
      else if (value) payload[name] = value;
    }
    try {
      state.settings = await api("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      state.notice = "Настройки сохранены";
      state.error = "";
      render();
    } catch (err) {
      state.error = err.message;
      render();
    }
  });
  wrap.append(form);
  return wrap;
}

function nameOf(map, value) {
  if (!value) return "не выбрано";
  if (String(value).startsWith("error:")) return String(value).replace(/^error:\s*/, "");
  return map[value] || value;
}

function select(name, options, current) {
  const node = el("select", { name });
  for (const [value, label] of options) {
    const option = el("option", { value, text: label });
    if (value === current) option.selected = true;
    node.append(option);
  }
  return node;
}

function secretField(name, label, isSet) {
  const block = el("div", { class: "stack" });
  block.append(el("label", {}, [
    label,
    el("input", {
      name,
      type: "password",
      autocomplete: "off",
      placeholder: isSet ? "Ключ сохранён — введите новый, чтобы заменить" : "Не задан",
    }),
  ]));
  if (isSet) {
    block.append(el("label", { class: "check" }, [
      el("input", { type: "checkbox", name: `${name}_clear` }),
      "Удалить сохранённый ключ",
    ]));
  }
  return block;
}

window.addEventListener("hashchange", refresh);
refresh();
