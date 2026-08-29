# FinWise (finanse)

Учёт личных финансов на **Python 3.11+** и **Flet**. Данные только на устройстве:
SQLite + SQLAlchemy. Слои: `domain` → use cases → `infrastructure` → `presentation`.

Документация: [`docs/README.md`](docs/README.md)

## Запуск на ПК

```powershell
python -m pip install -r requirements.txt
python scripts/migrate.py
python main.py
```

Каталог данных Windows: `%LOCALAPPDATA%\finanse\finanse\`.

Демо: `python scripts/seed_demo_data.py --wipe --scale medium --currency UZS`  
Тесты: `python -m pytest -q`

## Сборка на телефон

Биометрия, системные уведомления, микрофон и ярлык `finwise://voice` работают
только в установленном IPA/APK (не в `flet run --android`).

```powershell
.\scripts\build_apk.ps1
```

IPA: [`docs/CODEMAGIC.md`](docs/CODEMAGIC.md).
