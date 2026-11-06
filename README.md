# Rəqəmsal iqtisadiyyat üzrə vergitutma — interaktiv naviqator

Sayt **taxes.gov.az** səhifəsini avtomatik izləyir:
<https://www.taxes.gov.az/az/page/reqemsal-iqtisadiyyat-uzre-vergitutma>

GitHub hər saat rəsmi səhifəni yoxlayır. Orada nəsə dəyişsə (yeni şirkət, sual-cavab mətni, hədd, ƏDV dərəcəsi, tarix, link), sayt özü yenilənir. Sizdən heç nə tələb olunmur.

| Rəsmi səhifədə dəyişiklik | Saytda nə baş verir |
|---|---|
| Reyestrə yeni şirkət əlavə olunub, çıxarılıb və ya dəyişib | Reyestr, qrafiklər, göstəricilər, axtarış yenilənir |
| Sual-cavab mətni dəyişib və ya yeni sual əlavə olunub | Həmin sual rəsmi mətnlə göstərilir (dəyişməyənlər saytdakı qısa variantda qalır) |
| Dövriyyə həddi, ƏDV dərəcəsi, məcburi uçot tarixi, müddətlər, valyutalar | Kalkulyator, yoxlayıcı, təqvim və bütün mətnlər yeni rəqəmlə yenilənir |
| E-poçt, platforma linki, ödəniş təlimatı (PDF) | Saytdakı linklər yenilənir |
| Səhifədə istənilən başqa dəyişiklik | Sizə bildiriş gəlir (GitHub → Issues, adətən e-poçtla da) |

## Bir dəfəlik quraşdırma (təxminən 10 dəqiqə, pulsuz)

1. **github.com** saytında hesab açın (hesabınız varsa, bu addımı keçin).
2. Sağ yuxarıda **+ → New repository**. Ad yazın, məsələn `vergi-naviqator`, **Public** seçin, **Create repository** basın.
3. Açılan səhifədə **uploading an existing file** linkini basın. Arxivdən çıxardığınız qovluğun **içindəki bütün faylları və qovluqları** (`index.html`, `data`, `scripts`, `.github`, `README.md`) pəncərəyə sürükləyin və **Commit changes** basın.
   - `.github` qovluğu görünmürsə (Mac-da gizli olur): **Add file → Create new file** basın, ad yerinə `.github/workflows/taxes-sync.yml` yazın, həmin faylın məzmununu kopyalayıb yapışdırın və **Commit changes** basın.
4. **Settings → Pages** bölməsində **Source** üçün **GitHub Actions** seçin.
5. **Actions** bölməsində **taxes.gov.az avtomatik yeniləmə → Run workflow** basın (yalnız ilk dəfə, sonra hər saat özü işləyir).
6. 1–2 dəqiqədən sonra sayt bu ünvanda açılır:
   `https://İSTİFADƏÇİ-ADINIZ.github.io/vergi-naviqator/`

Bundan sonra heç nə etmək lazım deyil.

## Faylların təyinatı

| Fayl | Nədir |
|---|---|
| `index.html` | Saytın özü |
| `data/taxes.json` | taxes.gov.az-dan avtomatik oxunan məlumat (robot yeniləyir, əl ilə dəyişməyin) |
| `data/source-text.txt` | Rəsmi səhifənin mətn surəti — dəyişiklikləri müqayisə etmək üçün |
| `data/faq-baseline.json` | Saytdakı qısa sual-cavabların hansı rəsmi mətnə əsaslandığı |
| `scripts/taxes_sync.py` | Rəsmi səhifəni oxuyan proqram |
| `.github/workflows/taxes-sync.yml` | Hər saat işə salma qaydası |

## Tez-tez suallar

**Bir şey düz işləmirsə necə bilərəm?**
Saytı `?admin=idare2026` ilə açın (məs. `…/vergi-naviqator/?admin=idare2026`). Aşağıdakı idarəetmə panelində son yoxlama tarixi görünür. 2 gündən çox yoxlanılmayıbsa, orada xəbərdarlıq çıxır. Rəsmi səhifənin quruluşu kökündən dəyişsə, robot köhnə məlumatı saxlayır (sayt sınmır) və GitHub sizə "workflow failed" e-poçtu göndərir.

**Sayt GitHub-da deyil, öz hostinqimdə olacaq.**
Bu repo yenə də hər saat məlumatı yeniləyəcək. Öz hostinqinizə yalnız `index.html` faylını yükləyin və onun içində bu sətri tapıb ünvanı dəyişin:
`const TAXES={url:'data/taxes.json', …}` → `url:'https://İSTİFADƏÇİ-ADINIZ.github.io/vergi-naviqator/data/taxes.json'`

**İdarəetmə açarını necə dəyişim?**
`index.html`-də `ADMIN_KEY='idare2026'` sətrini tapıb öz sözünüzü yazın.

**Trademark və fəaliyyət istiqaməti haradan gəlir?**
Rəsmi səhifədə bu sütunlar yoxdur, ona görə saytın öz məlumatından götürülür. Yeni əlavə olunan şirkətdə bu xanalar "—" görünür. İstəsəniz, `qeyri-rezidentler-reyestri.xlsx` faylını repoya yükləyib həmin sütunları orada doldura bilərsiniz.
