# SAI2_Group_JMAF
Repo for SAI2 Group Project

Prototyp eines Security-Tutors: Er führt Studierende mit gestuften Fragen zu
einer unsicheren Entscheidung in KI-generiertem Webcode, ohne sie zu nennen.
Die Spezifikation steht in [development.md](development.md). Umgesetzt ist
bisher Arbeitsschritt 1: das Übungsformat und zwei Übungsentwürfe.

## Setup

Python 3.11 oder neuer.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # wird erst ab Schritt 3 (LLM) gebraucht
```

## Tests

```bash
pytest
```

Die Tests prüfen jede Validierungsregel (gültiger und ungültiger Fall), die
Normalisierung des Leak Guards, dass `tutor_context()` weder `answer_key` noch
`close` enthält, und dass alle Dateien in `exercises/` fehlerfrei laden.

## Neue Übung anlegen

1. Eine bestehende Datei in `exercises/` kopieren. Der Dateiname ist die `id`
   (nur Kleinbuchstaben, Ziffern, Bindestriche), z. B. `innerhtml-strapi.yaml`
   mit `id: innerhtml-strapi`.
2. Ausfüllen. Alles, was Studierende sehen (`scenario`, `hint`, `fix`,
   `pruefmuster`), auf Deutsch, mit ss statt ß.
3. `pytest` ausführen. Fehler haben die Form `<datei>: <feld>: <regel>`.

Regeln, die beim Laden geprüft werden:

- `decoy` ist explizit `true` oder `false`.
- Die Stufen 1, 2 und 3 sind vorhanden, jede mit nicht leerem `goal` und `hint`.
- `forbidden` ist in Stufe 1 und 2 nicht leer.
- Kein `hint` enthält einen seiner eigenen `forbidden`-Begriffe. Verglichen
  wird nach der Normalisierung des Leak Guards (Kleinschreibung, ohne
  Satzzeichen, ä/ö/ü = ae/oe/ue), auf ganzen Wörtern.
- `answer_key.accepted` hat mindestens 2 Einträge.
- Die `id` entspricht dem Dateinamen und ist eindeutig.
- Unbekannte Felder (z. B. Tippfehler wie `forbiden`) sind Fehler.

Die Hints sind Vorschläge des Teams und mit `# TODO Expert:in` markiert. Die
finalen Hints kommen von der Fachperson (Gold Standard).

## Entscheide (Ergänzungen zu development.md)

- **Modelle:** Pydantic statt dataclasses (Layout nennt dataclasses).
- **Tutor-Kontext:** `Exercise.tutor_context(stage)` liefert nur `goal` und
  `hint` der Stufe, auch ohne `forbidden`. `answer_key` und `close` sieht der
  Tutor nie, damit er sie nicht umschreiben und verraten kann.
- **Decoys:** Es gelten dieselben Regeln. `accepted` enthält die richtigen
  Begründungen, warum der Code in Ordnung ist. `forbidden` enthält Begriffe,
  die das Urteil vorwegnehmen (z. B. „sicher“, „unsicher“).
- **Stufe 0:** Optionales Feld `hook` (Text des echten Vorfalls) auf oberster
  Ebene. Es wird nicht an den Tutor gegeben.
- **Ordner:** `eval/results/` ist angelegt, obwohl es im Layout fehlt.
- **LLM-Anbindung vorgezogen:** `core/llm.py` und `core/config.py` entstehen
  vor Schritt 2 der "Order of work" (UI ohne LLM). Tutor, Grader und Prompts
  folgen erst in Schritt 3.
- **Backend:** BFH-LiteLLM-Proxy (OpenAI-kompatibel) über das `openai`-SDK.
  Der Provider kommt nur in `core/llm.py` vor.
- **API-Key:** wird als Pydantic-`SecretStr` gehalten. Fehlermeldungen nennen
  nur den Variablennamen. Provider-Exceptions werden in eigene Exceptions
  übersetzt (`from None`). Alles, was wie `sk-…` aussieht, wird entfernt.
- **Retries:** eigene Logik (exponentieller Backoff mit Jitter, 1 s bis
  maximal 20 s) statt der Retries des SDK. Das SDK läuft mit `max_retries=0`.
  Retry gibt es bei 429, 5xx, Timeout und Verbindungsfehlern, keinen Retry bei
  anderen 4xx.
- **`LLMResult.warnings`:** Zusatzfeld für leere oder abgeschnittene
  Antworten (`finish_reason=length`), damit diese nicht still durchgehen.
- **Reasoning:** `text` ist nur `message.content`. Zusätzlich werden
  `<think>…</think>`-Blöcke aus dem Content entfernt (auch nicht
  geschlossene), weil manche Modelle hinter einem Proxy ihr Reasoning so in
  den Content schreiben. Das Entfernen erscheint als Warnung.
- **`latency_ms`:** gesamte Dauer von `chat()`, inklusive Retries und
  JSON-Fallback, also die Wartezeit, die Studierende erleben.
- **`model` in `LLMResult`:** der angefragte Modellname aus der Config, nicht
  der Name, den der Proxy zurückgibt. So bleiben die Logs über Läufe hinweg
  vergleichbar.
