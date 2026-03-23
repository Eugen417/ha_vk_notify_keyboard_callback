# VK Notify

Интеграция для Home Assistant, для отправки уведомлений в VK.

Подробная иструкция по установке и настройке на сайте [uDocs](https://udocs.ru/posts/home-assistant/integrations/otpravka-uvedomleniy-v-vk)

## Требования

- Сообщество ВКонтакте с включёнными сообщениями
- Токен API сообщества с правами `messages` и `photos` (если нужна отправка фото)

## Установка

### Через HACS

1. Добавьте этот репозиторий как пользовательский репозиторий в HACS (категория: Интеграция)
2. Установите "VK Notify"
3. Перезапустите Home Assistant

### Вручную

1. Скопируйте папку `custom_components/vk_notify/` в директорию `config/custom_components/` вашего HA
2. Перезапустите Home Assistant

## Настройка

1. Перейдите в **Настройки → Устройства и службы → Добавить интеграцию**
2. Найдите **VK Notify**
3. Заполните поля:
   - **Токен доступа** — токен бота сообщества ВКонтакте
   - **Peer ID** — получатель:
     - Пользователь: его VK ID (например, `12345678`)
     - Групповая беседа: `2000000000 + ID беседы` (например, `2000000001`)
   - **Название** — отображаемое имя уведомителя (по умолчанию: `VK Notify`)

## Использование

### Отправка текстового сообщения

Сервис `notify.send_message`:

```yaml
action: notify.send_message
target:
  entity_id: notify.vk_notify
data:
  message: "Привет из Home Assistant!"
  title: "Оповещение" # необязательно
```

### Отправка фото

Сервис `vk_notify.send_photo`:

```yaml
action: vk_notify.send_photo
data:
  entity_id: notify.vk_notify
  url: "https://example.com/photo.jpg"
  message: "Подпись к фото" # необязательно
```

Или с локальным файлом (путь должен быть добавлен в `allowlist_external_dirs`):

```yaml
action: vk_notify.send_photo
data:
  entity_id: notify.vk_notify
  file: "/config/www/photo.jpg"
  message: "Подпись к фото"
```

### Использование в автоматизации

```yaml
action:
  - action: notify.send_message
    target:
      entity_id: notify.vk_notify
    data:
      message: "Входная дверь открыта"
```

## Получение токена сообщества ВКонтакте

1. Откройте управление сообществом → **Управление → Работа с API → Ключи доступа**
2. Создайте ключ с правами:
   - **Сообщения** — для отправки текстовых уведомлений
   - **Фотографии** — для отправки фото
3. В настройках сообщества включите **Разрешить отправку сообщений**
