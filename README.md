# VK Notify (Keyboard Edition) ⌨️

Форк оригинальной интеграции `VK Notify` с добавленной поддержкой интерактивных клавиатур, callback-кнопок и динамического изменения сообщений. Эта версия позволяет управлять вашим домом через ВКонтакте в «тихом» режиме, создавая настоящие умные пульты прямо в чате.

---

## 🚀 Что нового в этой версии

* **Действие `vk_notify.send_message`**: Расширенный сервис для отправки сообщений с поддержкой JSON-клавиатур.
* **Динамическое редактирование (`vk_notify.edit_message`)**: Возможность изменять текст и кнопки уже отправленного сообщения в чате (идеально для изменения статусов вкл/выкл).
* **Удаление сообщений (`vk_notify.delete_message`)**: Удаление сообщений бота у всех участников чата (вручную или по таймеру).
* **Callback-кнопки**: Кнопки, которые при нажатии не отправляют текст в чат, а генерируют скрытое событие внутри Home Assistant (с передачей `conversation_message_id` для редактирования или удаления).
* **Инлайн-клавиатуры**: Кнопки, которые прикрепляются прямо к сообщению, а не висят под полем ввода.
* **Цветные кнопки**: Поддержка всех 4-х стандартных цветов VK (синий, зеленый, красный, белый).
* **Умное именование:** Вам больше не нужно придумывать уникальные имена для каждого уведомителя. Интеграция автоматически формирует понятные названия карточек и `entity_id`, добавляя к базовому имени название чата и его `peer_id` (например: *VK Notify: Мой чат (2000012345)*).

---

## ⚙️ Обязательная настройка ВКонтакте

Для работы кнопок необходимо правильно настроить вашу группу (сообщество) в ВК:

### 1. Возможности ботов
Перейдите в: **Управление** > **Сообщения** > **Настройки для бота**
* **Возможности ботов:** Включены
* **Добавить кнопку «Начать»:** Включено (рекомендуется)
* **Разрешать добавлять сообщество в чаты:** По желанию

### 2. Настройка Long Poll API (Критически важно!)
Перейдите в: **Управление** > **Работа с API** > **Long Poll API** > **Типы событий**

В разделе **Сообщения** обязательно отметьте:
* [x] **Входящее сообщение** (для обработки текста и команд `/`)
* [x] **Исходящее сообщение** (для отслеживания статуса отправки)
* [x] **Действие с сообщением** — **ОБЯЗАТЕЛЬНО** для работы `callback`-кнопок. Без этой галочки нажатия на кнопки не будут приходить в Home Assistant!

---

## 📖 Примеры использования

### 1. Отправка пульта управления (Action)
Используйте этот код в любой автоматизации, чтобы отправить интерактивное меню с кнопками. Обратите внимание, что кнопки могут быть разных типов: `callback` (скрытая отправка данных) и `text` (отправка текста в чат).

<details>
  <summary><b>👨‍💻 Показать код YAML</b></summary>

```yaml
action: vk_notify.send_message
data:
  entity_id: notify.vk_notify_2000001234
  message: "Выберите устройство:"
  keyboard:
    inline: true
    buttons:
      - - action:
            type: callback
            label: "Свет: Гостиная 💡"
            payload: '{"action": "toggle", "item": "light.living_room"}'
          color: primary
        - action:
            type: callback
            label: "Все выключить 🌑"
            payload: '{"action": "all_off"}'
          color: negative
      - - action:
            type: text
            label: "/status"
          color: secondary
```

</details>

### 2. Продвинутая клавиатура (Цвета и ссылки)
Пример отправки сразу двух сообщений: одно с разноцветными кнопками, а второе — с кнопкой типа `open_link`, которая открывает нужный URL-адрес без отправки сообщений боту.

<details>
  <summary><b>👨‍💻 Показать код YAML</b></summary>

```yaml
alias: "Пульт управления светом и картой"
description: "Отправка сообщений с разными типами кнопок"
actions:
  - action: vk_notify.send_message
    data:
      entity_id: notify.vk_notify_2000001234
      message: "🎛 Пульт управления светом:"
      keyboard:
        inline: true
        buttons:
          - - action:
                type: callback
                label: "Переключить свет 💡"
                payload: '{"action": "toggle_light"}'
              color: primary
          - - action:
                type: callback
                label: "Включить всё ☀️"
                payload: '{"action": "all_on"}'
              color: positive
            - action:
                type: callback
                label: "Выключить всё 🌑"
                payload: '{"action": "all_off"}'
              color: negative
  - action: vk_notify.send_message
    data:
      entity_id: notify.vk_notify_2000001234
      message: "Нажми на кнопку, чтобы увидеть объект на карте:"
      keyboard:
        inline: true
        buttons:
          - - action:
                type: open_link
                link: "[https://yandex.ru/maps/?pt=37.62,55.75&z=15&l=map](https://yandex.ru/maps/?pt=37.62,55.75&z=15&l=map)"
                label: "Открыть карту 📍"
mode: single
```

</details>

### 3. Обработка нажатий (Trigger)
Эта автоматизация «слушает» невидимые нажатия `callback`-кнопок из примеров выше и выполняет действия в Home Assistant на основе данных из поля `payload`.

<details>
  <summary><b>👨‍💻 Показать код YAML</b></summary>

```yaml
alias: "VK: Обработка кнопок пульта"
description: "Реагирует на нажатия callback-кнопок из ВК"
triggers:
  - trigger: event
    event_type: vk_notify_callback
    event_data:
      peer_id: 2000001234  # <--- Фильтр: реагировать только на нажатия в этом чате
actions:
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.payload.action == 'toggle_light' }}"
        sequence:
          - action: light.toggle
            target:
              entity_id: light.double_switch_2_2_3
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.payload.action == 'all_off' }}"
        sequence:
          - action: light.turn_off
            target:
              entity_id: all
mode: parallel
```

</details>

### 4. Реакция на текстовые команды
Если вы нажали кнопку типа `text` или просто написали в чат сообщение со слэшем (например, `/status`), Home Assistant сгенерирует событие `vk_notify_command`. Вот как на него ответить:

<details>
  <summary><b>👨‍💻 Показать код YAML</b></summary>

```yaml
alias: "VK: Реакция на текстовые команды"
description: "Отвечает на команду /status"
triggers:
  - trigger: event
    event_type: vk_notify_command
    event_data:
      command: status  # <--- Указываем команду без слэша
      peer_id: 2000001234
actions:
  - action: vk_notify.send_message
    data:
      entity_id: notify.vk_notify_2000001234
      message: "🟢 Все системы работают в штатном режиме!"
mode: single
```

</details>

### 5. Умный пульт (Единая автоматизация с динамическим обновлением)
Эта мощная автоматизация объединяет всё: она отправляет пульт по команде `/пульт`, а при нажатии на кнопку — переключает свет и **редактирует само сообщение**, меняя цвет кнопки (зеленый/красный) в зависимости от текущего статуса устройства.

<details>
  <summary><b>👨‍💻 Показать код YAML</b></summary>

```yaml
alias: "VK: Умный пульт (Единая автоматизация)"
description: "Вызов пульта и динамическое обновление кнопок в одном месте"
mode: parallel
max: 10
triggers:
  # Триггер 1: Пользователь написал /пульт
  - trigger: event
    event_type: vk_notify_command
    event_data:
      command: пульт
      peer_id: 2000001234
    id: call_remote

  # Триггер 2: Пользователь нажал невидимую кнопку callback
  - trigger: event
    event_type: vk_notify_callback
    event_data:
      peer_id: 2000001234
    id: button_pressed

actions:
  - choose:
      # ВЕТКА 1: Отправка нового пульта в чат
      - conditions:
          - condition: trigger
            id: call_remote
        sequence:
          - action: vk_notify.send_message
            data:
              entity_id: notify.vk_notify_2000001234
              message: "🎛 **Главный пульт управления**"
              keyboard:
                inline: true
                buttons:
                  - - action:
                        type: callback
                        label: >-
                          {% if is_state('light.double_switch_2_2_3', 'on') %}Выключить свет 🌑
                          {% else %}Включить свет 💡{% endif %}
                        payload: '{"action": "toggle_light"}'
                      color: >-
                        {% if is_state('light.double_switch_2_2_3', 'on') %}negative
                        {% else %}positive{% endif %}

      # ВЕТКА 2: Обработка нажатий и обновление сообщения
      - conditions:
          - condition: trigger
            id: button_pressed
        sequence:
          - choose:
              - conditions:
                  - condition: template
                    value_template: "{{ trigger.event.data.payload.action == 'toggle_light' }}"
                sequence:
                  # 1. Переключаем свет
                  - action: light.toggle
                    target:
                      entity_id: light.double_switch_2_2_3
                  
                  # 2. Ждем секунду для обновления статуса в HA
                  - delay: "00:00:01"
                  
                  # 3. Редактируем сообщение (меняем цвет и текст)
                  - action: vk_notify.edit_message
                    data:
                      entity_id: notify.vk_notify_2000001234
                      conversation_message_id: "{{ trigger.event.data.conversation_message_id }}"
                      message: "🎛 **Главный пульт управления**"
                      keyboard:
                        inline: true
                        buttons:
                          - - action:
                                type: callback
                                label: >-
                                  {% if is_state('light.double_switch_2_2_3', 'on') %}Выключить свет 🌑
                                  {% else %}Включить свет 💡{% endif %}
                                payload: '{"action": "toggle_light"}'
                              color: >-
                                {% if is_state('light.double_switch_2_2_3', 'on') %}negative
                                {% else %}positive{% endif %}
```

</details>

### 6. Удаление сообщения по кнопке (Закрыть пульт)
Пример того, как можно добавить на пульт кнопку "Закрыть ❌", которая будет физически удалять сообщение из истории чата.

<details>
  <summary><b>👨‍💻 Показать код YAML</b></summary>

```yaml
alias: "VK: Закрытие пульта"
description: "Удаляет сообщение с пультом при нажатии на кнопку закрытия"
triggers:
  - trigger: event
    event_type: vk_notify_callback
    event_data:
      peer_id: 2000001234
actions:
  - choose:
      - conditions:
          - condition: template
            # Предполагается, что на пульте есть кнопка с payload: '{"action": "close_remote"}'
            value_template: "{{ trigger.event.data.payload.action == 'close_remote' }}"
        sequence:
          - action: vk_notify.delete_message
            data:
              entity_id: notify.vk_notify_2000001234
              # Берем ID сообщения прямо из клика по кнопке
              conversation_message_id: "{{ trigger.event.data.conversation_message_id }}"
```

</details>

### 7. Самоуничтожающиеся сообщения (Таймер)
Интеграция автоматически сохраняет внутренний ID последнего отправленного сообщения в атрибут `last_message_id`. Это позволяет создавать сообщения, которые удаляются сами через заданное время, чтобы не засорять чат.

<details>
  <summary><b>👨‍💻 Показать код YAML</b></summary>

```yaml
alias: "VK: Уведомление с таймером"
description: "Отправляет статус и удаляет его через час"
actions:
  # 1. Отправляем сообщение
  - action: vk_notify.send_message
    data:
      entity_id: notify.vk_notify_2000001234
      message: "👕 Стиральная машина закончила стирку!"
      
  # 2. Ждем 1 час
  - delay: "01:00:00"
  
  # 3. Удаляем именно то сообщение, которое отправили час назад
  - action: vk_notify.delete_message
    data:
      entity_id: notify.vk_notify_2000001234
      # Берем внутренний ID последнего отправленного сообщения из атрибутов
      message_id: "{{ state_attr('notify.vk_notify_2000001234', 'last_message_id') }}"
```

</details>

## Новые возможности начиная с версии v1.0.2

<details>
  <summary><b>📖 Как использовать новые функции в YAML (начиная с версии v1.0.2)</b></summary>
  

#### 1. Имитация бурной деятельности («Бот печатает...»)
Отлично подходит для скриптов, которые парсят данные или ждут ответа от железки (например, твоего ИБП). Бот будет показывать статус активности в течение 10 секунд.

```yaml
action: vk_notify.set_activity
data:
  entity_id: notify.vk_notify_2000001234
  type: typing # или 'audiomsg', если бот "записывает голосовое"
```

#### 2. Реакции (Лайки) на сообщения
Чтобы бот не засорял чат ответами "ОК, выключил", он может просто поставить лайк на твою команду. 
*(Коды реакций VK: 1 = 👍, 2 = 👎, 3 = ❤️, 4 = 🔥 и т.д.)*

```yaml
action: vk_notify.send_reaction
data:
  entity_id: notify.vk_notify_2000001234
  conversation_message_id: "{{ trigger.event.data.conversation_message_id }}" # ID твоего сообщения из триггера
  reaction_id: 1 # Ставим лайк 👍
```

#### 3. Геометки (Отправка координат)
Бот пришлет интерактивную карту прямо в чат.

```yaml
action: vk_notify.send_message
data:
  entity_id: notify.vk_notify_2000001234
  message: "📍 Автомобиль припаркован здесь:"
  lat: "55.751244"
  long: "37.618423"
```

#### 4. Карусель (Шаблоны)
Отправка красивых горизонтальных карточек. В нашем случае, мы добавили поддержку ключа `template` в стандартную службу `send_message`.

```yaml
action: vk_notify.send_message
data:
  entity_id: notify.vk_notify_2000001234 # Укажи свой ID
  message: "💡 Выберите сценарий освещения для гостиной:"
  template:
    type: carousel
    elements:
      # Карточка 1
      - title: "Вечерний отдых 🌙"
        description: "Приглушенный теплый свет (30%)"
        buttons:
          - action:
              type: callback
              label: "Включить"
              payload: '{"action": "set_scene", "scene": "evening"}'
            color: primary # Синяя кнопка
      
      # Карточка 2
      - title: "Яркий свет ☀️"
        description: "Максимальная яркость (100%)"
        buttons:
          - action:
              type: callback
              label: "Включить"
              payload: '{"action": "set_scene", "scene": "bright"}'
            color: positive # Зеленая кнопка
      
      # Карточка 3
      - title: "Режим кино 🍿"
        description: "Выключить основной свет, оставить подсветку ТВ"
        buttons:
          - action:
              type: callback
              label: "Включить"
              payload: '{"action": "set_scene", "scene": "movie"}'
            color: secondary # Серая кнопка
```

```yaml
action: vk_notify.send_message
data:
  entity_id: notify.vk_notify_2000001234
  message: "🎬 Выберите фильм для просмотра:"
  template:
    type: carousel
    elements:
      - title: "Интерстеллар"
        description: "Фантастика, 2014"
        photo_id: "-123456_7890" # Нужно заранее загрузить фото в ВК
        buttons:
          - action:
              type: callback
              label: "▶️ Включить на Plex"
              payload: '{"action": "play_movie", "id": "1"}'
      - title: "Дюна"
        description: "Фантастика, 2021"
        buttons:
          - action:
              type: callback
              label: "▶️ Включить на Plex"
              payload: '{"action": "play_movie", "id": "2"}'
```

#### 5. Закрепление сообщения
Например, можно отправить главное меню с кнопками и сразу прибить его гвоздями к верху чата.

```yaml
# Сначала отправляем сообщение и получаем ответ
- action: vk_notify.send_message
  data:
    entity_id: notify.vk_notify_2000001234
    message: "🎛 Главный пульт управления домом"
    # ... тут твоя клавиатура ...
  response_variable: msg_response

# Затем закрепляем это сообщение
- action: vk_notify.pin_message
  data:
    entity_id: notify.vk_notify_2000001234
    conversation_message_id: "{{ (msg_response.values() | first).conversation_message_id }}"
```

#### 6. Голосовые сообщения
Добавлена отдельная служба `send_voice`. Передай ей локальный путь к файлу `.ogg`.

```yaml
action: vk_notify.send_voice
data:
  entity_id: notify.vk_notify_2000001234
  file: "/config/www/audio/alarm.ogg"
```
*(Небольшая ремарка по аудио: чтобы оно отображалось именно как «волна», а не как прикрепленный файл-документ, твой файл `helpers.py` должен уметь запрашивать у ВКонтакте сервер для загрузки именно голосовых сообщений `docs.getMessagesUploadServer?type=audio_message`. Если он этого не умеет, ВК всё равно примет файл, но покажет его просто как аудио-документ).*

</details>

---

## 🛠 Установка


### Через HACS

[![Открыть в Home Assistant и установить VK Notify через HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Eugen417&repository=ha_vk_notify_keyboard_callback&category=integration)

Если кнопка не работает: добавьте репозиторий в HACS вручную (категория: Интеграция), установите "VK Notify (Keyboard Edition)" и перезапустите Home Assistant.

### Вручную (без HACS)

1. Откройте **HACS** > **Integrations**.
2. Нажмите три точки в верхнем правом углу > **Custom repositories**.
3. Вставьте ссылку на ваш репозиторий: `https://github.com/Eugen417/ha_vk_notify_keyboard_callback`
4. Выберите категорию **Integration** и нажмите **Add**.
5. Установите появившуюся интеграцию **VK Notify (Keyboard Edition)**.
6. Перезагрузите Home Assistant.

---

<details>
  <summary><b>🖼 Скриншоты установки и настройки (Нажмите, чтобы развернуть)</b></summary>
  <br>
  <img width="584" height="722" alt="Снимок экрана 2026-04-08 в 10 24 57" src="https://github.com/user-attachments/assets/3b427935-f55f-4a38-b312-996a3b6fa1e2" />

<img width="882" height="798" alt="Снимок экрана 2026-04-08 в 10 29 28" src="https://github.com/user-attachments/assets/5f5f5ad6-a9e8-42df-97f0-8333c94df659" />

<img width="882" height="798" alt="Снимок экрана 2026-04-08 в 10 30 40" src="https://github.com/user-attachments/assets/8fc155a5-cc20-48b6-91ec-89013a3e995a" />

<img width="1011" height="840" alt="Снимок экрана 2026-04-08 в 10 27 48" src="https://github.com/user-attachments/assets/288f2258-0669-43e5-bd22-00ae36a9dcfa" />

<img width="582" height="294" alt="Снимок экрана 2026-04-08 в 16 18 00" src="https://github.com/user-attachments/assets/e77dce74-d6d8-4979-9734-74d14952a1c7" />

<img width="582" height="294" alt="Снимок экрана 2026-04-08 в 16 17 52" src="https://github.com/user-attachments/assets/4365b34d-f3d4-4761-9469-efa8d51b0f1c" />

https://github.com/user-attachments/assets/e257553f-e171-4935-a5c5-afb8dddb018f


</details>
