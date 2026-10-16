# Bu Replik Kime Ait?

## Kurulum

1. `python -m venv .venv`
2. Windows: `.venv\Scripts\activate` — macOS/Linux: `source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. `.env.example` dosyasını `.env` olarak kopyala ve üç anahtarı doldur.
5. `uvicorn backend.main:app --reload`
6. Chrome'da `http://localhost:8000` adresini aç.
