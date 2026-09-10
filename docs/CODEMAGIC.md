# FinWise — сборка IPA через Codemagic

Сборка подписанного **IPA** для iPhone. Конфиг: корневой `codemagic.yaml`.  
Репозиторий: [github.com/Rom4ik121/FinWise](https://github.com/Rom4ik121/FinWise).

- **`ios-ipa`** — Ad Hoc (тестовые устройства по UDID)
- **`ios-appstore`** — App Store / TestFlight (нужен App Store provisioning profile)

Бесплатный личный план Codemagic: до **~500 мин/мес** на macOS (актуальные лимиты — на сайте Codemagic).

---

## Что попадает в IPA

| Компонент | Зачем |
|-----------|--------|
| Editable-пакеты из `requirements.txt` (`flet_local_auth`, `flet_local_notifications`) | Face ID, локальные пуши |
| matplotlib Agg | PDF charts (in-app dashboard charts use Flet canvas, **not** matplotlib). Kept in the IPA so PDF export stays correct. |
| Mobile-safe **ccxt** via `vendor/ccxt` (`[tool.flet.dev_packages]`) | Биржи по API; пакет генерируется `scripts/vendor_ccxt_mobile.py` перед `flet build` |
| `cryptography` **&lt; 50** | Совместимость с `pypi.flet.dev` wheels |
| Splash `#0B1220` | Бренд (как в `flet.toml` / Codemagic scripts) |

На Codemagic шаг **Vendor mobile-safe ccxt** обязателен. Не использовать относительный `file:./vendor/wheels/...`.

Info.plist (via `pyproject.toml` / IPA patch) asks for **Face ID** and **photo library** (receipt attachments). Do **not** add unused microphone / speech keys — App Store 5.1.1.

The IPA patch (`scripts/patch_ios_appdelegate.py`) also:

- sets `UNUserNotificationCenter.delegate` + `willPresent` (banners while FinWise is open)
- writes `PrivacyInfo.xcprivacy` (required-reason APIs)
- strips Flet's leftover AdMob test ID and unused mic/camera/location strings
- sets `ITSAppUsesNonExemptEncryption=false` and HTTPS-only ATS

Without a **new** IPA, plugin / Python / plist changes will not appear on device.

**Не** ставить `flet-android-notifications` в iOS-сборку: конфликт версий Flutter-пакета `timezone` с `flet_local_notifications`.

---

## Что нужно заранее

| Требование | Зачем |
|------------|--------|
| Репозиторий на **GitHub** (FinWise) | Codemagic подключается к Git |
| **Apple Developer Program** (~$99/год) | Подпись IPA |
| **UDID** тестового iPhone | В Ad Hoc профиле |
| App ID **`com.finanse.app`** | Совпадает с `flet.toml` / `pyproject.toml` |
| **Team ID** (10 символов) | Membership в Apple Developer |

---

## Шаг 1. Код на GitHub

Убедитесь, что remote указывает на FinWise и есть `codemagic.yaml`, `main.py`, `requirements.txt`:

```powershell
cd C:\Users\Admin\Desktop\Projects\finanse
git remote -v
git push -u origin main
```

(Опционально: `.\scripts\push_github.ps1`, если скрипт актуален для вашего remote.)

---

## Шаг 2. Регистрация Codemagic

1. [codemagic.io](https://codemagic.io) → **Sign up with GitHub**.
2. Разрешите доступ к репозиторию **FinWise**.
3. **Add application** → выберите **FinWise**.
4. Тип конфигурации: **codemagic.yaml** (не визуальный Flutter editor).

---

## Шаг 3. Apple — App ID и устройство

1. [developer.apple.com](https://developer.apple.com/account) → **Certificates, Identifiers & Profiles**.
2. **Identifiers** → **+** → App → Bundle ID: **`com.finanse.app`**.
3. **Devices** → **+** → UDID iPhone (Xcode → Devices, или Finder).
4. Запишите **Team ID** (Membership details).

---

## Шаг 4. Сертификат и Ad Hoc профиль

### Certificate (Distribution)

1. На Mac: Keychain Access → Certificate Assistant → **Request a Certificate** → `.certSigningRequest`.
2. Developer Portal → **Certificates** → **+** → **Apple Distribution** → CSR → `.cer` → установить в Keychain.
3. Export **Apple Distribution** → **`.p12`** (с паролем).

### Provisioning Profile (Ad Hoc)

1. **Profiles** → **+** → **Ad Hoc** → App ID `com.finanse.app`.
2. Distribution certificate + нужные устройства (UDID).
3. Скачать `.mobileprovision`.

---

## Шаг 5. Подпись в Codemagic

1. Codemagic → **Teams** → **Code signing identities**.
2. **iOS certificates** → загрузить `.p12` (reference, напр. `finanse_distribution`).
3. **iOS provisioning profiles** → `.mobileprovision` (напр. `finanse_adhoc`), тип **ad_hoc**, Bundle ID **`com.finanse.app`**.

Альтернатива: App Store Connect API key + `app-store-connect fetch-signing-files` — см. [доку Codemagic](https://docs.codemagic.io/yaml-code-signing/signing-ios/).

В `codemagic.yaml` уже указано:

```yaml
ios_signing:
  distribution_type: ad_hoc
  bundle_identifier: com.finanse.app
```

---

## Шаг 6. Переменные окружения

Группа **`finanse_ios`** (имя из yaml):

| Variable | Value | Secure |
|----------|--------|--------|
| `APPLE_TEAM_ID` | ваш 10-символьный Team ID | по желанию |

Workflow `ios-ipa` подключает группу `finanse_ios`.

---

## Шаг 7. Запуск сборки

1. Приложение **FinWise** в Codemagic → **Start new build**.
2. Workflow: **`ios-ipa`** (FinWise iOS IPA Ad Hoc).
3. Branch: **main** → Start.

Первая сборка часто **30–60+ минут** (Flet + Xcode).

### Без готовой подписи

Workflow **`ios-smoke`** — проверка, что проект собирается на macOS (IPA не гарантируется).

Оба workflow задают `--splash-color "#0B1220"` / `--splash-dark-color "#0B1220"`.

---

## Шаг 8. Установка IPA

1. **Artifacts** → скачать `*.ipa`.
2. Установка:
   - Mac + **Apple Configurator** (USB);
   - или **TestFlight** (нужен publish / Transporter).
3. На iPhone: **Settings → General → VPN & Device Management** → Trust.

### Без Mac

Codemagic только **собирает**. На Windows: TestFlight / Sideloadly / AltStore (ограничения Apple и Ad Hoc UDID) или попросить установить с Mac.

---

## Workflows в `codemagic.yaml`

| ID | Назначение |
|----|------------|
| `ios-ipa` | Подписанный Ad Hoc IPA, артефакты `build/ipa/*.ipa` |
| `ios-appstore` | Подписанный App Store IPA (TestFlight / App Store Connect) |
| `ios-smoke` | Smoke без полной подписи / simulator fallback |

Исключения из бандла: `build`, `tests`, `docs`, `.cursor`, venv, кэши и т.д. (см. `--exclude` в yaml).

---

## Частые ошибки

| Ошибка | Решение |
|--------|---------|
| `APPLE_TEAM_ID is missing` | Группа `finanse_ios` + переменная |
| No matching provisioning profile | Bundle ID / ad_hoc / UDID в профиле |
| `ResolutionImpossible` / `ccxt` | Нужен wheel из `vendor/wheels/` (без aiodns). Пересобрать: `python scripts/vendor_ccxt_mobile.py` и закоммитить. Не ставить upstream `ccxt` из PyPI в `[project].dependencies`. |
| `ResolutionImpossible` / cryptography | Держать `cryptography>=42,<50` под wheels `pypi.flet.dev`. |
| Binary wheel not found for iOS | Смотреть лог; убрать пакет без iOS wheel |
| Конфликт `timezone` 0.9 vs 0.11 | Не тянуть android-notifications в IPA |
| Build timeout | Увеличить `max_build_duration` |
| Лимит минут | Ждать новый месяц или billing |

---

## Android (кратко)

APK собирается локально: `.\scripts\build_apk.ps1` (не Codemagic).  
Цвет splash в скрипте может отличаться от `#0B1220` — для единообразия с iOS/`flet.toml` лучше выровнять флаги `--splash-color`.

---

## App Store / iPhone checklist

Already in the product:

- Local-first SQLite, no required account
- Face ID + PIN, 15s background lock on mobile
- `NSFaceIDUsageDescription`, photo-library strings, `ITSAppUsesNonExemptEncryption=false`
- Privacy manifest (`ios/PrivacyInfo.xcprivacy`) copied into the Runner at IPA build
- HTTPS FX/crypto APIs; IPA patch forces ATS `NSAllowsArbitraryLoads=false`
- Offline ledger; rates/sync need network
- Local notifications + AppDelegate `willPresent`

Still blocking a store listing (owner / Apple account):

1. Apple Developer Program + App ID `com.finanse.app`
2. App Store Connect app record, screenshots (6.7" + 6.1"), privacy nutrition labels
3. Codemagic **App Store** provisioning profile (not only Ad Hoc) → workflow `ios-appstore`
4. Privacy labels: financial info on-device; no tracking (`NSPrivacyTracking=false`)
5. TestFlight internal testers, then review
6. **CCXT / exchanges stay in v1.0** (product decision — do not strip)

Not implemented (product call, do not ship unused permissions):

- Speech / microphone (removed from docs; do not add Info.plist keys)
- iCloud Drive / CloudKit sync
- Touch ID (Face ID / iris only by policy)

Shipped in this branch:

- iOS Keychain for the secret-box master key (file fallback on desktop/Android; migrate + delete file after a successful Keychain write)
- Encrypted ``.fwbackup`` share bundle (database + key + receipt photos); restore still accepts older ``.db`` / sidecar ``.key`` / embedded ``_finanse_secret_box`` / ``FWEX``
- Native Settings deep-link when notification permission is denied

---

## Полезные ссылки

- [Codemagic — iOS signing](https://docs.codemagic.io/yaml-code-signing/signing-ios/)
- [Flet — iOS publish](https://flet.dev/docs/publish/ios/)
- [Codemagic pricing](https://docs.codemagic.io/billing/pricing/)
- Документация приложения — [README.md](README.md)  
