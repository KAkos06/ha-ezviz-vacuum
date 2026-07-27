# EZVIZ Vacuum – Home Assistant integráció

Ez az integráció lehetővé teszi, hogy egy támogatott EZVIZ robotporszívó
állapotát megjelenítsd a Home Assistantban.

A telepítés után a Home Assistantban többek között láthatod:

- a robotporszívó aktuális állapotát;
- az akkumulátor töltöttségét;
- hogy a porszívó töltődik-e és elérhető-e;
- az aktuális takarítási feladatot;
- a beállított szívóerőt és vízmennyiséget;
- az aktív térkép nevét;
- a kefék, a HEPA-szűrő, a felmosó és a szenzorok hátralévő értékeit;
- az EZVIZ valós idejű értesítési kapcsolatának állapotát.

> [!IMPORTANT]
> Ez jelenleg egy állapotfigyelő, csak olvasható integráció. A takarítás
> elindítása, szüneteltetése, a dokkolás és más vezérlési műveletek még nem
> támogatottak.

## Támogatott készülék

Az első támogatott és célzott modell:

- **EZVIZ RE5 Plus**
- eszköztípus: `CS-RE5P-TWT`
- eszközkategória: `SweepingRobot`
- alkategória: `RE5P`

Más EZVIZ robotporszívók is megjelenhetnek, ha ugyanazt az adatstruktúrát
használják, de ezek működése még nincs igazolva.

## Mire van szükség?

- működő Home Assistant rendszerre;
- telepített [HACS](https://hacs.xyz/) kiegészítőre;
- internetkapcsolatra;
- arra az EZVIZ-fiókra, amelyhez a robotporszívó hozzá van rendelve.

Az integráció az EZVIZ felhőszolgáltatását használja, ezért internetkapcsolat
nélkül nem tudja frissíteni a porszívó állapotát.

## Telepítés HACS segítségével

Az integráció egyelőre HACS egyéni tárolóként telepíthető.

1. Nyisd meg a Home Assistantban a **HACS** oldalt.
2. Válaszd az **Integrations** menüpontot.
3. A jobb felső sarokban nyisd meg a hárompontos menüt.
4. Válaszd a **Custom repositories** lehetőséget.
5. A repository mezőbe másold be:

   ```text
   https://github.com/KAkos06/ha-ezviz-vacuum
   ```

6. A kategóriánál válaszd az **Integration** lehetőséget.
7. Kattints az **Add** gombra.
8. Keresd meg az **EZVIZ Vacuum** integrációt, majd telepítsd.
9. A telepítés után indítsd újra a Home Assistantot.

## Az integráció beállítása

Az újraindítás után:

1. Nyisd meg a **Beállítások → Eszközök és szolgáltatások** oldalt.
2. Kattints az **Integráció hozzáadása** gombra.
3. Keresd meg az **EZVIZ Vacuum** integrációt.
4. Add meg az EZVIZ-fiókod adatait:

   - **E-mail-cím:** az EZVIZ alkalmazásban használt fiók;
   - **Jelszó:** az EZVIZ-fiók jelszava;
   - **Régió:** Magyarország és a legtöbb európai fiók esetén `eu`.

5. Sikeres bejelentkezés után az integráció automatikusan megkeresi a fiókhoz
   tartozó támogatott robotporszívókat.

Minden megtalált robotporszívó külön eszközként jelenik meg a Home Assistantban.

## Létrejövő entitások

Az elérhető adatoktól függően az integráció az alábbi entitásokat hozza létre.

### Robotporszívó

- aktuális aktivitás, például tétlen, takarít, szünetel, visszatér vagy dokkolt;
- elérhetőség;
- aktuális szívóerő;
- esetleges hibaállapot.

### Szenzorok

- akkumulátor töltöttsége;
- aktuális feladat állapota;
- szívóerő;
- vízmennyiség;
- térkép neve;
- HEPA-szűrő hátralévő értéke;
- főkefe hátralévő értéke;
- oldalkefe hátralévő értéke;
- felmosó hátralévő értéke;
- szenzortisztítás hátralévő értéke;
- utolsó valós idejű értesítés időpontja;
- az EZVIZ értesítési kapcsolat állapota.

### Kapcsolók állapotát jelző szenzorok

- töltés;
- online állapot;
- valós idejű értesítési kapcsolat;
- szőnyeg-turbó mód;
- pihenő mód.

> [!NOTE]
> A fogyóeszközökhöz kapott hátralévő számértékek mértékegységét az EZVIZ nem
> dokumentálja egyértelműen. Emiatt az integráció ezeket mértékegység nélküli,
> nyers értékként jeleníti meg.

## Milyen gyorsan frissülnek az állapotok?

Az integráció kétféle frissítést használ:

1. **EZVIZ valós idejű értesítések:** ha az EZVIZ felhő értesítést küld a
   porszívó állapotváltozásáról, az integráció rövid időn belül lekéri az új
   állapotot.
2. **Biztonsági időszakos frissítés:** ha nem érkezik valós idejű értesítés,
   az integráció rendszeresen lekéri az állapotot az EZVIZ felhőből.

Ehhez nincs szükség saját MQTT szerverre vagy Mosquitto telepítésére. Az
integráció közvetlenül az EZVIZ felhő értesítési szolgáltatásához kapcsolódik.

Az RE5 Plus esetében még nem igazolt, hogy az EZVIZ minden egyes
állapotváltozásról küld értesítést. Ha nem érkezik ilyen értesítés, az
integráció továbbra is működik az időszakos lekérdezéssel.

## Kézi telepítés HACS nélkül

1. Töltsd le a repository tartalmát.
2. Másold a `custom_components/ezviz_vacuum` mappát a Home Assistant
   konfigurációs könyvtárának `custom_components` mappájába.
3. Indítsd újra a Home Assistantot.
4. Add hozzá az integrációt a
   **Beállítások → Eszközök és szolgáltatások** oldalon.

A végeredménynek így kell kinéznie:

```text
config/
└── custom_components/
    └── ezviz_vacuum/
        ├── __init__.py
        ├── manifest.json
        └── ...
```

## Ha nem sikerül a beállítás

Ellenőrizd a következőket:

- ugyanazzal az e-mail-címmel és jelszóval be tudsz-e jelentkezni az EZVIZ
  mobilalkalmazásba;
- a robotporszívó megjelenik-e és online állapotú-e az EZVIZ alkalmazásban;
- a régió `eu` értékre van-e állítva;
- újraindítottad-e a Home Assistantot a HACS-telepítés után;
- nem adtad-e már hozzá korábban ugyanazt az EZVIZ-fiókot.

Részletesebb naplózáshoz add hozzá ezt a Home Assistant
`configuration.yaml` fájljához:

```yaml
logger:
  default: info
  logs:
    custom_components.ezviz_vacuum: debug
```

A módosítás után indítsd újra a Home Assistantot.

Hibajelentésnél hasznos információ:

- Home Assistant verzió;
- integráció verzió;
- robotporszívó pontos modellje és firmware-verziója;
- használt régió;
- az integráció letöltött, kitakart diagnosztikája;
- a hibához kapcsolódó debug naplórészlet.

Soha ne küldj jelszót, tokenfájlt, teljes sorozatszámot, hitelesítési kódot vagy
teljes nyers API-választ hibajelentésben.

## Jelenlegi korlátozások

- A robotporszívó vezérlése még nem támogatott.
- Az integráció használatához internetkapcsolat szükséges.
- Az EZVIZ nem dokumentált felhő API-jára támaszkodik.
- Egy későbbi EZVIZ API-változás átmenetileg működésképtelenné teheti.
- Túl gyakori lekérdezés esetén az EZVIZ ideiglenesen korlátozhatja a fiókot.
- A többfaktoros hitelesítést igénylő bejelentkezés jelenleg nem támogatott.
- Az RE5 Plus valós idejű értesítéseinek teljes lefedettsége még ellenőrzésre
  szorul.

## Adatvédelem

Az EZVIZ bejelentkezési adatokat a Home Assistant konfigurációs bejegyzése
tárolja. A Home Assistant konfigurációs könyvtárát és biztonsági mentéseit ennek
megfelelően védd.

Az integráció diagnosztikai kimenete kitakarja többek között a bejelentkezési
adatokat, tokeneket, munkamenet-azonosítókat, sorozatszámokat, hálózati címeket
és titkos kulcsokat.

## Jogi nyilatkozat

This project is an unofficial community integration and is not affiliated with,
endorsed by, or supported by EZVIZ.
