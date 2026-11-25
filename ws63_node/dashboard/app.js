"use strict";

const element = id => document.getElementById(id);
const canvas = element("map");
const context = canvas.getContext("2d");
const view = {scale: 1, x: 0, y: 0, fitted: false};
const requestedView = new URLSearchParams(window.location.search);
let mode = requestedView.get("source") === "live" ? "live" : "recorded";
let traceSelection = null;
let traceOptions = "";
let routeFrame = null;
let routePlayback = null;
let packetSignature = "";
const logEvents = new Map();
let state = null;
let mapImage = null;
let imageId = null;
let drag = null;
let requestId = 0;

const size = () => ({width: canvas.clientWidth, height: canvas.clientHeight});

function fit() {
  if (!mapImage || !state || !state.map) return;
  const box = size();
  const map = state.map;
  const meters = map.resolution;
  const margin = Math.min(box.width, box.height) * 0.10;
  view.scale = Math.min((box.width - margin) / (map.width * meters), (box.height - margin) / (map.height * meters));
  view.x = box.width / 2 - map.width * meters * view.scale / 2;
  view.y = box.height / 2 + map.height * meters * view.scale / 2;
  view.fitted = true;
  draw();
}

function point(x, y) {
  const m = state.map;
  const dx = x - m.x, dy = y - m.y;
  const c = Math.cos(m.yaw), s = Math.sin(m.yaw);
  return [view.x + (dx * c + dy * s) * view.scale, view.y - (dy * c - dx * s) * view.scale];
}

function draw() {
  const box = size();
  const pixelRatio = Math.min(2, window.devicePixelRatio || 1);
  if (canvas.width !== Math.round(box.width * pixelRatio) || canvas.height !== Math.round(box.height * pixelRatio)) {
    canvas.width = Math.round(box.width * pixelRatio);
    canvas.height = Math.round(box.height * pixelRatio);
  }
  context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  context.clearRect(0, 0, box.width, box.height);
  element("scale").hidden = !(mapImage && state && state.map);
  if (element("scale").hidden) return;
  const m = state.map;
  const unit = m.resolution * view.scale;
  context.imageSmoothingEnabled = false;
  context.drawImage(mapImage, view.x, view.y - m.height * unit, m.width * unit, m.height * unit);

  if (element("show-path").checked && state.trail.length > 1) {
    context.beginPath();
    state.trail.forEach((p, i) => {
      const [x, y] = point(p[0], p[1]);
      if (i === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    context.lineWidth = 2;
    context.strokeStyle = "#f2be78";
    context.stroke();
  }
  if (element("show-scan").checked) {
    context.fillStyle = "#65cadb";
    for (const p of state.points) {
      const [x, y] = point(p[0], p[1]);
      context.fillRect(x - 2, y - 2, 4, 4);
    }
  }
  if (element("show-walls").checked && state.walls && state.walls.length) {
    context.beginPath();
    for (const [start, end] of state.walls) {
      const [x0, y0] = point(start[0], start[1]);
      const [x1, y1] = point(end[0], end[1]);
      context.moveTo(x0, y0);
      context.lineTo(x1, y1);
    }
    context.lineWidth = 2;
    context.strokeStyle = "#e3bdff";
    context.stroke();
  }
  if (state.pose) {
    const [x, y] = point(state.pose[0], state.pose[1]);
    context.save();
    context.translate(x, y);
    context.rotate(m.yaw - state.pose[2]);
    context.beginPath();
    context.moveTo(11, 0);
    context.lineTo(-6, -6);
    context.lineTo(-3, 0);
    context.lineTo(-6, 6);
    context.closePath();
    context.fillStyle = "#8de5bd";
    context.fill();
    context.lineWidth = 1.5;
    context.strokeStyle = "#0e171d";
    context.stroke();
    context.restore();
  }
  const fontSize = parseFloat(getComputedStyle(document.documentElement).fontSize);
  const meters = Math.pow(10, Math.floor(Math.log(fontSize * 6 / view.scale) / Math.LN10));
  const bar = meters * view.scale < fontSize * 2.5 ? meters * 5 : meters;
  element("scale").firstElementChild.style.width = (bar * view.scale) + "px";
  element("scale").lastElementChild.textContent = Number(bar.toPrecision(3)) + " m";
}

function zoom(factor, x, y) {
  if (!mapImage) return;
  const ratio = Math.min(800, Math.max(4, view.scale * factor)) / view.scale;
  view.x = x - (x - view.x) * ratio;
  view.y = y - (y - view.y) * ratio;
  view.scale *= ratio;
  view.fitted = false;
  draw();
}

function centeredZoom(factor) {
  const box = size();
  zoom(factor, box.width / 2, box.height / 2);
}

function traceRow(list, elapsed, title, description) {
  const row = document.createElement("li");
  const time = document.createElement("time");
  const text = document.createElement("div");
  const heading = document.createElement("strong");
  const details = document.createElement("small");
  time.textContent = `+${elapsed} ms`;
  heading.textContent = title;
  details.textContent = description;
  text.append(heading, details);
  row.append(time, text);
  list.append(row);
}

function timeLabel(time) {
  return new Date(time).toLocaleTimeString("zh-CN", {hour12: false}) + "." + String(time % 1000).padStart(3, "0");
}

function frameEvents(frame) {
  const events = [[frame.capture_ms, "scan", "采集", `${frame.raw_points} 点 → ${frame.bins} 桶，${frame.segments} 段`]];
  for (const part of frame.tx) {
    events.push([part.at_ms, `tx${part.part}`, "USB TX", `第 ${part.part}/${frame.segments} 段 · ${part.bytes} B → 感知端 WS63`]);
  }
  for (const part of frame.rx) {
    events.push([part.at_ms, `rx${part.part}`, "SLE RX", `第 ${part.part}/${frame.segments} 段 · ${part.bytes} B · 序号 ${part.seq} · CRC ${part.crc16} OK · 节点时间 ${part.sender_uptime_ms} ms`]);
  }
  if (frame.published_ms) {
    events.push([frame.published_ms, "ros", "ROS", `发布 /scan_sle · ${frame.valid_bins} 个有效测距 · 采集后 ${frame.published_ms - frame.capture_ms} ms`]);
  }
  return events.sort((a, b) => a[0] - b[0]);
}

function measuredRoute(frame, elapsed = Infinity) {
  if (!frame) return {captured: false, sent: [], received: [], published: false, expired: false};
  const observed = event => event.at_ms - frame.capture_ms <= elapsed;
  return {captured: elapsed >= 0, sent: frame.tx.filter(observed), received: frame.rx.filter(observed),
    published: Boolean(frame.published_ms && frame.published_ms - frame.capture_ms <= elapsed),
    expired: elapsed === Infinity && frame.status === "expired"};
}

function renderRoute(frame, elapsed = Infinity) {
  const seen = measuredRoute(frame, elapsed);
  const received = seen.received.length;
  const sent = seen.sent.length;
  const total = frame ? frame.segments : 0;
  const waiting = seen.expired ? "expired" : "pending";
  const steps = {
    capture: [seen.captured ? `${frame.raw_points} 点` : "待采集", seen.captured ? "received" : "idle"],
    sender: [total ? `提交 ${sent}/${total}` : "待提交", sent ? "received" : "idle"],
    radio: [total ? `回传 ${received}/${total}` : "待回传", received === total && total ? "received" : sent ? waiting : "idle"],
    receiver: [received ? `已转交 ${received} 段` : "待转交", received ? "received" : "idle"],
    ros: [seen.published ? "已发布" : seen.expired ? "整帧超时" : received ? `CRC ${received}/${total}` : "待重组",
      seen.published ? "received" : seen.expired ? "expired" : received ? "pending" : "idle"]
  };
  for (const [name, [label, tone]] of Object.entries(steps)) {
    const node = element("route-" + name);
    node.lastElementChild.textContent = label;
    node.dataset.tone = tone;
  }
  const packets = [];
  for (let part = 1; part <= total; part++) {
    const rx = seen.received.some(item => item.part === part);
    const tx = seen.sent.some(item => item.part === part);
    packets.push(rx ? [`第 ${part} 段 · CRC 通过`, "received"] :
      tx ? [`第 ${part} 段 · ${seen.expired ? "回传超时" : "已提交"}`, waiting] : [`第 ${part} 段 · 待提交`, "idle"]);
  }
  const signature = JSON.stringify(packets);
  if (signature === packetSignature) return;
  packetSignature = signature;
  const list = element("route-packets");
  list.textContent = "";
  for (const [label, tone] of packets) {
    const item = document.createElement("li");
    item.textContent = label;
    item.dataset.tone = tone;
    list.append(item);
  }
}

function stopRoutePlayback() {
  if (!routePlayback) return;
  routePlayback.timers.forEach(clearTimeout);
  routePlayback = null;
  element("play-route").textContent = "播放此帧";
}

function playRoute(frame) {
  stopRoutePlayback();
  const button = element("play-route");
  const run = {capture: frame.capture_ms, timers: []};
  routePlayback = run;
  button.textContent = "按实测时间播放…";
  button.disabled = true;
  renderRoute(frame, 0);
  const elapsed = [...new Set(frameEvents(frame).map(([stamp]) => stamp - frame.capture_ms))].filter(ms => ms > 0);
  for (const ms of elapsed) run.timers.push(setTimeout(() => renderRoute(frame, ms), ms));
  run.timers.push(setTimeout(() => {
    stopRoutePlayback();
    renderRoute(frame);
    button.disabled = false;
  }, Math.max(0, ...elapsed) + 240));
}

function renderLogs(link) {
  const output = element("log-console");
  if (!link && !logEvents.size) {
    output.textContent = mode === "live" ? "等待实时采集开始。" : "此实测记录没有传输日志。";
  }
  element("log-source").textContent = mode === "live" ? (link ? "实时 · 传输时间与校验" : "实时 · 等待采集") : "实测回放 · 传输时间与校验";
  if (!link) return;
  let changed = false;
  for (const frame of [...link.recent, ...link.pending]) {
    const label = timeLabel(frame.capture_ms);
    const events = frameEvents(frame);
    if (frame.status === "expired") {
      events.push([link.updated_ms, "expired", "超时", `整帧未完成 ${frame.rx.length}/${frame.segments} 段`]);
    }
    for (const [stamp, id, stage, detail] of events) {
      const key = `${frame.capture_ms}/${id}`;
      if (logEvents.has(key)) continue;
      const time = id === "expired" ? label : timeLabel(stamp);
      logEvents.set(key, {stamp, text: `${time} | 帧 ${label} | [${stage}] ${detail}`});
      changed = true;
    }
  }
  if (!changed && logEvents.size) return;
  const events = [...logEvents.entries()].sort((a, b) => a[1].stamp - b[1].stamp);
  for (const [key] of events.slice(0, Math.max(0, events.length - 160))) logEvents.delete(key);
  const position = output.scrollTop;
  output.textContent = events.slice(-160).map(([, event]) => event.text).join("\n") || "等待第一帧进入 WS63。";
  output.scrollTop = element("follow-log").checked ? output.scrollHeight : position;
}

function renderLink(next, error) {
  const link = next && next.link;
  const counts = link && link.counts;
  const set = (id, text) => { element(id).textContent = text; };
  const status = element("link-status");
  status.dataset.tone = link ? mode : "idle";
  status.lastElementChild.textContent = link ? (mode === "live" ? "实时观测" : "实测回放") :
    (error ? "服务不可用" : "等待链路");
  const frames = link ? [...link.recent, ...link.pending].sort((a, b) => b.capture_ms - a.capture_ms).slice(0, 7) : [];
  const durations = frames.filter(frame => frame.published_ms).map(frame => frame.published_ms - frame.capture_ms).sort((a, b) => a - b);
  const median = durations.length ? (durations[Math.floor(durations.length / 2)] + durations[Math.floor((durations.length - 1) / 2)]) / 2 : null;
  const finalized = counts ? counts.completed + counts.expired : 0;
  set("link-frames", counts ? `${counts.submitted} → ${counts.completed}` : "—");
  set("link-parts", counts ? `${counts.rx_parts} / ${counts.tx_parts}` : "—");
  set("link-ratio", finalized ? `${(100 * counts.completed / finalized).toFixed(1)}%` : "—");
  set("link-latency", median === null ? "—" : `${median} ms`);
  set("link-bytes", counts ? `${counts.rx_bytes.toLocaleString()} B` : "—");
  set("link-note", link ? (mode === "live" ? "实时采集 · SLE SSAP Notification" :
    "实测回放 · " + new Date(link.updated_ms).toLocaleString("zh-CN", {hour12: false})) : "采集、无线回传与 ROS 发布");
  const progress = counts && Number.isInteger(counts.startup_expired) ?
    `启动阶段超时 ${counts.startup_expired} 帧，首帧回传后超时 ${counts.expired - counts.startup_expired} 帧。` :
    (counts ? `超时 ${counts.expired} 帧。` : "启动 Jetson 采集后可查看真实链路。");
  const pendingLabel = mode === "live" ? "帧处理中" : "帧在记录结束时待确认";
  set("link-progress", link ? `${link.pending.length} ${pendingLabel}。${progress}` : progress);
  element("export-link").disabled = !link || !frames.length;

  const active = frames.find(frame => frame.capture_ms === traceSelection) ||
    (mode === "recorded" && frames.find(frame => frame.status === "published")) || frames[0];
  routeFrame = active;
  if (routePlayback && (!active || mode !== "recorded" || routePlayback.capture !== active.capture_ms)) stopRoutePlayback();
  if (!routePlayback) renderRoute(active);
  element("play-route").disabled = !active || mode !== "recorded" || Boolean(routePlayback);
  const history = element("trace-history");
  const rows = element("trace-events");
  rows.textContent = "";
  const preview = element("trace-preview");
  preview.hidden = !(active && active.sample_mm);
  const empty = element("trace-empty");
  empty.hidden = Boolean(active);
  empty.textContent = link ? "等待第一帧进入 WS63。" : "此记录没有链路追踪数据。";
  const stage = {pending: mode === "live" ? "回传中" : "记录时待确认", published: "已发布", expired: "超时"};
  const options = frames.map(frame => `${frame.capture_ms}/${frame.status}/${frame.rx.length}`).join(";");
  if (traceOptions !== options) {
    traceOptions = options;
    history.textContent = "";
    for (const frame of frames) {
      const option = document.createElement("option");
      option.value = frame.capture_ms;
      option.textContent = `${timeLabel(frame.capture_ms)} · ${stage[frame.status]} ${frame.rx.length}/${frame.segments}`;
      history.append(option);
    }
  }
  history.disabled = !active;
  history.value = active ? String(active.capture_ms) : "";
  if (!active) return;
  for (const [stamp, , title, description] of frameEvents(active)) traceRow(rows, stamp - active.capture_ms, title, description);
  if (active.sample_mm) preview.textContent = `测距样本（mm） ${active.sample_mm.map(value => value == null ? "缺测" : value).join(" · ")}`;
}

function render(next, error) {
  const hadMap = Boolean(state && state.map);
  state = next;
  renderLink(next, error);
  renderLogs(next && next.link);
  const m = state && state.map;
  const isLive = mode === "live";
  const set = (id, value) => { element(id).textContent = value; };
  element("state").dataset.tone = m ? mode : "idle";
  element("state").lastElementChild.textContent = m ? (isLive ? "实时接收" : "历史实测") : (error ? "服务不可用" : "等待数据");
  element("empty").hidden = Boolean(m);
  set("empty", error ? "暂时无法连接本机数据服务" : isLive ? "建图启动后会显示实时地图" : "正在生成实测地图");
  set("raw-count", m ? state.raw_count.toLocaleString() + " 帧" : "—");
  const scanTopic = m && state.scan_topic || "/scan_sle";
  set("scan-input", scanTopic);
  set("sle-count", m ? state.sle_count.toLocaleString() + " 帧" : "—");
  set("scan-hz", m && state.scan_hz ? state.scan_hz.toFixed(2) + " Hz" : "—");
  set("resolution", m ? (m.resolution * 100).toFixed(0) + " cm / 格" : "—");
  set("known-area", m ? (m.known * m.resolution * m.resolution).toFixed(1) + " m²" : "—");
  set("pose", m && state.pose ? state.pose.slice(0, 2).map(v => v.toFixed(2)).join(" / ") + " m" : "—");
  set("map-frame", m ? m.frame.toUpperCase() : "MAP");
  if (!m) {
    mapImage = null;
    imageId = null;
    draw();
    return;
  }
  const id = m.id + ":" + m.x + ":" + m.y + ":" + m.yaw;
  if (id === imageId) {
    draw();
    return;
  }
  const previousImage = mapImage;
  imageId = id;
  const image = new Image();
  image.onload = () => {
    if (imageId !== id) return;
    mapImage = image;
    if (!previousImage || !hadMap || view.fitted) fit();
    else draw();
  };
  image.onerror = () => {
    if (imageId !== id) return;
    imageId = null;
    render(null, true);
  };
  image.src = "data:image/png;base64," + m.png;
}

async function refresh() {
  const request = ++requestId;
  try {
    const response = await fetch("/api/" + mode, {cache: "no-store"});
    if (!response.ok) throw new Error("request failed");
    const next = await response.json();
    if (request === requestId && !(state && next && state.written_at === next.written_at)) render(next, false);
  } catch (error) {
    if (request === requestId) render(null, true);
  }
}

for (const id of ["recorded", "live"]) {
  element(id).setAttribute("aria-pressed", mode === id);
  element(id).addEventListener("click", () => {
    if (mode === id) return;
    mode = id;
    traceSelection = null;
    logEvents.clear();
    element("recorded").setAttribute("aria-pressed", mode === "recorded");
    element("live").setAttribute("aria-pressed", mode === "live");
    render(null, false);
    refresh();
  });
}
element("trace-history").addEventListener("change", event => {
  traceSelection = Number(event.target.value);
  renderLink(state, false);
});
element("play-route").addEventListener("click", () => {
  if (routeFrame && mode === "recorded") playRoute(routeFrame);
});
element("follow-log").addEventListener("change", event => {
  const output = element("log-console");
  if (event.target.checked) output.scrollTop = output.scrollHeight;
});
element("export-link").addEventListener("click", () => {
  if (!state || !state.link) return;
  const file = URL.createObjectURL(new Blob([JSON.stringify({source: state.source, ...state.link}, null, 2)], {type: "application/json"}));
  const anchor = document.createElement("a");
  anchor.href = file;
  anchor.download = `ws63-link-${state.link.updated_ms}.json`;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(file), 1000);
});
element("zoom-in").addEventListener("click", () => centeredZoom(1.25));
element("zoom-out").addEventListener("click", () => centeredZoom(0.8));
element("fit").addEventListener("click", fit);
element("show-scan").addEventListener("change", draw);
element("show-walls").addEventListener("change", draw);
element("show-path").addEventListener("change", draw);
canvas.addEventListener("wheel", event => {
  if (!mapImage) return;
  event.preventDefault();
  zoom(event.deltaY < 0 ? 1.12 : 0.89, event.offsetX, event.offsetY);
}, {passive: false});
canvas.addEventListener("pointerdown", event => {
  if (!mapImage || event.button !== 0) return;
  drag = {x: event.clientX, y: event.clientY};
  canvas.setPointerCapture(event.pointerId);
  canvas.classList.add("dragging");
});
canvas.addEventListener("pointermove", event => {
  if (!drag) return;
  view.x += event.clientX - drag.x;
  view.y += event.clientY - drag.y;
  drag = {x: event.clientX, y: event.clientY};
  view.fitted = false;
  draw();
});
for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) {
  canvas.addEventListener(name, () => {
    drag = null;
    canvas.classList.remove("dragging");
  });
}
window.addEventListener("resize", () => {
  if (view.fitted) fit();
  else draw();
  const output = element("log-console");
  if (element("follow-log").checked) output.scrollTop = output.scrollHeight;
});
draw();
refresh();
setInterval(refresh, 400);
