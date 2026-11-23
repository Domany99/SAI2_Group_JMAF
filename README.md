# SAI2_Group_JMAF
Repo for SAI2 Group Project

Prototyp eines Security-Tutors: Er führt Studierende mit gestuften Fragen zu
einer unsicheren Entscheidung in KI-generiertem Webcode, ohne sie zu nennen.
Die Spezifikation steht in [development.md](development.md). Umgesetzt sind
bisher Arbeitsschritt 1 (Übungsformat und zwei Übungsentwürfe) und
Arbeitsschritt 2 (Stufen-Logik und Streamlit-UI mit fixen Fragen, ohne LLM).

## Setup

Python 3.11 oder neuer.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # wird erst ab Schritt 3 (LLM) gebraucht
```

## App starten

Im Repo-Hauptordner, mit aktivierter `.venv`:

```bash
streamlit run app/main.py
```

Die App öffnet sich im Browser (standardmässig http://localhost:8501).
Ablauf: Vorwissen einstufen (Pflicht vor der ersten Übung), Übung wählen,
Szenario lesen (Kursauftrag, KI-Chat, Code), die Fragen der Stufen 1 bis 3
beantworten, Abschluss mit Fix und Prüfmuster.

Zwei Modi über die Variable `MODE` (in `.env` oder als Umgebungsvariable):

- **`MODE=llm` (Standard):** Die Frage jeder Stufe formuliert der Tutor
  (LLM 1) über den Leak Guard, die Antwort bewertet der Grader (LLM 2).
  Jeder Turn (Tutor, Antwort, Grader, Hint-Fallback) wird nach
  `logs/<YYYY-MM-DD>.jsonl` geloggt. Braucht eine gültige `.env` mit
  API-Key und ausserhalb des BFH-Netzes VPN. Eine Frage dauert 15 bis 40 s,
  während der Wartezeit zeigt die App einen Ladehinweis.
- **`MODE=fixed`:** Schritt 2, für Tests und als Notfall. Die Fragen sind die
  `hint`s aus den Übungsdateien, jede Antwort beurteilt die **Testleitung**
  per Knopf (Erkannt, Teilweise, Nicht erkannt). Kein LLM, kein Log.

```bash
MODE=fixed streamlit run app/main.py      # PowerShell: $env:MODE="fixed"; streamlit run app/main.py
```

Mit `HOOK=incident` erscheint vor Stufe 1 der Vorfall-Hook (Stufe 0), sofern
die Übung ein Feld `hook` hat. Standard ist `HOOK=none`.

Neue oder geänderte Dateien in `exercises/` erscheinen nach einem Neustart der
App automatisch.

Das Aussehen folgt dem Low-Fi-Prototyp „Mind the Gap“ (Navy, Gelb,
Warnstreifen). Das Theme steht in `.streamlit/config.toml`, die übrigen
Styles als CSS oben in `app/main.py`.

## Tests

```bash
pytest
```

Die Tests prüfen jede Validierungsregel (gültiger und ungültiger Fall), die
Normalisierung des Leak Guards, dass `tutor_context()` weder `answer_key` noch
`close` enthält, dass alle Dateien in `exercises/` fehlerfrei laden und jeden
Übergang der Stufen-Logik, inklusive der Garantie, dass die Lücke erst nach
Stufe 3 aufgelöst wird.

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
- **Fehlannahmen:** Optionales Feld `misconceptions` auf oberster Ebene, eine
  Liste mit `id`, `belief` und `reaction`. Der Grader gibt im Feld
  `misconception` die `id` zurück, der Code wählt damit die vorbereitete
  Reaktion. Die `id` ist pro Übung eindeutig. Nicht im Tutor-Kontext.
- **Fix-Auswahl:** Optionales Feld `close.fix_choices`, eine Liste mit `text`,
  `verdict` (`correct`, `partial`, `wrong`) und `reason`. Wenn vorhanden,
  mindestens 2 Optionen und mindestens eine `correct`. Erscheint erst nach dem
  Erkennen und nur, wenn die Person keinen eigenen Fix findet.
- **Beheben-Phase:** Nach dem Abschluss der Stufen (erkannt oder nach Stufe 3
  aufgelöst) zeigt die App zuerst Lücke und Folge, dann die Frage nach einem
  eigenen Fix. Erst nach dem eigenen Vorschlag oder dem Knopf «Ich komme nicht
  weiter» erscheinen Fix und Prüfmuster. Mit dem Knopf kommen zuerst die
  `fix_choices`, in pro Start gemischter Reihenfolge (die richtige Option steht
  in den Dateien oft zuerst). Eine Wahl zählt nur mit Begründung; danach zeigt
  die App das Urteil («Passt», «Teilweise», «Passt nicht») mit `reason` und
  alle Optionen mit Begründung. Der eigene Vorschlag wird nicht bewertet, die
  Person vergleicht ihn selbst mit dem Fix. Bei Decoys lauten Titel und Frage
  anders («Der Code ist in Ordnung», «Würdest du trotzdem etwas ändern?»).
  Läuft in `MODE=fixed` und `MODE=llm` gleich, ohne LLM.
- **Beheben-Phase nicht geloggt:** Eigener Vorschlag, Wahl und Begründung
  stehen nur in der Sitzung. `Turn` kennt dafür keine Rolle und nur die
  Stufen 1 bis 3. Ob die Daten ins Log sollen, ist offen.
- **Reihenfolge:** Pflichtfeld `order` (ganze Zahl ab 1) auf oberster Ebene,
  eindeutig über alle Übungen. `load_all` sortiert danach statt nach id, die
  App zeigt die Übungen in dieser Reihenfolge. Werte: API-Key 1, Strapi 2,
  XSS 3.
- **API-Key-Übung:** `api-key-frontend` hat ab `version: 2` den echten Fall
  (Key über GitHub Secrets in `secret.js` gebaut und mit der Seite
  veröffentlicht) statt des Wetter-API-Platzhalters. Die id bleibt, weil
  Tests, Skripte und Probeläufe sie verwenden. Probeläufe vor dem 20.11.2026
  beziehen sich auf Version 1.
- **Strapi-Übung:** `strapi-auth-false` ersetzt den Platzhalter
  `strapi-public-create`. In den Agent-Tests war Public `create` gewollt, die
  Lücke war `auth: false` in der Route, das auch Ändern und Löschen öffnet.
- **Decoy-Übung:** `kommentare-bereinigt` (`order: 4`) ist ein echter
  Agent-Lauf (17.11.2026), in dem die KI `v-html` mit einer eigenen
  Bereinigung (Positivliste) gebaut hat. In Chromium mit 30 Eingaben
  getestet, keine Ausführung. Ein Decoy statt der 1 bis 2 aus
  `development.md`. Er steht fest an vierter Stelle; wer die Übungen
  wiederholt, kennt ihn. Das ist eine Limitation, kein Versehen.
- **Decoy-Bewertung:** Behauptet eine Antwort eine konkrete Lücke, die es
  nicht gibt, ist sie `not`, auch wenn der Einwand fachlich berechtigt ist
  (etwa "eigene Filter sind lückenhaft"). So steht es in `grader_v2`, und so
  wird auch beim Labeln gewertet. Die Stufen-Logik behandelt `partial` und
  `not` ohnehin gleich.
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
- **Stufen-Logik:** `core/stages.py` hält den Zustand als unveränderliches
  `StageState` (Stufe 0 bis 3 und `outcome`). Jeder Übergang gibt einen neuen
  Zustand zurück. Ungültige Übergänge (Urteil in Stufe 0, Urteil nach dem
  Abschluss, unbekanntes Urteil) sind Fehler (`StageError`), keine stillen
  Sonderfälle.
- **Urteile:** `Verdict` hat die Werte `recognized`, `partial` und `not`, also
  dieselben wie die Grader-Ausgabe. `on_verdict()` nimmt auch die Strings
  direkt an. Ungültige Grader-Ausgaben werden ab Schritt 3 vorher zu
  `partial`, nicht in der Stufen-Logik.
- **Abschluss:** `outcome` ist `recognized` (selbst gefunden) oder `revealed`
  (nach Stufe 3 aufgelöst). Die Stufe bleibt erhalten, so ist sichtbar, auf
  welcher Stufe die Lücke gefunden wurde (Messgrösse für Step 4).
- **Testleitung statt Grader:** In Schritt 2 bewertet eine Person die
  Antworten in der UI. Die Knöpfe nutzen dieselben drei Urteile wie LLM 2,
  damit die Testläufe mit den späteren Grader-Läufen vergleichbar sind.
- **Einstufung:** Vor der ersten Übung schätzen Studierende ihr Vorwissen
  selbst ein (`core/prior_knowledge.py`: neu, Grundlagen, erfahren). Ohne
  Einstufung startet keine Übung. In Schritt 2 wird die Stufe nur angezeigt
  und pro Antwort mitgeführt. Ab Schritt 3 geht sie in den Tutor-Kontext und
  in die Logs (Segmentvergleich, H11). Die Beschreibungen der Stufen fragen
  nach Erfahrung (Begriffe gekannt, Code geprüft, Security-Modul besucht),
  nicht nach dem gewünschten Tempo. Sie versprechen keine Unterschiede bei
  Stufen oder Hinweisen, weil es diese nicht gibt.
- **`Verdict` in `core/models.py`:** liegt dort wie im Layout vorgesehen,
  weil auch `Turn` ihn braucht (sonst Import-Kreis mit `core/stages.py`).
  `core/stages.py` re-exportiert ihn, bestehende Imports bleiben gültig.
- **Turn-Rollen:** `tutor` (Frage von LLM 1, auch blockierte mit
  `guard_hit=true`), `student` (Antwort), `grader` (Urteil, `text` = evidence)
  und `hint` (Fallback auf den Expert:innen-Hint nach dem zweiten
  Guard-Treffer). So zeigt das Log, was die Person wirklich gesehen hat.
  `model`, `prompt_version` und `temperature` sind nur bei `tutor` und
  `grader` gesetzt (sonst `null`), `verdict` nur bei `grader`, `guard_hit`
  nur bei `tutor`. `prompt_version` muss `<role>_v<n>` sein.
- **Turn-Stufe:** nur 1 bis 3. Stufe 0 (Hook) hat weder Frage noch Antwort.
- **Vorwissen im Log:** die Code-Werte `new | basics | experienced` aus
  `core/prior_knowledge.py`, nicht die deutschen Werte aus Issue I-05.
- **Session-ID:** `s-` plus 8 Hex-Zeichen aus `secrets` (z. B.
  `s-7f3a91c2`) statt 4 wie im Beispiel der Spezifikation. Bei 4 Zeichen liegt
  die Kollisionswahrscheinlichkeit ab etwa 50 Sessions bei rund 2 %.
- **Zeitstempel:** ISO 8601 mit Zeitzone, auf Sekunden gerundet wie im
  Beispiel. Naive Zeitstempel lehnt `Turn` ab. `now()` nimmt fest
  `Europe/Zurich` (seit I-18), nicht die Zone des Servers: Streamlit
  Community Cloud läuft in UTC, sonst lägen Zeitstempel und Tagesgrenze der
  Logdateien daneben. Dafür ist `tzdata` gepinnt (Windows hat keine
  Zeitzonen-Daten); gepinnt ist die getestete Version 2025.2, die über
  Streamlit/pandas ohnehin installiert ist.
- **Logdatei pro Tag:** Das Datum im Namen `logs/<YYYY-MM-DD>.jsonl` ist das
  Datum von `ts` in dessen eigener Zone. Schreiben ist mit einem Lock
  geschützt, weil Streamlit mehrere Sessions in Threads eines Prozesses
  bedient.
- **Freitext:** `text` enthält die Antworten wörtlich. Schreibt jemand den
  eigenen Namen hinein, steht er im Log. Das lässt sich im Code nicht
  verhindern und gehört in die Instruktion vor dem Pilot (siehe I-15).
- **Prompt-Platzhalter:** `{{name}}` statt `str.format`, weil die Prompts
  JSON mit einfachen `{}` enthalten. `render()` ist streng (fehlende und
  überzählige Werte sind Fehler) und ersetzt nicht rekursiv. Details in
  `prompts/README.md`, Loader in `core/prompts.py`.
- **Prompt = System-Prompt:** Die Vorlage ist die System-Nachricht. Antworten
  der Studierenden kommen nie in die Vorlage, sondern als eigene
  User-Nachricht, damit Anweisungen darin nicht als Teil des Prompts gelten.
- **Feed back:** Der Tutor sieht ab Stufe 2 die letzte Antwort der Person
  (als User-Nachricht), damit Feed back konkret wird. Er darf sie nicht als
  richtig oder falsch bewerten. Das erweitert I-07 um einen optionalen
  Parameter.
- **Few-Shot im Tutor:** Platzhalter `examples` mit den Hints derselben
  Stufe aus anderen Übungen, eingesetzt von `core/tutor.py`. Nichts davon
  steht fest im Prompt, sonst wäre bei einer der Übungen ihr eigener Hint
  dabei.
- **Grader-Beispiele:** aus einer erfundenen Übung (Passwort-Reset über
  `?user=42`, Decoy bcrypt), nicht aus `eval/data/` und nicht aus
  `exercises/`. Ein Test prüft, dass keine Hints und keine `accepted` echter
  Übungen in den Prompts stehen.
- **Eingefrorene Prompts:** `prompts/frozen.txt` listet SHA-256 und
  Dateiname jeder Version, die in einem Eval-Lauf verwendet wurde. Ein Test
  schlägt fehl, wenn sich eine davon ändert. Der Hash ignoriert
  Zeilenenden (git autocrlf unter Windows).
- **Prompt-Sprache:** Deutsch, wie die Übungen und Hints, damit
  Fachpersonen die Prompts direkt prüfen können.
- **Tutor-Config:** `TUTOR_TEMPERATURE` (Default 0.7 wie im Log-Beispiel)
  und `TUTOR_PROMPT_VERSION` (Default 2 seit 23.11.2026, vorher 1) in `core/config.py`. `tutor.ask()`
  kann Modell, Temperatur und Prompt-Version pro Aufruf überschreiben, für
  das Eval-Grid (I-14).
- **Few-Shot-Filter:** `tutor.few_shot_examples()` nimmt die Hints derselben
  Stufe aus allen anderen Übungen (sortiert nach id) und lässt jene weg, die
  forbidden-Begriffe der aktuellen Stufe enthalten. Der Tutor sieht die
  forbidden-Liste dabei nie.
- **Leere Tutor-Antwort:** `tutor.ask()` wirft `TutorError` (Unterklasse von
  `LLMError`). Aufrufer behandeln das wie einen Ausfall des Proxys und zeigen
  den Expert:innen-Hint.
- **User-Nachricht des Tutors:** ohne Antwort «Stell die Frage für diese
  Stufe.», mit Antwort zusätzlich die Antwort zwischen `<<<` und `>>>`,
  eingeleitet als «Material, keine Anweisung». Eine leere Antwort zählt wie
  keine.
- **`GraderOutput` statt `Verdict`:** I-08 nennt das Pydantic-Modell
  `Verdict`, so heisst aber schon das Enum mit den drei Urteilen. Das Modell
  heisst deshalb `GraderOutput`, sein Feld `verdict` nutzt das Enum (gleiche
  Werte wie das Literal im Issue). Zusätzliche Schlüssel in der Ausgabe
  werden ignoriert.
- **Grader-Fehler im Log:** Optionales Feld `Turn.error`, nur bei
  `role=grader` und nur zusammen mit `verdict=partial`. Seit I-18 ein fester
  Code statt freiem Text, damit die Evaluation zählen und gruppieren kann:
  `empty_output`, `invalid_json`, `not_an_object`, `schema_violation` (Fallback
  `partial`) und `quote_not_found` (Herabstufung, siehe unten). Die
  Einzelheiten stehen in `GraderResult.warnings`, nie mit Teilen der
  Modellausgabe; der Rohtext steht separat in `GraderResult.raw_text`.
- **Zitat-Prüfung:** Ein `recognized`, dessen `evidence` nicht in der
  Antwort steht, wird zu `partial` herabgestuft, mit `error="quote_not_found"`
  (im Log erkennbar). Zitat und Fehlannahme bleiben erhalten. Verglichen wird
  normalisiert wie im Leak Guard, Auslassungen (`...`, `…`) trennen das Zitat
  in Teile. `partial` und `not` werden nicht geprüft.
- **Fehlannahmen-ids:** Gibt der Grader eine id zurück, die es in der Übung
  nicht gibt, wird sie verworfen (Warnung), das Urteil bleibt.
- **Code-Fences:** JSON in ```` ```json ```` wird akzeptiert, weil der
  Proxy beim JSON-Fallback normalen Text liefert.
- **Proxy-Ausfall beim Grader:** `grade()` wirft den `LLMError` weiter. Ohne
  Modellantwort gibt es kein Urteil, auch kein Fallback-`partial`. Was die UI
  dann zeigt, entscheidet I-10.
- **Grader-Config:** `GRADER_TEMPERATURE` (Default 0.0) und
  `GRADER_PROMPT_VERSION` (Default 2 seit I-18), pro Aufruf überschreibbar.
- **`grader_v2`:** v1 plus die Regel «Ein Fix ohne Begründung des Problems
  ist partial» und ein Beispiel dazu, sonst unverändert, damit ein
  Unterschied zwischen v1 und v2 in der Evaluation genau dieser Regel
  zuzuordnen ist. Anlass: Im Probelauf wurde «textContent statt innerHTML»
  `recognized` (`docs/probelaeufe.md`). Default ist v2, schon vor dem ersten
  Eval-Lauf. Weitere Beobachtungen stehen in `prompts/v2_candidates.md` und
  kommen erst nach der Evaluation in eine neue Version.
- **Proxy-Cache:** Der BFH-Proxy (LiteLLM) liefert identische Anfragen aus
  seinem Cache, auch bei Temperatur > 0. `core/llm.py` schickt deshalb
  `extra_body={"cache": {"no-cache": True}}` mit (`LLM_NO_CACHE`, Default
  `true`) und setzt `cache_hit`, wenn der Proxy den Header
  `x-litellm-cache-key` mitschickt. Am 20.11.2026 geprüft: Der Proxy
  erlaubt `no-cache` für unseren Key, eine Anfrage bei der BFH ist nicht
  nötig. Mit `no-cache` wird nicht aus dem Cache gelesen, die Antwort aber
  trotzdem gespeichert. Für die Header ruft `core/llm.py` das SDK über
  `with_raw_response` auf. Probeläufe vor I-18 waren teilweise
  Cache-Wiederholungen und zählen nicht für die Evaluation.
- **`cache_hit` im Log:** Pflicht bei `tutor` und `grader` (sonst `null`),
  steht auch in `TutorQuestion` und `GraderResult`. So lassen sich trotz
  `no-cache` durchgerutschte Treffer aus der Auswertung filtern.
- **`prompt_hash`:** SHA-256 des fertig eingesetzten System-Prompts (inkl.
  Few-Shot-Beispiele und Lösungsschlüssel), Pflicht bei `tutor` und
  `grader`. Die User-Nachricht mit der Antwort zählt nicht dazu, sonst wäre
  jeder Hash anders. `prompt_version` allein reicht nicht, weil sich die
  eingesetzten Beispiele und Schlüssel ändern, wenn Übungen angepasst
  werden.
- **`hook` im Log:** Pflicht in jedem Turn, `incident` oder `none`. Geloggt
  wird der Arm des A/B-Tests (Einstellung `HOOK`), nicht ob die Übung
  tatsächlich einen Hook hat; das lässt sich aus der Übungsdatei ableiten.
- **`n_examples`:** Zahl der Few-Shot-Beispiele im Tutor-Prompt, Pflicht bei
  `tutor`. Bei 0 setzt `tutor.ask()` eine Warnung: Die Stufe läuft dann
  Zero-Shot und ist nicht mit den anderen vergleichbar.
- **Reihenfolge im Log:** zuerst die Felder der Spezifikation, danach die
  Ergänzungen `prior_knowledge`, `hook`, `prompt_hash`, `n_examples`,
  `attempt`, `cache_hit`, `fallback`, `error`.
- **Leak-Guard-Ablauf in `core/leak_guard.py`:** nicht in `core/guard.py`,
  weil `core/models.py` von dort importiert und der Ablauf `core/tutor.py`
  braucht (Import-Kreis). `guard.py` behält `normalize()` und
  `find_forbidden()`, der Ablauf nutzt genau diese.
- **Zweiter Versuch ohne Wortliste:** Nach dem ersten Treffer erfährt der
  Tutor nicht, welche Wörter getroffen wurden, und sieht seine blockierte
  Frage nicht. Sonst lernte er einen Teil der forbidden-Liste kennen und
  wiche auf Synonyme aus, die der Guard nicht kennt. Stattdessen hängt
  `tutor.ask(strict=True)` die allgemein strengere Anweisung
  `prompts/tutor_strict_v<n>.md` an den System-Prompt (`TUTOR_STRICT_VERSION`,
  Default 1). Sie geht den Tonregeln vor.
- **`Turn.attempt`:** 1 oder 2, Pflicht bei `tutor`. Die Leak-Rate für Step 4
  ist der Anteil blockierter Versuche mit `attempt=1`. Ohne das Feld liesse
  sich ein zweiter Versuch nur über die Reihenfolge der Zeilen erkennen.
- **Blockierte Fragen im Log:** Auch der Text blockierter Versuche wird
  geloggt (`guard_hit=true`), die Person sieht ihn nie. Er ist Material für
  die Auswertung der Leaks.
- **Fallback bei Ausfall des Tutors:** Antwortet der Tutor nicht
  (`LLMError`, auch `TutorError` bei leerer Antwort), zeigt der Ablauf den
  Expert:innen-Hint wie nach dem zweiten Treffer. Ein Treffer im ersten
  Versuch bleibt dabei im Log. Fehler in Übung, Stufe oder Prompt-Vorlage
  gehen dagegen weiter, das sind Programmfehler.
- **`Turn.fallback`:** Pflicht bei `hint`, `guard` (zweiter Treffer) oder
  `llm_error` (Tutor hat nicht geantwortet), damit sich die beiden Gründe
  im Log trennen lassen.
- **Turns bauen, nicht schreiben:** `GuardedQuestion.turns(session, hook,
  ts)` gibt die Turns zurück, schreiben muss sie der Aufrufer
  (`core.logging.write_turn`, ab I-10 in der UI). So bleibt der Ablauf ohne
  Dateizugriff testbar.
- **Ablauf ausserhalb der UI:** `core/session.py` holt Fragen
  (`ask_question`), loggt Antworten (`log_answer`) und lässt bewerten
  (`grade_answer`). `app/main.py` zeigt nur an. So ist der Ablauf ohne
  Streamlit testbar, und jeder Turn wird an genau einer Stelle geloggt.
- **`MODE=llm|fixed`:** Standard ist `llm`, der eigentliche Prototyp. Fehlt
  die LLM-Konfiguration, zeigt die App eine Meldung mit dem Hinweis auf
  `MODE=fixed`. Nur `MODE=llm` loggt: Im fixen Modus passt `Turn` nicht (eine
  fixe Frage ist kein tutor-Turn, das Urteil der Testleitung kein
  grader-Turn), und die Logs sollen nur vergleichbare Daten enthalten.
- **`.env` in der App:** `app/main.py` lädt `.env` beim Start, damit auch
  `MODE` und `HOOK` dort stehen dürfen. Vorher wirkte `HOOK` nur als echte
  Umgebungsvariable.
- **Eine Frage pro Stufe:** Die Frage wird einmal pro Stufe erzeugt und in
  der Sitzung gemerkt, Reruns von Streamlit erzeugen keine neue. Ab Stufe 2
  bekommt der Tutor die letzte Antwort.
- **Grader antwortet nicht:** Die Antwort bleibt stehen, die Stufe ändert
  sich nicht. Die App zeigt eine verständliche Meldung (Details aufklappbar)
  und den Knopf «Erneut auswerten», ohne automatischen neuen Versuch. Die
  Antwort wird nur einmal geloggt (beim Absenden), der grader-Turn erst bei
  Erfolg.
- **Tutor antwortet nicht:** Der Leak Guard zeigt den Expert:innen-Hint
  (`fallback=llm_error`). Die App sagt dazu in einer Zeile, dass die Frage
  direkt von der Fachperson stammt.
- **Sitzung:** pro Browser-Sitzung eine zufällige ID (`s-` plus 8 Hex), sie
  bleibt beim Wechsel der Übung gleich. `hook` im Log ist der Arm aus `HOOK`.
- **App-Tests:** `tests/test_app.py` spielt die App mit Streamlits
  `AppTest` durch (LLM gemockt, Log in `tmp_path`). `streamlit` ist schon
  eine Abhängigkeit.
- **Probeskripte:** `scripts/try_prompts.py` (eingesetzte Prompts anzeigen,
  ohne LLM), `scripts/try_tutor.py` und `scripts/try_grader.py`
  (Plausibilitätschecks gegen den Proxy). Sie lesen die Config aus `.env`
  und sind nicht Teil von pytest. Ergebnisse in `docs/probelaeufe.md`.
- **Import-Pfad der App:** `streamlit run app/main.py` legt nur `app/` in den
  Suchpfad. `app/main.py` ergänzt deshalb den Repo-Hauptordner, damit
  `import core` funktioniert, auch auf Streamlit Community Cloud.
