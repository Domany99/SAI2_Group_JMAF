# Prompts

Versionierte Prompt-Vorlagen für LLM 1 (Tutor) und LLM 2 (Grader). Geladen
werden sie mit `core.prompts.load_prompt(role, number)`, zum Beispiel
`load_prompt("tutor", 1)` für `tutor_v1.md`. `PromptTemplate.version`
(`"tutor_v1"`) kommt so ins Log (`Turn.prompt_version`).

## Regeln

- Dateiname `<role>_v<n>.md`, Rolle `tutor` oder `grader`, `n` ab 1 ohne
  führende Null.
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
  Beispiele in `grader_v1.md` nutzen eine erfundene Übung
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

### `tutor_v1.md`

| Platzhalter | Inhalt | Quelle |
|---|---|---|
| `stage` | `1`, `2` oder `3` | Stufen-Logik |
| `goal` | Ziel der Stufe | `tutor_context(stage)["goal"]` |
| `hint` | Expert:innen-Hint der Stufe | `tutor_context(stage)["hint"]` |
| `prior_knowledge` | `new`, `basics` oder `experienced` | `PriorKnowledge` |
| `examples` | Hints **derselben Stufe aus anderen Übungen**, eine Zeile pro Hint als `- «…»` | `core/tutor.py` (I-07) |

User-Nachricht (nicht in der Vorlage): ab Stufe 2 die letzte Antwort der
Person, sonst eine kurze Aufforderung, die Frage zu stellen.

### `grader_v1.md`

| Platzhalter | Inhalt | Quelle |
|---|---|---|
| `decoy` | `ja` oder `nein` | `Exercise.decoy` |
| `issue` | Kern des Problems (bei Decoys: warum der Code in Ordnung ist) | `answer_key.issue` |
| `consequence` | Folge | `answer_key.consequence` |
| `accepted` | eine Zeile pro Antwort als `- …` | `answer_key.accepted` |
| `misconceptions` | eine Zeile pro Fehlannahme als `- <id>: <belief>`, ohne Einträge `keine` | `Exercise.misconceptions` |

User-Nachricht (nicht in der Vorlage): die Antwort der Person. Der Grader
bekommt die Einstufung des Vorwissens **nicht** (I-08, Vergleich H11).
