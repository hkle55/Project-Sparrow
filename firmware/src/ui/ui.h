// Screen layouts. Each build compiles exactly one ui_<W>x<H>.cpp (see platformio.ini).
// Layouts only draw: every decision (countdown state, tight/missed) comes from core/.
// They use only the LovyanGFX sprite API, so they're reusable on any board that has it.
#pragma once

#include <M5GFX.h>

#include "core/sparrow_core.h"

namespace sparrow {

struct ScreenState {
  const Model* model = nullptr;
  bool haveModel = false;
  int64_t now = 0;           // device's best estimate of server time (epoch s)
  bool noConn = false;       // polls have been failing for a while
  bool lastPollFailed = false;
  const char* lastError = "";
  int batteryPct = -1;       // -1 = unknown
  bool clockView = false;    // show clock times instead of countdowns (where supported)
};

int screenWidth();
int screenHeight();
void drawScreen(lgfx::LGFX_Sprite& c, const ScreenState& s);

// Colors (RGB565). Urgency never relies on color alone: text and inversion carry it too.
constexpr uint16_t kBlack = 0x0000, kWhite = 0xFFFF, kGrey = 0x8410;
constexpr uint16_t kRed = 0xF9C6, kYellow = 0xFEA7, kGreen = 0x3666;

}  // namespace sparrow
