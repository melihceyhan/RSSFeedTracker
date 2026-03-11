# RSS Feed Tracker

RSS feedlerden haber çekip AI ile özetleyip Telegram'a gönderen sistem.

## Kurulum

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # .env dosyasını düzenleyin
```

## Yapılandırma

`.env` dosyasındaki ayarları düzenleyin veya Web UI'daki Ayarlar sayfasından yapılandırın:

- **AI_PROVIDER**: `ollama` veya `openai`
- **AI_MODEL**: Kullanılacak model adı (örn. `qwen2.5:7b`, `gpt-4o-mini`)
- **TELEGRAM_BOT_TOKEN**: Telegram BotFather'dan alınan token
- **TELEGRAM_CHAT_ID**: Mesajların gönderileceği chat/grup ID
- **FETCH_INTERVAL_MINUTES**: Haberlerin çekilme aralığı (varsayılan: 60 dakika)

## Çalıştırma

```bash
python run.py
```

Web UI: http://localhost:8000

## Özellikler

- RSS/Atom feed desteği
- Ollama (QWEN, Llama vb.) ve OpenAI ile AI özetleme
- Saat başı otomatik fetch + özetleme + Telegram gönderim
- Günlük otomatik veri temizliği (eski günlerin verileri silinir)
- Web dashboard ile feed yönetimi ve izleme
- Manuel tetikleme ("Şimdi Çalıştır") desteği
