"use strict";

const get = (name) => document.getElementById("watch-" + name);
const update = (name, value) => { get(name).textContent = value; };
const labels = {
  calibrating: "正在建立基线", clear: "通道正常", occupied: "占道", unknown: "可见性不足",
  heartbeat: "心跳", baseline: "基线就绪", intrusion: "占道", restored: "通道恢复",
  blind: "缺测确认"
};
const number = new Intl.NumberFormat("zh-CN");
const distance = (mm) => mm ? (mm / 1000).toFixed(2) + " m" : "缺测";
let selected = null;
let lastEventList = null;

function renderEvents(state) {
  const events = state ? state.events : [];
  const keyFor = (event) => event.session + "/" + event.event_id;
  const signature = events.map((event) => keyFor(event) + ":" + event.site_confirmed + ":" + event.site_pending).join(",");
  get("empty").hidden = events.length > 0;
  if (lastEventList !== signature) {
    lastEventList = signature;
    const list = get("events");
    list.replaceChildren();
    for (const event of events) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.key = keyFor(event);
      let acknowledgement = "";
      if (event.kind === "intrusion") {
        acknowledgement = event.site_confirmed ? "　已确认" : event.site_pending ? "　待确认" : "　未确认";
      }
      button.textContent = labels[event.kind] + "　#" + event.event_id + acknowledgement;
      button.onclick = () => { selected = keyFor(event); renderEvents(state); };
      item.append(button);
      list.append(item);
    }
  }
  if (!events.some((event) => keyFor(event) === selected)) selected = null;
  const event = events.find((entry) => keyFor(entry) === selected) || events[0];
  for (const button of get("events").querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(Boolean(event && button.dataset.key === keyFor(event))));
  }
  get("evidence").replaceChildren();
  get("table").hidden = !(event && event.evidence_mm.length);
  if (!event) {
    update("detail", "选择一条事件，查看基线和当前测距。");
    return;
  }
  const span = event.count ? " · 区段 " + event.count + " 格 · 上传 " + event.evidence_mm.length + " 格" : "";
  const latency = event.capture_age_ms === null ? "" : " · 触发帧到接收 " + event.capture_age_ms + " ms";
  update("detail", labels[event.kind] + " #" + event.event_id + span + latency);
  event.evidence_mm.forEach(([before, after], index) => {
    const angle = ((event.first + index + .5) / 72 - .5) * state.width_deg;
    const row = get("evidence").insertRow();
    row.insertCell().textContent = angle.toFixed(1) + "°";
    row.insertCell().textContent = distance(before);
    row.insertCell().textContent = distance(after);
  });
}

function render(data, failed = false) {
  const latest = data && data.latest;
  const recent = Boolean(latest && Date.now() / 1000 - data.latest_at < 3.5);
  const live = Boolean(data && data.running && recent && !failed);
  const state = live ? latest.state : "";
  const status = failed ? "界面连接中断" :
    !data || !data.running ? "监测未启动" : recent ? labels[state] : "等待新报告";
  update("state", status);
  get("state").dataset.state = state;
  update("link", live ? "SLE 在线" : "无实时报告");
  const stationOnline = data && data.site_station_online;
  const awaitingConfirmation = live && data.events.some((event) => event.site_pending);
  update("station", !stationOnline ? "现场确认终端离线" :
    awaitingConfirmation ? "现场确认终端在线 · 按下 BOOT 确认占道" : "现场确认终端在线");
  get("link").dataset.tone = live ? "live" : "";
  const waiting = data && data.stage === "sender" ? "正在等待感知端握手。" :
    "正在等待接收端通过星闪回传心跳。";
  update("reason", live ? ({
    calibrating: "保持通道原状，等待稳定的测距基线。",
    occupied: data.detect_range_m ?
      "已确认 " + data.detect_range_m + " 米内有物体，本次占道持续记录至通道恢复。" :
      "已确认通道内出现持续的近距变化。",
    clear: "未检测到持续的近距变化。",
    unknown: "能够观测的基线不足，等待重新确认。"
  })[state] : data && data.error ? data.error :
    data && data.running ? waiting : "静态监测适用于固定机架。");
  update("baseline", latest ? latest.valid_baseline + " / " + latest.roi_count : "—");
  update("observed", latest && latest.fresh ? latest.observed + " / " + latest.valid_baseline : "—");
  update("scans", latest ? number.format(latest.scans) : "—");
  update("bytes", latest ? number.format(data.received_bytes) + " B" : "—");
  update("full", latest && latest.scans ? number.format(data.same_rate_full_bytes) + " B" : "—");
  update("frames", latest ? data.received_reports + " / " + data.missing_reports : "—");
  update("last", latest ? "最近报告 · " + labels[latest.kind] + " · 序号 " + latest.seq : "");
  renderEvents(data);
}

async function refresh() {
  const load = async (url) => {
    const response = await fetch(url, {cache: "no-store"});
    if (!response.ok) throw new Error("request failed");
    return response.json();
  };
  const [watch, station] = await Promise.allSettled([load("/api/watch"), load("/api/station")]);
  render(watch.value, watch.status === "rejected");
  renderStation(station.value);
  setTimeout(refresh, 750);
}

function renderStation(station) {
  update("usb-status", !station ? "页面接收中断" : station.online ? "正在接收" : "终端离线");
  get("usb-status").dataset.tone = station && station.online ? "live" : "";
  if (!station) return;
  update("usb-port", station.port || "—");
  update("usb-total", number.format(station.received));
  const ack = station.last_ack;
  update("usb-ack", ack ? "事件 #" + ack.event_id + (ack.accepted ? " · 已确认" : " · 未匹配") : "等待确认报文");
  get("usb-empty").hidden = station.frames.length > 0;
  const entries = station.frames.map((frame) => {
    const row = document.createElement("li");
    const sequence = document.createElement("span");
    const message = document.createElement("code");
    sequence.textContent = "#" + frame.number;
    message.textContent = frame.line;
    row.append(sequence, message);
    return row;
  });
  get("usb-frames").replaceChildren(...entries);
}

refresh();
