# Changelog

## 0.4.1

- Migrated the integration to a GitHub/HACS-ready repository layout.
- Added repository documentation and issue-tracker metadata.
- Added `@bronzedragon` as integration code owner.
- Switched custom-integration localization to `translations/en.json` only for current Home Assistant compatibility.
- Added bundled local brand assets and GitHub validation workflows for HACS and Hassfest.
- No AVPro protocol, entity, service, or config-entry behavior changes from v0.4.0.

## 0.4.0

- Added Home Assistant `media_player` entities for both matrix outputs.
- Added model-specific Telnet framing: MX42 legacy leading-CRLF behavior is preserved; MX82 uses the manual's command + Return framing.
- Renamed the Output 1 scaler entity to `4K-to-2K scaler`.
- Added AC-MX82-AUHD extracted-audio binding control.
- Added AC-MX82-AUHD AVR mirror/double-switch control.
- Added AC-MX82-AUHD extracted-audio enable/mute control.
- Added per-output AC-MX82-AUHD HDMI-audio mute controls.
- Advanced MX82 status polling is non-fatal so basic routing remains available if an advanced firmware response differs.
- Clarified that Home Assistant input/output labels do not alter the matrix's 8-character Port Alias settings.
- Added generic home-theater dashboard, compact remote, scripts, and optional universal media-player examples.

## 0.3.0

- Added AC-MX82-AUHD model support and Inputs 5-8.
- Preserved AC-MX42-AUHD upgrades under the existing `avpro_mx42` domain.
