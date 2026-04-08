# VK Notify (Keyboard Edition) ⌨️

Форк оригинальной интеграции `ha_vk_notify` с добавленной поддержкой интерактивных клавиатур и callback-кнопок. Эта версия позволяет управлять вашим домом через ВКонтакте в «тихом» режиме, не засоряя чат текстовыми командами.

---

## 🚀 Что нового в этой версии

* **Действие `vk_notify.send_message`**: Расширенный сервис для отправки сообщений с поддержкой JSON-клавиатур.
* **Callback-кнопки**: Кнопки, которые при нажатии не отправляют текст в чат, а генерируют скрытое событие внутри Home Assistant.
* **Инлайн-клавиатуры**: Кнопки, которые прикрепляются прямо к сообщению, а не висят под полем ввода.
* **Цветные кнопки**: Поддержка всех 4-х стандартных цветов VK (синий, зеленый, красный, белый).
* **Название сущностей**: Можно больше не присваивать, так как к названию добавляется пир (VK Notify: Мой чат(2000012345)).

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
Используйте этот код в любой автоматизации, чтобы отправить интерактивное меню.

```yaml
action: vk_notify.send_message
data:
  entity_id: notify.vk_notify
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

### 2. Обработка нажатий (Trigger)
Эта автоматизация «слушает» нажатия callback-кнопок и выполняет действия на основе данных из `payload`.

```yaml
alias: "Пульт управления светом:"
description: ""
triggers: []
conditions: []
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
                label: Переключить свет 💡
                payload: "{\"action\": \"toggle_light\"}"
              color: primary
          - - action:
                type: callback
                label: Включить всё ☀️
                payload: "{\"action\": \"all_on\"}"
              color: positive
            - action:
                type: callback
                label: Выключить всё 🌑
                payload: "{\"action\": \"all_off\"}"
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
                link: https://yandex.ru/maps/?pt=37.62,55.75&z=15&l=map
                label: Открыть карту 📍
mode: single

```

### 3. Реакция на текстовые команды
Если вы нажали кнопку типа `text` или написали сообщение со слэшем (например, `/start`).

```yaml
alias: "VK: Обработка кнопок пульта"
description: Реагирует на нажатия callback-кнопок из ВК
triggers:
  - trigger: event
    event_type: vk_notify_callback
    event_data:
      peer_id: 2000001234  # <--- Добавляем фильтр сюда
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

---

## 🛠 Установка через HACS


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

<img width="584" height="722" alt="Снимок экрана 2026-04-08 в 10 24 57" src="https://github.com/user-attachments/assets/3b427935-f55f-4a38-b312-996a3b6fa1e2" />


<img width="882" height="798" alt="Снимок экрана 2026-04-08 в 10 29 28" src="https://github.com/user-attachments/assets/5f5f5ad6-a9e8-42df-97f0-8333c94df659" />

<img width="882" height="798" alt="Снимок экрана 2026-04-08 в 10 30 40" src="https://github.com/user-attachments/assets/8fc155a5-cc20-48b6-91ec-89013a3e995a" />

<img width="1011" height="840" alt="Снимок экрана 2026-04-08 в 10 27 48" src="https://github.com/user-attachments/assets/288f2258-0669-43e5-bd22-00ae36a9dcfa" />

