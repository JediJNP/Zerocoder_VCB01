## Игра «Шарики: всасывай, смешивай, выплёвывай»

Небольшая аркада на `pygame`: разноцветные шарики летают по полю, смешивают цвета при соприкосновении, а вы можете «всасывать» их курсором в инвентарь и затем «выплёвывать» обратно.

- **ЛКМ (удерживать)**: включить всасывание курсором и забирать шарики в инвентарь.
- **ПКМ (клик)**: выплюнуть следующий шарик из инвентаря в направлении последнего движения мыши.
- **ESC**: выход.

Логика симуляции вынесена в `VCB01/logic.py` (класс `GameLogic`). Графический запуск оформлен через точку входа `gui.py`.

### Зависимости и локальный запуск

Требуется Python 3.11+.

Установите зависимости (достаточно только `pygame`):

```bash
python -m pip install --upgrade pip
pip install pygame
```

Запуск игры одной командой:

```bash
python gui.py
```

### Сборка и запуск в Docker (X11)

В контейнере используется X11 для вывода окна. Перед запуском убедитесь, что на хосте запущен X‑сервер:

- Linux: системный Xorg уже запущен.
- macOS: установите XQuartz и включите «Allow connections from network clients».
- Windows: установите и запустите VcXsrv (или Xming), разрешив подключения без контроля доступа, либо добавьте правило доступа.

Соберите образ:

```bash
docker build -t marble-game .
```

Запуск контейнера (окно игры должно появиться на хосте):

- Linux:

```bash
xhost +local:root
docker run --rm \
  -e DISPLAY=${DISPLAY} \
  -v /tmp/.X11-unix:/tmp/.X11-unix:ro \
  marble-game
xhost -local:root
```

- macOS (XQuartz):

```bash
# В XQuartz: Preferences → Security → Allow connections from network clients
export DISPLAY=host.docker.internal:0
docker run --rm -e DISPLAY=${DISPLAY} marble-game
```

- Windows (VcXsrv):

```powershell
# Запустите VcXsrv (Display: 0, Disable access control — для простоты)
docker run --rm -e DISPLAY=host.docker.internal:0.0 marble-game
```

Примечания:

- Образ основан на `python:3.11-slim` и устанавливает системные библиотеки X11/GL/шрифты для корректной работы `pygame`.
- В контейнере точка входа уже задана: окно игры откроется сразу после `docker run`.

### Структура проекта

- `VCB01/logic.py` — логика симуляции и функция `run_game()` для запуска графики на `pygame`.
- `gui.py` — точка входа (одна команда запуска).
- `Dockerfile` — контейнер для запуска с X11.

