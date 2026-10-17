# Spec: Quell-URL-agnostische Release-Suche

Status: **Phase 1 und Phase 2 umgesetzt (Version 2.0)**.

Stand der Phase 2:
- Spotify (Album und Track), Amazon Music (Album, `.com`) und Smart Links (too.fm, ffm.to) laufen über den Browser.
- Smart Links liefern die Plattform-Links der Seite direkt (Confidence 100). Nur die übrigen Plattformen werden gesucht. Die Quellen-Auflösung läuft über die Seite (Ziel-Links aus dem `cd`-Parameter), nicht über Odesli.
- Beatport ist nicht unterstützt: Cloudflare-Challenge, auch im Browser.
- Freitext-Suche (Phase 3) ist weiterhin offen.

## 1. Ziel

`find_release()` akzeptiert jede unterstützte Plattform-URL als Ausgangspunkt, nicht nur Bandcamp. Die URL wird in Artist, Titel und Release-Typ aufgelöst. Danach wird das Release auf allen anderen aktiven Plattformen gesucht.

Das Tool übernimmt damit die Aufgabe, die bisher Odesli (song.link) erfüllt hat: aus einer Plattform-URL die Links auf allen anderen Plattformen liefern. Odesli ist dabei **keine Abhängigkeit**. Das Tool braucht keinen API-Key und keinen externen Dienst. Odesli bleibt nur als Referenz für Abnahmetests (siehe Abschnitt 8).

Anlass: Das Release "Logic Moon & Diogene - Miracles" hat keine Bandcamp-Seite, nur einen too.fm-Smart-Link. Der Scraper kann es deshalb heute nicht verarbeiten.

## 2. Nicht-Ziele

- Keine Freitext-Suche ohne URL in dieser Phase (siehe Phase 3).
- Keine Plugin-Registry und keine Basisklassen. Ein Dict mit Funktionen genügt.
- Die deaktivierten Plattformen (YouTube Music, Tidal, Napster, Pandora) werden nicht aktiviert.
- Kein Schreiben in `releases.js`. Das bleibt ein manueller Schritt laut `AGENTS.md`.

## 3. Unterstützte Eingabe-URLs

| Host | Beispiel | Auflösung | Stand (geprüft 2026-10-17) |
|---|---|---|---|
| bandcamp.com | `.../album/<slug>` | JSON-LD, `og:title`, Markup (bestehend, `bandcamp.py`) | funktioniert |
| music.apple.com | `.../album/<slug>/<id>` | `og:title` (`"<Titel> by <Artist> on Apple Music"`) | `og:title` vorhanden |
| deezer.com | `/<lang>/album/<id>` | Titel: `og:title`; Artist: `GET https://api.deezer.com/album/<id>` (JSON, kein Auth-Key) | funktioniert ohne Browser |
| soundcloud.com | `/<artist>/sets/<slug>` | Titel: `og:title`; Artist: erster URL-Pfadabschnitt, normalisiert (Hyphens → Spaces, Titlecase) | Einschränkung: Slug ≠ Displayname bei Kollaborationen |
| open.spotify.com | `/album/<id>` | **keine Metadaten ohne Browser** (generischer `<title>`, kein `og:title`, kein JSON-LD) | nur mit Playwright lösbar |
| music.amazon.* | `/albums/<id>` | offen, nicht geprüft | Phase 2 |
| beatport.com | `/release/<slug>/<id>` | HTTP 403 für Requests (Cloudflare) | nur mit Playwright lösbar |
| Smart Links (too.fm u. ä.) | `https://too.fm/<id>` | Seite lädt Plattform-Links per JavaScript nach, nicht im HTML | nur mit Browser oder externem Dienst |

**Phase 1** (Resolver Requests-basiert): Bandcamp (bestehend), Apple Music, Deezer, SoundCloud.
**Phase 2** (Resolver Browser-basiert): Spotify, Beatport, Smart Links, Amazon.

**Hinweis:** "Requests-basiert" bezieht sich nur auf den neuen *Resolver* (Quell-URL auflösen). Die bestehenden *Suchmodule* für Deezer und SoundCloud (`platforms/deezer.py`, `platforms/soundcloud.py`) nutzen bereits Playwright – das bleibt unverändert.

**Erkennung:** Der Hostname bestimmt den Resolver. Unbekannte Hosts liefern `ValueError` mit der Liste der unterstützten Hosts.

**Odesli als Referenz, nicht als Quelle:** Die Odesli-API hat im Test mit 401 geantwortet (Key nötig). Das Tool ruft sie deshalb nicht auf. Für die Abnahme (Abschnitt 8) kann man die Odesli-Ausgabe für dieselbe URL manuell als Vergleichswert heranziehen.

## 4. Auflösung: `resolve_source(url) -> ReleaseInfo`

Neues Modul `src/dsp_scraper/sources.py`.

- `ReleaseInfo` wird nach `src/dsp_scraper/types.py` verschoben und erhält ein neues Feld `platform` (`bandcamp`, `apple_music`, `deezer`, `soundcloud`, `spotify`, `beatport`, `amazon_music`). Die übrigen Felder bleiben: `artist`, `title`, `release_type`, `url`. `bandcamp.py` importiert `ReleaseInfo` von dort; seine Logik bleibt unverändert.
- Ein Dict ordnet Hosts den Resolvern zu, z. B. `{"music.apple.com": apple_source, ...}`. Kein Registry-Framework.
- Jeder Resolver folgt dem Muster aus `bandcamp.py`: zuerst strukturierte Daten (JSON-LD, dann `og:title`), danach `RuntimeError`, wenn beides fehlt. Markup-Selektoren als letzter Fallback nur, wenn sie per Test abgedeckt sind.
- **Deezer-Resolver:** Titel aus `og:title`, Artist via `GET https://api.deezer.com/album/<id>` (Feld `artist.name`). ID aus dem URL-Pfad `/<lang>/album/<id>`. Kein Auth-Key nötig.
- **SoundCloud-Resolver:** Titel aus `og:title`, Artist = erster URL-Pfadabschnitt normalisiert (`logic-moon` → `Logic Moon`). Bekannte Einschränkung: Bei Kollaborations-Accounts stimmt der Slug nicht mit dem Displaynamen überein – Matching funktioniert trotzdem, weil der Titel-Score dominiert (70 % Gewicht).
- `sources.py` ruft `scrape_release()` für Bandcamp-URLs auf und setzt danach `platform = "bandcamp"` auf dem zurückgegebenen `ReleaseInfo`-Objekt.
- Browser-basierte Resolver (Phase 2) nutzen `platforms/_common.py` (`new_page()`), wie die Suche.

**Fehlerfälle:**
- Host nicht unterstützt: `ValueError`.
- HTTP-Fehler: `raise_for_status()` wie bisher.
- Metadaten nicht lesbar: `RuntimeError`. Die Suche läuft nicht los.

## 5. Kernlogik: `core.find_release(source_url, platform_delay=...)`

1. `info = resolve_source(source_url)`. Ergebnis hat `info.platform` = Quellplattform.
2. Für jede Plattform in `PLATFORMS`:
   - Ist sie die Quellplattform, wird **nicht gesucht**. Das Ergebnis entsteht direkt aus der Quell-URL: `url` = Quell-URL, `confidence` = 100.0, `matched_title` und `matched_artist` aus `info`, `error` = null.
   - Ist die Quellplattform nicht Teil von `PLATFORMS` (z. B. Bandcamp), wird keine Plattform übersprungen – alle 6 werden normal durchsucht.
   - Sonst wie bisher: `search()` und `pick_best()`.
3. Ausgabe:
   - `source.platform` ist die echte Quellplattform. Bisher war dieses Feld immer `"bandcamp"`.
   - `results` enthält weiterhin alle 6 aktiven Plattformen mit den 5 bekannten Feldern. Das Schema bleibt damit kompatibel.

**Begründung für die Quelle ohne Suche:** Die Quell-URL ist per Definition der Treffer. Dort zu suchen würde nur neue Fehlerquellen bringen (z. B. Single statt Album).

**Track-URLs:** `release_type` = `track` wird wie heute übernommen. Die Suche selbst bleibt unverändert, Track-Matching ist nicht Teil dieser Spec.

## 6. Matching

`matching.py` bleibt unverändert: `WRatio`, Gewichtung 0.7 Titel / 0.3 Artist, Schwelle 70.

**Offener Punkt:** Kollaborationen wie "Logic Moon & Diogene" gegen "Logic Moon". Der Artist-Score kann dabei zu niedrig ausfallen. Eine Änderung (z. B. `partial_ratio` für den Artist) nur einführen, wenn ein Test mit echten Daten zeigt, dass es nötig ist.

## 7. CLI

`uv run cli.py <url>` akzeptiert jede unterstützte URL. Bei unbekanntem Host listet die Fehlermeldung die unterstützten Hosts. `--stdout` und `--delay` bleiben unverändert.

## 8. Tests und Abnahme

- **Unit (ohne Netz):** `resolve_source()` gegen gespeicherte HTML-Fixtures, je ein Fixture pro Host. Zusätzlich je ein Test pro Fehlerpfad: unsupportierter Host (`ValueError`), HTTP-Fehler (Mock 404/500), fehlende Metadaten (`RuntimeError`).
- **Live-Smoke (manuell):** eine echte URL pro Host, analog zu `tests/test_bandcamp.py`.
- **Regression:** Die 15 bestehenden Bandcamp-Referenz-Releases liefern nach der Änderung dieselben Ergebnisse wie vorher. Abgleich per JSON-Diff, wie beim bisherigen Full-Pipeline-Test.
- **Abnahme Phase 1:** Eingabe `https://music.apple.com/us/album/it-may-never-coming-back-single/6804971310` liefert für Spotify, Amazon, Deezer und SoundCloud jeweils eine URL mit Confidence ≥ 70 oder `null` mit Begründung.
- **Abnahme Phase 2:** Eingabe `https://too.fm/2mozry1` (Miracles) liefert Spotify, Apple, Amazon, Deezer und SoundCloud. Ist eines davon nicht auffindbar, wird das in der Ausgabe begründet, nicht geraten.
- **Vergleich mit Odesli (manuell):** Für jede Abnahme-URL die Odesli-Seite (song.link) öffnen und die Plattform-Links mit der Scraper-Ausgabe abgleichen. Abweichungen werden dokumentiert: Fehlt bei uns etwas, das Odesli kennt, oder umgekehrt? Odesli wird dabei nie im Code aufgerufen.

## 9. Phasen

- **Phase 1:** `sources.py` mit Apple, Deezer und SoundCloud, Bandcamp-Anbindung, `core`-Änderung, CLI, Unit-Tests.
- **Phase 2:** Spotify-Resolver (Playwright), Beatport, Amazon, Smart Links (Browser-Rendering, Links aus dem gerenderten DOM lesen). Jeder Resolver mit Live-Test.
- **Phase 3 (optional):** Freitext-Suche (Artist + Titel ohne URL) als eigener Einstieg.

## 10. Risiken

- **Browser-Laufzeit:** Phase 2 macht jede Quelle langsamer, Schätzung einige Sekunden pro Release. Für die Batch-Läufe relevant.
- **Blockaden:** Beatport (Cloudflare) und mögliche Consent-Wände bei EU-Zugriffen. Ein Resolver kann ausfallen, ohne dass der Rest des Laufs stoppt.
- **Markup-Änderungen:** Die Selektoren der Plattform-Module wurden am 2026-08-23 verifiziert. Sie können sich ändern, dann liefern sie still `[]`.
- **Deezer JSON API:** Der Deezer-Resolver nutzt `https://api.deezer.com/album/<id>` für den Artist-Namen. Wenn diese API Rate Limits setzt oder ihr Schema ändert, fällt der Resolver mit `RuntimeError` aus. Fehler werden via `raise_for_status()` surfaced; kein stiller Ausfall.

## 11. Offene Fragen

1. Welche Eingaben brauchst du tatsächlich? Reicht Bandcamp plus Apple/Deezer/SoundCloud (Phase 1), oder müssen Spotify und Smart Links ebenfalls rein? Da das Tool Odesli ersetzen soll, sind Smart Links (too.fm u. ä.) als Eingabe vermutlich Pflicht. Das bedeutet Phase 2.
2. Ist die Browser-Laufzeit für Smart Links und Spotify in Ordnung?
3. Soll Phase 3 (Freitext-Suche) mit rein, oder erst später?
