// Sparrow V1 firmware for the M5Stack StickS3: work commute only, no mode toggle.
//
// Power button: on (press) / off (double press). Button A: refresh now and keep the screen
// awake. The device polls /api/v1/device every 20 s, counts down locally every second, and
// powers itself off after 10 minutes without a button press.
//
// All transit decisions come from the backend. All screen decisions live in core/
// (unit-tested natively). This file is only hardware: Wi-Fi, HTTPS, buttons, drawing.
#include <HTTPClient.h>
#include <M5Unified.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <WiFiMulti.h>

#include "core/sparrow_core.h"
#include "root_ca.h"
#include "secrets.h"

using namespace sparrow;

namespace {

constexpr uint32_t kPollMs = 20000;           // backend caches SEPTA for 20 s
constexpr uint32_t kAwakeMs = 10 * 60 * 1000;  // power off after 10 min idle
constexpr uint32_t kHttpTimeoutMs = 6000;
constexpr bool kBeep = true;                   // beep once on LEAVE NOW / TIGHT
constexpr int W = 240, H = 135;

WiFiMulti wifi;
M5Canvas canvas(&M5.Display);

Model model;
bool haveModel = false;
uint32_t fetchedAtMs = 0, lastOkMs = 0, lastPollMs = 0, lastActivityMs = 0;
bool lastPollFailed = false;
char lastError[40] = "";
Hero lastHero = Hero::NoBus;

// Colors (RGB565). Urgency never relies on color alone: text and inversion carry it too.
constexpr uint16_t kBlack = TFT_BLACK, kWhite = TFT_WHITE, kGrey = 0x8410;
constexpr uint16_t kRed = 0xF9C6, kYellow = 0xFEA7, kGreen = 0x3666;

// --- networking ----------------------------------------------------------------------

void setError(const char* e) {
  strncpy(lastError, e, sizeof lastError - 1);
  lastPollFailed = true;
}

void poll() {
  lastPollMs = millis();
  if (wifi.run(5000) != WL_CONNECTED) return setError("Wi-Fi not connected");

  const bool https = strncmp(SPARROW_API_URL, "https://", 8) == 0;
  WiFiClientSecure secure;
  WiFiClient plain;
  if (https) secure.setCACert(kRootCAs);
  HTTPClient http;
  http.setTimeout(kHttpTimeoutMs);
  http.setConnectTimeout(kHttpTimeoutMs);
  if (!http.begin(https ? static_cast<WiFiClient&>(secure) : plain, SPARROW_API_URL)) {
    return setError("bad URL");
  }
  http.addHeader("X-Sparrow-Token", SPARROW_TOKEN);
  const int code = http.GET();
  if (code != 200) {
    char e[24];
    snprintf(e, sizeof e, code < 0 ? "network %d" : "HTTP %d", code);
    http.end();
    return setError(e);
  }
  String body = http.getString();
  http.end();
  Model m;
  if (!parse(body.c_str(), body.length(), m)) return setError("bad data");
  model = m;
  haveModel = true;
  fetchedAtMs = lastOkMs = millis();
  lastPollFailed = false;
  lastError[0] = '\0';
}

// --- drawing -------------------------------------------------------------------------

void textAt(const char* s, int x, int y, const lgfx::IFont* font, uint16_t color,
            textdatum_t datum = top_left, float size = 1.0f) {
  canvas.setFont(font);
  canvas.setTextSize(size);
  canvas.setTextColor(color);
  canvas.setTextDatum(datum);
  canvas.drawString(s, x, y);
}

void drawChip(bool noConn) {
  const char* label;
  uint16_t color;
  if (noConn) { label = "NO WIFI"; color = kRed; }
  else if (model.simulated) { label = "SIM"; color = kYellow; }
  else if (model.status == DataStatus::Live) { label = "LIVE"; color = kGreen; }
  else if (model.status == DataStatus::Stale) { label = "STALE"; color = kYellow; }
  else { label = "SCHED"; color = kYellow; }
  canvas.setFont(&fonts::Font2);
  const int w = canvas.textWidth(label) + 8;
  canvas.drawRect(W - w - 3, 2, w, 17, color);
  textAt(label, W - w / 2 - 3, 4, &fonts::Font2, color, top_center);

  const int pct = M5.Power.getBatteryLevel();  // -1 if unknown
  if (pct >= 0) {
    char b[8];
    snprintf(b, sizeof b, "%d%%", pct);
    textAt(b, W - w - 8, 4, &fonts::Font2, pct <= 15 ? kRed : kGrey, top_right);
  }
}

void drawHero(int64_t now, bool noConn) {
  const Rec& r = model.rec;
  if (!r.present) {
    textAt("NO BUS", 6, 4, &fonts::FreeSansBold9pt7b, kGrey);
    textAt(model.msg, W / 2, 55, &fonts::Font2, kWhite, middle_center);
    return;
  }
  char buf[48];
  snprintf(buf, sizeof buf, "BUS %s", r.route);
  textAt(buf, 6, 3, &fonts::FreeSansBold12pt7b, kWhite);

  const HeroView v = hero(model, now);
  if (kBeep && v.hero != lastHero && (v.hero == Hero::Now || v.hero == Hero::Tight)) {
    M5.Speaker.tone(2600, 120);
  }
  lastHero = v.hero;

  switch (v.hero) {
    case Hero::Leave:
    case Hero::Ready: {
      const bool ready = v.hero == Hero::Ready;
      textAt(ready ? "GET READY" : "LEAVE IN", 8, 28, &fonts::Font2, ready ? kYellow : kGrey);
      snprintf(buf, sizeof buf, "%d", v.minutes);
      textAt(buf, 6, 44, &fonts::FreeSansBold24pt7b, kWhite, top_left, 1.4f);
      canvas.setFont(&fonts::FreeSansBold24pt7b);
      const int numW = canvas.textWidth(buf) * 1.4f;
      canvas.setTextSize(1);
      textAt("min", 14 + numW, 66, &fonts::FreeSansBold12pt7b, kWhite);
      if (ready) canvas.drawRect(3, 26, 120 + numW / 2, 64, kYellow);
      break;
    }
    case Hero::Now:
      canvas.fillRect(4, 28, W - 8, 56, kWhite);
      textAt("LEAVE NOW", W / 2, 56, &fonts::FreeSansBold18pt7b, kBlack, middle_center);
      break;
    case Hero::Tight:
      for (int x = 4; x < W - 4; x += 8) {  // dashed red frame
        canvas.drawFastHLine(x, 28, 5, kRed);
        canvas.drawFastHLine(x, 83, 5, kRed);
      }
      canvas.drawFastVLine(4, 28, 56, kRed);
      canvas.drawFastVLine(W - 5, 28, 56, kRed);
      textAt("TIGHT - GO", W / 2, 50, &fonts::FreeSansBold18pt7b, kWhite, middle_center);
      if (v.spareS < 60) snprintf(buf, sizeof buf, "<1 min to spare");
      else snprintf(buf, sizeof buf, "%d min to spare", floorMinutes(v.spareS));
      textAt(buf, W / 2, 75, &fonts::Font2, kRed, middle_center);
      break;
    case Hero::Checking:
      textAt("CHECKING...", W / 2, 56, &fonts::FreeSansBold12pt7b, kGrey, middle_center);
      break;
    case Hero::NoBus:
      break;
  }
  if ((r.approx || noConn) && v.hero != Hero::Checking) {
    textAt("~ not live", W - 6, 28, &fonts::Font2, kYellow, top_right);
  }

  // Secondary line: offline warning > safer alternative > reason.
  if (noConn) {
    snprintf(buf, sizeof buf, "Offline: countdown may be off");
  } else if (r.hasAlt) {
    const int64_t al = r.altLeaveAt - now;
    if (al >= 0) snprintf(buf, sizeof buf, "Safer: %s leave in %dm", r.altRoute, floorMinutes(al));
    else snprintf(buf, sizeof buf, "Safer: bus %s", r.altRoute);
  } else {
    snprintf(buf, sizeof buf, "%s", r.why);
  }
  textAt(buf, 6, 89, &fonts::Font2, noConn ? kRed : kGrey);
}

void drawRows(int64_t now) {
  char buf[8];
  for (int i = 0; i < model.nRows; i++) {
    const Row& row = model.rows[i];
    const int y = 104 + i * 16;
    textAt(row.route, 6, y, &fonts::Font2, kWhite, top_left, 1.0f);
    for (int j = 0; j < kMaxArrivals; j++) {
      const int x = 92 + j * 52;
      if (j >= row.n) {
        textAt("-", x, y, &fonts::Font2, kGrey, top_right);
        continue;
      }
      const Arrival& a = row.t[j];
      const bool live = a.kind == Kind::Live;
      const int64_t to = a.at - now;
      if (to <= 30) snprintf(buf, sizeof buf, "%snow", live ? "" : "~");
      else snprintf(buf, sizeof buf, "%s%d", live ? "" : "~", floorMinutes(to));
      const Cell c = cell(model, row, a, now);
      const uint16_t color = c == Cell::Missed ? kGrey : live ? kWhite : kYellow;
      textAt(buf, x, y, &fonts::Font2, color, top_right);
      canvas.setFont(&fonts::Font2);
      const int w = canvas.textWidth(buf);
      if (c == Cell::Missed) canvas.drawFastHLine(x - w, y + 8, w, kGrey);
      if (c == Cell::Tight) textAt("!", x + 2, y, &fonts::Font2, kRed);
    }
    textAt("min", W - 4, y, &fonts::Font0, kGrey, top_right);
  }
}

void render() {
  const uint32_t nowMs = millis();
  const bool noConn = noConnection(lastPollFailed, lastOkMs, nowMs);
  canvas.fillScreen(kBlack);
  if (!haveModel) {
    textAt(lastPollFailed ? "NO CONNECTION" : "CONNECTING...", W / 2, 58,
           &fonts::FreeSansBold12pt7b, lastPollFailed ? kRed : kWhite, middle_center);
    if (lastPollFailed) textAt(lastError, W / 2, 85, &fonts::Font2, kGrey, middle_center);
  } else {
    const int64_t now = deviceNow(model, fetchedAtMs, nowMs);
    drawChip(noConn);
    drawHero(now, noConn);
    drawRows(now);
  }
  canvas.pushSprite(0, 0);
}

}  // namespace

void setup() {
  auto cfg = M5.config();
  M5.begin(cfg);
  M5.Display.setRotation(1);  // landscape, 240x135
  M5.Display.setBrightness(160);
  M5.Speaker.setVolume(96);   // keep it modest on battery (vendor guidance: < 75%)
  canvas.setColorDepth(16);
  canvas.createSprite(W, H);

  WiFi.mode(WIFI_STA);
  wifi.addAP(SPARROW_WIFI_1_SSID, SPARROW_WIFI_1_PASS);
  if (strlen(SPARROW_WIFI_2_SSID) > 0) wifi.addAP(SPARROW_WIFI_2_SSID, SPARROW_WIFI_2_PASS);

  lastActivityMs = millis();
  render();  // "CONNECTING..." immediately
  poll();
}

void loop() {
  M5.update();
  const uint32_t nowMs = millis();
  if (M5.BtnA.wasPressed() || M5.BtnB.wasPressed()) {
    lastActivityMs = nowMs;
    poll();
  }
  if (nowMs - lastPollMs >= kPollMs) poll();
  if (nowMs - lastActivityMs >= kAwakeMs) {
    M5.Display.fillScreen(kBlack);
    M5.Power.powerOff();  // press the power button to wake
  }
  static uint32_t lastDraw = 0;
  if (nowMs - lastDraw >= 250) {
    lastDraw = nowMs;
    render();
  }
  delay(10);
}
