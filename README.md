<div align="center">

# 🎬 DVD Koleksiyonum

**Letterboxd günlüğümden beslenen kişisel film arşivim**

[![Siteyi aç](https://img.shields.io/badge/Siteyi_aç-brensvenka.github.io%2FDVD__Archive-845331?style=for-the-badge)](https://brensvenka.github.io/DVD_Archive/)
[![Letterboxd](https://img.shields.io/badge/Letterboxd-brensvenka-202830?style=for-the-badge&logo=letterboxd&logoColor=white)](https://letterboxd.com/brensvenka/)

![Filmler](https://img.shields.io/badge/film-597-ad7a4b?style=flat-square)
![İncelemeler](https://img.shields.io/badge/inceleme-102-ad7a4b?style=flat-square)
![Dönem](https://img.shields.io/badge/2024–2026-c4ae8d?style=flat-square)
![HTML](https://img.shields.io/badge/HTML%20%2B%20vanilla%20JS-21160f?style=flat-square)

</div>

---

## Nedir?

İzlediğim her filmi ahşap raflı bir DVD dolabı gibi gezilebilen tek sayfalık bir sitede topladım. Veriler Letterboxd'dan alınıyor; afişler, puanlarım, izleme tarihlerim ve yazdığım incelemeler bir arada duruyor.

## Özellikler

| | |
|---|---|
| 🗂️ **Koleksiyonlar** | Tüm filmler, ★ Favoriler, Son izlediklerim ve yıllara göre raflar |
| ↕️ **Sıralama** | Son izlenen, en yüksek / en düşük puan, A–Z, IMDb puanı |
| 🎞️ **Film kartı** | Afişe tıklayınca yönetmen, yıl, puan, izleme tarihleri ve incelemem |
| 📄 **Sayfalama** | Önceki / sonraki ve doğrudan sayfaya atlama |
| 📱 **Mobil uyumlu** | Telefonda da rahat gezilir |

## Dosyalar

```
DVD_Archive/
├── index.html      # Sayfa, stiller ve tüm arayüz kodu
└── films-data.js   # Letterboxd'dan çıkarılan film verisi (597 film)
```

Derleme adımı, sunucu ya da bağımlılık yok. Bilgisayarda denemek için `index.html` dosyasını tarayıcıda açmak yeterli.

## Otomatik güncelleme

Bir GitHub Actions görevi her sabah 06:17'de (Türkiye saati) Letterboxd RSS akışımı okur. Yeni izlediğim filmleri, puanları ve incelemeleri `films-data.js` dosyasına ekler, sonra siteyi yeniden yayınlar. Sayfanın altındaki "Letterboxd eşitlendi" tarihi son çalışmayı gösterir.

Görevi beklemeden çalıştırmak için **Actions → Letterboxd günlük güncelleme → Run workflow** yolunu izleyin.

```
├── update_films.py                     # RSS'i okuyup veriyi güncelleyen betik
└── .github/workflows/letterboxd.yml    # Günlük zamanlayıcı
```

---

<div align="center">
<sub>Film verileri ve afişler <a href="https://letterboxd.com">Letterboxd</a>'a aittir. · GitHub Pages ile yayınlanıyor.</sub>
</div>
