# Prompts

Versionierte Prompt-Vorlagen für LLM 1 (Tutor) und LLM 2 (Grader). Geladen
werden sie mit `core.prompts.load_prompt(role, number)`, zum Beispiel
`load_prompt("tutor", 1)` für `tutor_v1.md`. `PromptTemplate.version`
(`"tutor_v1"`) kommt so ins Log (`Turn.prompt_version`).

## Versionen

| Datei | Default | Änderung gegenüber der Vorversion | Anlass |
|---|---|---|---|
| `tutor_v1.md` | nein (bis 23.11.2026 ja) | erste Version | I-06 |
| `grader_v1.md` | nein | erste Version | I-06 |
| `tutor_strict_v1.md` | ja | erste Version: Zusatz zum Tutor-Prompt für den zweiten Versuch nach einem Guard-Treffer, ohne Platzhalter | I-09 |
| `tutor_v2.md` | ja (seit 23.11.2026) | Abschnitt «Ton nach Vorwissen» geschärft: Grundsatz «nicht mehr nennen als der Hinweis, auch nicht als Erklärung, Beispiel oder Tipp»; `experienced` höchstens drei kurze Sätze, Feed up optional; `basics` nur das Werkzeug, nicht genauer als der Hint; `new` Begriffe allgemein erklären, keine Beispiele aus Code oder Übung aufzählen. Platzhalter wie v1. | Probeläufe vom 20.11.2026, Kandidaten T3, T4, T5 (`v2_candidates.md`). Default nach Läufen 7 und 8 (`docs/probelaeufe.md`) |
| `grader_v2.md` | nein (bis 24.11.2026 ja) | Regel «Ein Fix ohne Begründung des Problems ist partial» und ein passendes Beispiel. Sonst identisch mit v1. | Probelauf 3: «textContent statt innerHTML» wurde fälschlich `recognized` (`docs/probelaeufe.md`, Lauf 3 und 4) |
| `grader_v3.md` | ja (seit 24.11.2026) | Neuer Platzhalter `required` (Pflichtbausteine der Übung). «recognized» nur, wenn alle Bausteine sinngemäss enthalten sind; fehlt einer, ist es «partial». Ähnlichkeit mit einer akzeptierten Antwort allein reicht nicht mehr. Beispiele mit Pflichtbausteinen und ein neues Beispiel «Kern ohne Folge = partial». Sonst wie v2. | Probelauf 9: zwei falsche `recognized` (G2, G3 in `v2_candidates.md`). Default nach Lauf 12: 16 von 16 Probefällen wie erwartet |

Beobachtungen für weitere Versionen sammelt `v2_candidates.md`.

## Regeln

- Dateiname `<role>_v<n>.md`, Rolle `tutor`, `grader` oder `tutor_strict`,
  `n` ab 1 ohne führende Null.
- `tutor_strict_v<n>.md` wird nach einem Guard-Treffer unverändert an den
  eingesetzten Tutor-Prompt angehängt (`core.leak_guard`). Es nennt keine
  getroffenen Wörter. Im Log steht beim zweiten Versuch weiterhin
  `prompt_version=tutor_v<n>` mit `attempt=2`; der Zusatz ändert den
  `prompt_hash`. Die Version wählt `TUTOR_STRICT_VERSION`.
- **Eine Version, die in einem Eval-Lauf verwendet wurde, wird nie mehr
  bearbeitet.** Für Änderungen eine neue Datei `<role>_v<n+1>.md` anlegen.
- Nach dem ersten Eval-Lauf mit einer Version diese in `frozen.txt`
  eintragen. Ein Test schlägt dann fehl, sobald sich die Datei ändert:

  ```bash
  python -c "from core.prompts import prompt_hash, PROMPTS_DIR; print(prompt_hash(PROMPTS_DIR / 'tutor_v1.md'), ' tutor_v1.md')" >> prompts/frozen.txt
  ```

- Die ganze Datei ist der System-Prompt. Was hier steht, sieht das Modell.
- Antworten der Studierenden kommen **nie** in die Vorlage, sondern als
  eigene User-Nachricht (Schutz vor Prompt Injection).
- Gelabelte Grader-Beispiele dürfen nicht aus `eval/data/` stammen und nicht
  aus einer Übung in `exercises/`, sonst ist die Evaluation verzerrt. Die
  Beispiele in `grader_v1.md` und `grader_v2.md` nutzen eine erfundene Übung
  (Passwort-Reset über `?user=42`, Decoy bcrypt). Wird daraus je eine echte
  Übung, braucht der Grader eine neue Version mit anderen Beispielen.

## Platzhalter

Syntax: `{{name}}`, der Name besteht aus Kleinbuchstaben, Ziffern und `_`
und beginnt mit einem Buchstaben. Doppelte Klammern, weil die Prompts JSON
mit einfachen `{}` enthalten. Andere doppelte Klammern sind beim Laden ein
Fehler. Escaping gibt es nicht.

`PromptTemplate.render(values)` ist streng: Fehlt ein Wert oder kommt einer
ohne Platzhalter dazu, gibt es einen `PromptError`. Eingesetzte Werte werden
nicht erneut ersetzt.

### `tutor_v1.md` und `tutor_v2.md`

| Platzhalter | Inhalt | Quelle |
|---|---|---|
| `stage` | `1`, `2` oder `3` | Stufen-Logik |
| `goal` | Ziel der Stufe | `tutor_context(stage)["goal"]` |
| `hint` | Expert:innen-Hint der Stufe | `tutor_context(stage)["hint"]` |
| `prior_knowledge` | `new`, `basics` oder `experienced` | `PriorKnowledge` |
| `examples` | Hints **derselben Stufe aus anderen Übungen**, eine Zeile pro Hint als `- «…»` | `core/tutor.py` (I-07) |

User-Nachricht (nicht in der Vorlage): ab Stufe 2 die letzte Antwort der
Person, sonst eine kurze Aufforderung, die Frage zu stellen.

### `grader_v1.md` bis `grader_v3.md`

| Platzhalter | Inhalt | Quelle |
|---|---|---|
| `decoy` | `ja` oder `nein` | `Exercise.decoy` |
| `issue` | Kern des Problems (bei Decoys: warum der Code in Ordnung ist) | `answer_key.issue` |
| `consequence` | Folge | `answer_key.consequence` |
| `accepted` | eine Zeile pro Antwort als `- …` | `answer_key.accepted` |
| `misconceptions` | eine Zeile pro Fehlannahme als `- <id>: <belief>`, ohne Einträge `keine` | `Exercise.misconceptions` |
| `required` | nur v3: eine Zeile pro Pflichtbaustein als `- …`, ohne Einträge ein Hinweis «keine angegeben» | `answer_key.required` |

User-Nachricht (nicht in der Vorlage): die Antwort der Person. Der Grader
bekommt die Einstufung des Vorwissens **nicht** (I-08, Vergleich H11).
