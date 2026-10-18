# Bu Replik Kime Ait?

İki mod: **Find the line** (sesli arama) ve **Guess the line** (çikolata/ödül oyunu).

## Kurulum

1. `python3 -m venv .venv`
2. macOS/Linux: `source .venv/bin/activate` — Windows: `.venv\Scripts\activate`
3. `pip install -r requirements.txt`
4. `.env.example` dosyasını `.env` olarak kopyala ve üç anahtarı doldur.
5. `uvicorn backend.main:app --reload`
6. Chrome'da `http://localhost:8000` adresini aç.

## Oyun ayarları

`backend/game.py` başında: `TOTAL` (soru sayısı), `WIN_SCORE` (ödül için doğru sayısı), `SECONDS` (soru başına süre).
Replikler ve şıklar `backend/game_data.py` içinde. Yeni replik eklemek için `LINES` listesine bir satır ekle.

## Güvenlik ve canlıya alma

- Açılışta üç API anahtarı kontrol edilir; biri eksikse sunucu hangisinin eksik olduğunu yazıp başlamaz.
- `/api/guess` ve `/api/transcribe` IP başına dakikada 30, diğer uçlar 240 istekle sınırlıdır (`.env` ile değişir).
- İstek gövdesi en fazla 3 MB. Metin alanlarının uzunluk sınırı var.
- Tüm yanıtlarda güvenlik başlıkları (CSP, X-Frame-Options vb.) bulunur. Hata detayları kullanıcıya gösterilmez, JSON olarak loglanır; anahtarlar loglarda maskelenir. Ses ve konuşma metni loglanmaz.
- `GET /health`: anahtarları ve SQLite cache'i kontrol eder, sorun varsa 503 döner.
- Proxy (Nginx, Cloudflare vb.) arkasında çalışıyorsan `.env` içine `TRUST_PROXY=1` yaz, yoksa tüm ziyaretçiler tek IP gibi görünür.

### Test
```
pip install -r requirements-dev.txt
python -m pytest -q tests
```

### Vercel
1. Projeyi GitHub'a push et, Vercel'de "Add New → Project" ile repoyu içe aktar. Framework otomatik FastAPI olarak algılanır (`pyproject.toml` giriş noktasını gösterir).
2. Project Settings → Environment Variables bölümüne `GEMINI_API_KEY`, `TAVILY_API_KEY`, `TMDB_API_KEY` ekle (Production için).
3. Deploy et. `https://<proje>.vercel.app/health` adresi `{"status":"ok"}` dönmeli.
4. Hatalı sürümde: Deployments → önceki deployment → Instant Rollback / Promote to Production.

Vercel'de dosya sistemi salt okunurdur, bu yüzden cache `/tmp` içine yazılır ve her örnekte sıfırlanabilir (sadece hız içindir). Hız sınırı bellek içidir ve her örnekte ayrı sayılır; ek koruma için Vercel Firewall kullanılabilir.

### Docker (isteğe bağlı)
```
docker build -t whose-line .
docker run -p 8000:8000 --env-file .env whose-line
```

## Event day limits

Defaults assume billing is enabled on the Gemini project. Set them as environment variables in Vercel.

| Variable | Default | Meaning |
|---|---|---|
| `RATE_LIMIT_HEAVY` | 120 | Voice and search requests per IP per minute |
| `SEARCH_PER_IP_DAY` | 150 | New web searches per IP per day |
| `SEARCH_TOTAL_DAY` | 400 | New web searches per day, all visitors |
| `VOICE_PER_IP_DAY` | 200 | Voice requests per IP per day |
| `VOICE_TOTAL_DAY` | 800 | Voice requests per day, all visitors |

Counters are kept per server instance on Vercel, so totals are approximate. Set a budget alert in Google Cloud and watch Tavily credits.
