# PythonMagic-Solver

Yazar: PythonMagic

Cloudflare Turnstile, cf_clearance, Google reCAPTCHA v3 ve AWS WAF Token çözmek icin
yazılmıs bir REST API servisi. FastAPI ve Camoufox (gizlilik odaklı Firefox) üzerinde
çalısıyor, tamamı asenkron olarak isliyor.

> Durum: Çalışıyor. Projeyi düzenli aralıklarla test ediyorum ve üzerinde hala calışıyorum.

Biraz da benzer isleri yapan bircok acık kaynak projeden ilham aldım, ama kodu
bastan yazarak kendine ozgu bir hale getirdim.

---

## Özellikler

- 4 adet çözücü endpoint: `/turnstile`, `/clearance`, `/aws-token`, `/recaptchaV3`
- Ek çözücüler: `/recaptchaV2` ve `/hcaptcha` (yeni)
- reCAPTCHA v2 checkbox ve görsel bulmaca, model ONNX ile lokal çözülüyor
- hCaptcha checkbox ve invisible modlari desteklenir
- İlk calistirmada otomatikkurulum (Python paketleri ve Camoufox tarayıcı verisi)
- `config.json` uzerinden yapılandırma, dosyadan yada interaktif menuden yapılabilir
- Proxy desteği, round-robin rotasyon ile her tarayıcıya farklı bir proxy atanır
- Dusuk RAM li VPS ler icin zorunlu periyodik bellek temizliği yapar
- Headless ve GUI modu (terminal / VPS icin xvfb, masaustu icin normal mod)

---

## Kurulum

Yeni bir VPS te ilk kurulum sırasında takılırsanız genelde sorun tarayıcı cache
verisinin eksik olmasından kaynaklanır. Aşağıdaki adımları sırayla uekfailmanız
yeterli olucaktir.

Önerilen adımlar (Ubuntu / Debian):

```bash
# 1. Sistemi guncelle ve tarayıcı sistem bagımlılıklarını kur
sudo apt update -y && sudo apt upgrade -y
sudo apt install xvfb -y
sudo apt install libasound2 -y
sudo apt install python3 python3-pip python3-venv -y

# 2. Proje dosyalarını indirin ve klasore girin
cd PythonMagic-Solver

# 3. Sanal ortam olustur (kesinlikle tavsiye ederim)
python3 -m venv venv
source venv/bin/activate

# 4. Python bagımlılıklarını kur
pip install fastapi==0.95.2 uvicorn "camoufox[fetch]" loguru psutil playwright onnxruntime numpy pillow

# 5. Camoufox verisni birkez indir ve tarayıcı eksiklerini tamamla
python3 -m camoufox fetch
python3 -m playwright install-deps

# 6. Servisi baslat
python3 api_server.py
```

> GUI modunda calistrırsanız (headless=false) ve VPS te ekra yoksa xvfb-run ile
> baslatmalısınız:
>
> ```bash
> source venv/bin/activate
> xvfb-run -a python3 api_server.py
> ```

---

## Yapılandırma (config.json)

İlk calistirmada script config.json dosyasına bakar, yoksa varsayılan degerlerle
devam eder. Dosyayı istediğiniz gibi duzenleyebilirsiniz:

```json
{
    "headless":      true,
    "thread":        2,
    "page_count":    1,
    "proxy_support": false,
    "proxy_file":    "proxies.txt",
    "host":          "0.0.0.0",
    "port":          8001,
    "debug":         false,
    "cleanup_interval_minutes": 10
}
```

| Parametre | Tip | Varsayılan | Açıklama |
|---|---|---|---|
| `headless` | bool | `true` | Tarayıcı ekransuz calisir |
| `thread` | int | `2` | Tarayıcı instance sayısı (en fazla CPU cekirdegi kadar) |
| `page_count` | int | `1` | Her tarayıcıda acilacak sekme sayısı |
| `proxy_support` | bool | `false` | `proxies.txt` icindeki proxy listesini kullanir |
| `cleanup_interval_minutes` | int | `10` | Bellek temizligi icin gecen sure (dakika) |

## Proxy Formatı (proxies.txt)

`proxy_support` acıksa `proxies.txt` dosyasına her satıra bir proxy yazın.
Desteklenen formatlar sunlar:

```text
http://ip:port
http://user:pass@ip:port
socks5://user:pass@ip:port
```

---

## API Kullanımı

Çözücü asenkron çalışır. Önce görevi olusturup `task_id` alırsınız, ardından sonucu
almak icin `/result` endpointini poll edersiniz.

### 1. Gorev Olusturma Endpointleri

| Gorev | Endpoint | Gerekli Parametreler |
|---|---|---|
| Turnstile | `GET /turnstile` | `url`, `sitekey` |
| cf_clearance | `GET /clearance` | `url`, `timeout` (opsiyonel, saniye) |
| AWS WAF | `GET /aws-token` | `url`, `timeout` (opsiyonel, saniye) |
| reCAPTCHA v3 | `GET` veya `POST` `/recaptchaV3` | `url`, `sitekey`, `action` (opsiyonel, varsayılan `submit`) |
| reCAPTCHA v2 | `GET` veya `POST` `/recaptchaV2` | `url`, `sitekey`, `version` (opsiyonel), `enterprise` (opsiyonel boolean), `classifier` (opsiyonel) |
| hCaptcha | `GET` veya `POST` `/hcaptcha` | `url`, `sitekey`, `version` (opsiyonel, cookie `checkbox` yada `invisible`) |

#### Ornek cURL istekleri

Turnstile:

```bash
curl -X GET "http://127.0.0.1:8001/turnstile?url=https://ornek.com/&sitekey=0x4AAAAAxxxxxxxxxxxx"
```

cf_clearance:

```bash
curl -X GET "http://127.0.0.1:8001/clearance?url=https://ornek.com/&timeout=30"
```

AWS WAF:

```bash
curl -X GET "http://127.0.0.1:8001/aws-token?url=https://ornek.com/&timeout=30"
```

reCAPTCHA v3 (GET):

```bash
curl -X GET "http://127.0.0.1:8001/recaptchaV3?url=https://ornek.com&sitekey=6Ldqxxxxxxxxxxxx&action=submit"
```

reCAPTCHA v3 (POST):

```bash
curl -X POST "http://127.0.0.1:8001/recaptchaV3" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://ornek.com", "sitekey": "6Ldqxxxxxxxxxxxx", "action": "submit"}'
```

reCAPTCHA v2 (checkbox, gorsel bulmaca ONNX ile cozulebilir):

```bash
curl -X GET "http://127.0.0.1:8001/recaptchaV2?url=https://ornek.com/&sitekey=6Ldqxxxxxxxxxxxx"
```

reCAPTCHA v2 invisible (Enterprise sitekey icin `enterprise=true`):

```bash
curl -X GET "http://127.0.0.1:8001/recaptchaV2?url=https://ornek.com/&sitekey=6Ldqxxxxxxxxxxxx&version=invisible&action=submit"
```

hCaptcha (checkbox):

```bash
curl -X GET "http://127.0.0.1:8001/hcaptcha?url=https://ornek.com/&sitekey=345e6d03-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

hCaptcha (invisible):

```bash
curl -X GET "http://127.0.0.1:8001/hcaptcha?url=https://ornek.com/&sitekey=345e6d03-xxxx-xxxx-xxxx-xxxxxxxxxxxx&version=invisible"
```

Başarılı görev olusturma cevabı (202):

```json
{
  "task_id": "8a31e3d4-b41e-450f-a63c-94cc8193eb41",
  "status": "accepted"
}
```

### 2. Sonuc Sorgulama (`GET /result?id=<task_id>`)

Yukarıda aldıgınız `task_id` ile bu endpointi poll etmeniz gerekiyor. Status
`success` veya `error` olana kadar devam edin, aralık olarak 1 saniye öneririm.

```bash
curl -X GET "http://127.0.0.1:8001/result?id=8a31e3d4-b41e-450f-a63c-94cc8193eb41"
```

Turnstile / reCAPTCHA v3 başarılı cevabı:

```json
{
  "status": "success",
  "elapsed_time": 2.431,
  "value": "0.AbCdEf..."
}
```

cf_clearance / AWS WAF başarılı cevabı:

```json
{
  "status": "success",
  "elapsed_time": 3.102,
  "user_agent": "Mozilla/5.0 ...",
  "cookies": "cf_clearance=abcdef...;",
  "cf_clearance": "abcdef..."
}
```

HTTP durum kodları:

- `200` = Başarılı.
- `202` = Hala isleniyor, `/result` endpointini poll etmeye davam edin.
- `404` = Task id gecersiz veya suresi dolmus.
- `408` = Zaman asımı (5 dakikadan fazla surdu).
- `500` / `422` = Dahili hata veya captcha cozulemedi.

---

## Notlar

- Her istemci isteği ayri bir gorev olarak kuyruga alınır, bu yuzden aynı anda birden
  fazla istek gönderebilirsiniz.
- Proje yalnızca egitim ve test iyindir. Kullanırken hedef sitenin kullanım
  şartlarına dikkat edin, cunku boyle aracılar bazi platformlar tarafından yasaklıdır.
- reCAPTCHA v2 gorsel bulmacası icin `models/recaptcha_cls_s.onnx` dosyasının
  mevcut olması gerek. Dosya yoksa checkbox yine calisir ama bulmaca otomatik
  cozulemez. Model 14 sinif (bisiklet, otobus, araba vb) icin egitimlidir.
- hCaptcha'nın gorsel bulmaca (image challange) tarafı bir VZY goruntur modeli
  gerektirdigi icin varsayılan olarak atlanır; checkbox ve invisible modlar calisir.
- Aklınıza takılan bir caslik olursa issue acmaktan cekinmeyin.

## Lisans

MIT License - Detaylar icin [LICENSE](LICENSE) dosyasına bakabilirsiniz.