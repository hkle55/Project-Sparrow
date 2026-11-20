// 240x135 layout (M5Stack StickS3, landscape). Moved unchanged from main.cpp.
#include <stdio.h>
#include <string.h>

#include "ui.h"

namespace sparrow {

namespace {

constexpr int W = 240, H = 135;

void textAt(lgfx::LGFX_Sprite& c, const char* s, int x, int y, const lgfx::IFont* font,
            uint16_t color, lgfx::textdatum_t datum = lgfx::top_left, float size = 1.0f) {
  c.setFont(font);
  c.setTextSize(size);
  c.setTextColor(color);
  c.setTextDatum(datum);
  c.drawString(s, x, y);
}

void drawChip(lgfx::LGFX_Sprite& c, const ScreenState& s) {
  const Model& model = *s.model;
  const char* label;
  uint16_t color;
  if (s.noConn) { label = "NO WIFI"; color = kRed; }
  else if (model.simulated) { label = "SIM"; color = kYellow; }
  else if (model.status == DataStatus::Live) { label = "LIVE"; color = kGreen; }
  else if (model.status == DataStatus::Stale) { label = "STALE"; color = kYellow; }
  else { label = "SCHED"; color = kYellow; }
  c.setFont(&fonts::Font2);
  const int w = c.textWidth(label) + 8;
  c.drawRect(W - w - 3, 2, w, 17, color);
  textAt(c, label, W - w / 2 - 3, 4, &fonts::Font2, color, lgfx::top_center);

  if (s.batteryPct >= 0) {
    char b[8];
    snprintf(b, sizeof b, "%d%%", s.batteryPct);
    textAt(c, b, W - w - 8, 4, &fonts::Font2, s.batteryPct <= 15 ? kRed : kGrey, lgfx::top_right);
  }
}

void drawHero(lgfx::LGFX_Sprite& c, const ScreenState& s) {
  const Model& model = *s.model;
  const Rec& r = model.rec;
  const int64_t now = s.now;
  if (!r.present) {
    textAt(c, "NO BUS", 6, 4, &fonts::FreeSansBold9pt7b, kGrey);
    textAt(c, model.msg, W / 2, 55, &fonts::Font2, kWhite, lgfx::middle_center);
    return;
  }
  char buf[48];
  snprintf(buf, sizeof buf, "BUS %s", r.route);
  textAt(c, buf, 6, 3, &fonts::FreeSansBold12pt7b, kWhite);

  const HeroView v = hero(model, now);
  switch (v.hero) {
    case Hero::Leave:
    case Hero::Ready: {
      const bool ready = v.hero == Hero::Ready;
      textAt(c, ready ? "GET READY" : "LEAVE IN", 8, 28, &fonts::Font2, ready ? kYellow : kGrey);
      snprintf(buf, sizeof buf, "%d", v.minutes);
      textAt(c, buf, 6, 44, &fonts::FreeSansBold24pt7b, kWhite, lgfx::top_left, 1.4f);
      c.setFont(&fonts::FreeSansBold24pt7b);
      const int numW = c.textWidth(buf) * 1.4f;
      c.setTextSize(1);
      textAt(c, "min", 14 + numW, 66, &fonts::FreeSansBold12pt7b, kWhite);
      if (ready) c.drawRect(3, 26, 120 + numW / 2, 64, kYellow);
      break;
    }
    case Hero::Now:
      c.fillRect(4, 28, W - 8, 56, kWhite);
      textAt(c, "LEAVE NOW", W / 2, 56, &fonts::FreeSansBold18pt7b, kBlack, lgfx::middle_center);
      break;
    case Hero::Tight:
      for (int x = 4; x < W - 4; x += 8) {  // dashed red frame
        c.drawFastHLine(x, 28, 5, kRed);
        c.drawFastHLine(x, 83, 5, kRed);
      }
      c.drawFastVLine(4, 28, 56, kRed);
      c.drawFastVLine(W - 5, 28, 56, kRed);
      textAt(c, "TIGHT - GO", W / 2, 50, &fonts::FreeSansBold18pt7b, kWhite, lgfx::middle_center);
      if (v.spareS < 60) snprintf(buf, sizeof buf, "<1 min to spare");
      else snprintf(buf, sizeof buf, "%d min to spare", floorMinutes(v.spareS));
      textAt(c, buf, W / 2, 75, &fonts::Font2, kRed, lgfx::middle_center);
      break;
    case Hero::Checking:
      textAt(c, "CHECKING...", W / 2, 56, &fonts::FreeSansBold12pt7b, kGrey, lgfx::middle_center);
      break;
    case Hero::NoBus:
      break;
  }
  if ((r.approx || s.noConn) && v.hero != Hero::Checking) {
    textAt(c, "~ not live", W - 6, 28, &fonts::Font2, kYellow, lgfx::top_right);
  }

  // Secondary line: offline warning > safer alternative > reason.
  if (s.noConn) {
    snprintf(buf, sizeof buf, "Offline: countdown may be off");
  } else if (r.hasAlt) {
    const int64_t al = r.altLeaveAt - now;
    if (al >= 0) snprintf(buf, sizeof buf, "Safer: %s leave in %dm", r.altRoute, floorMinutes(al));
    else snprintf(buf, sizeof buf, "Safer: bus %s", r.altRoute);
  } else {
    snprintf(buf, sizeof buf, "%s", r.why);
  }
  textAt(c, buf, 6, 89, &fonts::Font2, s.noConn ? kRed : kGrey);
}

void drawRows(lgfx::LGFX_Sprite& c, const ScreenState& s) {
  const Model& model = *s.model;
  char buf[8];
  for (int i = 0; i < model.nRows; i++) {
    const Row& row = model.rows[i];
    const int y = 104 + i * 16;
    textAt(c, row.route, 6, y, &fonts::Font2, kWhite);
    for (int j = 0; j < kMaxArrivals; j++) {
      const int x = 92 + j * 52;
      if (j >= row.n) {
        textAt(c, "-", x, y, &fonts::Font2, kGrey, lgfx::top_right);
        continue;
      }
      const Arrival& a = row.t[j];
      const bool live = a.kind == Kind::Live;
      const int64_t to = a.at - s.now;
      if (to <= 30) snprintf(buf, sizeof buf, "%snow", live ? "" : "~");
      else snprintf(buf, sizeof buf, "%s%d", live ? "" : "~", floorMinutes(to));
      const Cell cs = cell(model, row, a, s.now);
      const uint16_t color = cs == Cell::Missed ? kGrey : live ? kWhite : kYellow;
      textAt(c, buf, x, y, &fonts::Font2, color, lgfx::top_right);
      c.setFont(&fonts::Font2);
      const int w = c.textWidth(buf);
      if (cs == Cell::Missed) c.drawFastHLine(x - w, y + 8, w, kGrey);
      if (cs == Cell::Tight) textAt(c, "!", x + 2, y, &fonts::Font2, kRed);
    }
    textAt(c, "min", W - 4, y, &fonts::Font0, kGrey, lgfx::top_right);
  }
}

}  // namespace

int screenWidth() { return W; }
int screenHeight() { return H; }

void drawScreen(lgfx::LGFX_Sprite& c, const ScreenState& s) {
  c.fillScreen(kBlack);
  if (!s.haveModel) {
    textAt(c, s.lastPollFailed ? "NO CONNECTION" : "CONNECTING...", W / 2, 58,
           &fonts::FreeSansBold12pt7b, s.lastPollFailed ? kRed : kWhite, lgfx::middle_center);
    if (s.lastPollFailed) textAt(c, s.lastError, W / 2, 85, &fonts::Font2, kGrey, lgfx::middle_center);
    return;
  }
  drawChip(c, s);
  drawHero(c, s);
  drawRows(c, s);
}

}  // namespace sparrow
