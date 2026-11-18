// Copy to include/secrets.h (gitignored) and fill in. Never commit real values.
#pragma once

// Her home Wi-Fi (V1 only needs this one). Add a second network, e.g. a phone hotspot,
// in SPARROW_WIFI_2_* or leave it empty.
#define SPARROW_WIFI_1_SSID "home-network-name"
#define SPARROW_WIFI_1_PASS "home-network-password"
#define SPARROW_WIFI_2_SSID ""
#define SPARROW_WIFI_2_PASS ""

// Hosted backend (docs/deployment.md) and its SPARROW_ACCESS_TOKEN.
#define SPARROW_API_URL "https://sparrow-example.fly.dev/api/v1/device"
#define SPARROW_TOKEN "paste-the-access-token-here"
