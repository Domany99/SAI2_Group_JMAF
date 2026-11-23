# Kandidaten für neue Prompt-Versionen

Beobachtungen aus Probeläufen, die eine neue Prompt-Version rechtfertigen
könnten. Ein Eintrag ist noch kein Entscheid: Ob sich eine Änderung lohnt,
zeigt erst die Evaluation mit gelabelten Daten (I-13, I-14). Einzelne
Probeläufe sind Stichproben (n = 1 pro Fall).

Pro Eintrag: Datum, Prompt-Version, Beispiel, vermutete Ursache, Status.
Läufe vor dem 20.11.2026 (I-18) kamen teilweise aus dem Cache des Proxys.

## Tutor

### T1: Der Tutor lobt

- **Datum:** 20.11.2026, `tutor_v1`, `qwen3.8-27b`, Temperatur 0.7
- **Beispiel:** Stufe 2, `api-key-frontend`, `new`: «Das ist eine gute Beobachtung zum Client-Code im Allgemeinen.»
- **Vermutete Ursache:** Die Feed-back-Regel sagt «Würdige die Beobachtung». Das Modell liest «würdigen» als «loben». Die Regel gegen Bewertungen nennt Lob nur indirekt.
- **Idee:** «Würdigen» durch «aufgreifen» ersetzen und Lob ausdrücklich verbieten («nicht loben, nicht ‹gut›, ‹richtig›, ‹genau›»).
- **Status:** offen

### T2: Der Tutor bewertet die Antwort

- **Datum:** 20.11.2026, `tutor_v1`, `qwen3.8-27b`, Temperatur 0.7
- **Beispiel:** Stufe 2, `xss-projektsuche`, `basics`: «Du hast den Weg erkannt: der Suchbegriff kommt aus dem Link …». Ähnlich bei `api-key-frontend`, `experienced`: «Hier geht es aber nicht um den Code selbst, sondern …» (wertet die Antwort als daneben).
- **Vermutete Ursache:** Feed back verlangt einen Bezug auf die Antwort. Das Modell trennt «aufgreifen» und «bewerten» nicht. «erkannt» klingt nach «richtig».
- **Idee:** Beispiele für neutrales Aufgreifen in den Prompt («Du schreibst, dass …», «Du vermutest …»).
- **Status:** offen

### T3: Bei `experienced` mehr als zwei Sätze

- **Datum:** 20.11.2026, `tutor_v1`, `qwen3.8-27b`, Temperatur 0.7
- **Beispiel:** Stufe 2, `api-key-frontend`, `experienced`: drei Sätze («Dass der Quellcode … Hier geht es aber … Öffne den Netzwerk-Tab …»).
- **Vermutete Ursache:** Feed back, Feed up und Feed forward sind drei Teile; bei `experienced` passen sie nicht in zwei Sätze. Die Regeln widersprechen sich.
- **Idee:** Bei `experienced` Feed up weglassen oder die Grenze auf «höchstens drei kurze Sätze» setzen.
- **Status:** in `tutor_v2` umgesetzt, seit 23.11.2026 Default. Probeläufe 7 und 8: in v2 nicht mehr aufgetreten (n = 1 pro Fall, erster Hinweis)

### T4: Erklärungen für `new` erhöhen die Leak-Rate

- **Datum:** 20.11.2026, `tutor_v1`, `qwen3.8-27b`, Temperatur 0.7, ohne Cache
- **Beispiel:** Stufe 1, `strapi-auth-false`, `new`: «… welche konkreten Handlungen wie ein Eintrag anlegen, ändern oder löschen …» (Guard: «löschen», «ändern»). Derselbe Leak schon im Lauf davor.
- **Vermutete Ursache:** Die Ton-Regel für `new` verlangt, Begriffe zu erklären. Beim Erklären von «Aktionen» zählt das Modell die Aktionen auf, und damit genau die verbotenen Wörter.
- **Idee:** «Erkläre Begriffe, ohne Beispiele aus dem Code aufzuzählen.» Leak-Rate pro Einstufung in der Evaluation getrennt ausweisen.
- **Status:** in `tutor_v2` umgesetzt, seit 23.11.2026 Default. Probeläufe 7 und 8: in v2 nicht mehr aufgetreten (n = 1 pro Fall, erster Hinweis)

### T5: Tipps nennen Wörter, die der Hint vermeidet

- **Datum:** 20.11.2026, `tutor_v1`, `qwen3.8-27b`, Temperatur 0.7, ohne Cache
- **Beispiel:** Stufe 1, `xss-projektsuche`, `basics`: «(Tipp: … wo im HTML-Code der Begriff eingefügt wird.)» (Guard: «HTML»).
- **Vermutete Ursache:** Die Ton-Regel für `basics` verlangt «einen kurzen Hinweis, wo man nachschauen kann». Das Modell konkretisiert den Ort über den Hint hinaus.
- **Idee:** «Der Hinweis, wo man nachschaut, darf nicht konkreter sein als der Hint der Fachperson.»
- **Status:** in `tutor_v2` umgesetzt, seit 23.11.2026 Default. Probeläufe 7 und 8: in v2 nicht mehr aufgetreten (n = 1 pro Fall, erster Hinweis)

### T6: Der Tutor übernimmt Inhalte aus den Few-Shot-Beispielen

- **Datum:** 23.11.2026, `tutor_v1`, Temperatur 0.7, ohne Cache (Lauf 7)
- **Beispiel:** Stufe 1, `kommentare-bereinigt`, `basics`: «Folge dem Datenfluss von der Route über die Komponente bis zum Template». Im Code der Übung gibt es keine Route, das Wort stammt aus dem Hint von `strapi-auth-false` («Schau in die Route»).
- **Vermutete Ursache:** Die Regel «Übernimm keine Inhalte daraus» reicht nicht. Beim Decoy kommt dazu, dass alle Beispiele aus Übungen mit Lücke stammen.
- **Idee:** Decoys nur Beispiele aus Decoys geben (betrifft `core/tutor.py`, `few_shot_examples`), oder die Beispiele auf die Fragestruktur kürzen.
- **Status:** offen. In Lauf 8 (`tutor_v2`) nicht aufgetreten, das sagt bei n = 1 nichts.

### T7: Fachlich falsche Erklärung bei `new`

- **Datum:** 23.11.2026, `tutor_v2`, Temperatur 0.7, ohne Cache (Lauf 8)
- **Beispiel:** Stufe 1, `kommentare-bereinigt`, `new`: «… mit einer sogenannten v-html-Anweisung ausgegeben, was bedeutet, dass der Text so angezeigt wird, wie er als HTML-Code geschrieben ist, also mit allen Schrägstrichen und Klammern, die er enthält.» Das beschreibt `{{ }}`, nicht `v-html`. In Lauf 7 (`tutor_v1`) war die Erklärung richtig.
- **Vermutete Ursache:** Die Ton-Regel für `new` verlangt Erklärungen. Jede freie Erklärung kann falsch sein, und der Leak Guard prüft nur Wörter, nicht die Richtigkeit. Trifft die Gruppe, die den Fehler am wenigsten erkennt; beim Decoy lenkt er zudem in die falsche Richtung.
- **Idee:** Bei `new` nur Werkzeuge erklären (Entwicklertools, Netzwerk-Tab), nicht wie der Code funktioniert, denn das ist Teil der Aufgabe. In der menschlichen Bewertung (I-13/I-14) ein Kriterium «fachlich korrekt» ergänzen.
- **Status:** offen

### T8: Der Tutor bietet die Antwort als Auswahl an

- **Datum:** 23.11.2026, `tutor_v2`, Temperatur 0.7, ohne Cache (Lauf 8)
- **Beispiel:** Stufe 1, `xss-projektsuche`, `new`: «Wer bestimmt, was in diesem Suchbegriff steht – du selbst, Lea, oder könnte es auch jemand anderes sein». Stufe 1, `strapi-auth-false`, `new`: «… und welche hat die KI zusätzlich erlaubt?» (setzt voraus, dass zu viel offen ist).
- **Vermutete Ursache:** Beim ausführlicheren Formulieren konkretisiert das Modell die offene Frage des Hints mit möglichen Antworten. Kein verbotenes Wort, also kein Guard-Treffer.
- **Idee:** Regel «Biete keine möglichen Antworten an und unterstelle kein Ergebnis.»
- **Status:** offen

### Beobachtung: Floskel im Feed up

- **Datum:** 23.11.2026, `tutor_v2` (Lauf 8)
- **Beispiel:** 8 von 12 Fragen beginnen mit «Dieser Schritt schaut …» oder «Dieser Schritt geht darum …».
- **Idee:** Feed up nicht mit «Dieser Schritt» beginnen lassen oder in die Frage einbauen. Niedrige Priorität, wirkt erst über mehrere Übungen mechanisch.
- **Status:** offen

## Grader

### G1: «Irgendwas mit der URL?» schwankt zwischen `not` und `partial`

- **Datum:** 20.11.2026, `gpt-oss:120b`, Temperatur 0.0 bzw. 0.1
- **Beispiel:** `api-key-frontend`. `grader_v1`: erst `not` (vermutlich aus dem Cache), dann `partial` (ohne Cache). `grader_v2`: `not` (ohne Cache).
- **Vermutete Ursache:** Die Antwort ist eine vage Vermutung, die auf die richtige Stelle zeigt (der Key steht in der URL). Die Rubrik unterscheidet «zeigt in die richtige Richtung» (`partial`) und «hat nichts mit dem Kern zu tun» (`not`) nicht scharf genug für Ein-Wort-Vermutungen. Trotz Temperatur 0 nicht stabil.
- **Idee:** Beispiel in der erfundenen Übung ergänzen: vage Vermutung zur richtigen Stelle = `partial`.
- **Status:** offen

### G2: Fix, der die Lücke implizit benennt

- **Datum:** 20.11.2026, `grader_v1` und `grader_v2`, `gpt-oss:120b`, Temperatur 0.0, ohne Cache
- **Beispiel:** `strapi-auth-false`: «Man sollte auth: false entfernen und nur create freigeben.» ergibt in v1 und v2 `recognized`.
- **Vermutete Ursache:** «nur create freigeben» sagt indirekt, dass die anderen Aktionen zu viel sind. Das Modell wertet das als Kern. Ob das reicht, ist eine fachliche Frage, keine des Prompts (siehe Frage an die Fachperson «Reicht ein Fix allein?»).
- **Status:** wartet auf die Fachperson

### Erledigt: Fix ohne Begründung wird `recognized`

- **Datum:** 20.11.2026, `grader_v1`
- **Beispiel:** `xss-projektsuche`: «Man sollte textContent statt innerHTML nehmen.» ergibt `recognized`, obwohl weder die Quelle (Link) noch die Folge genannt sind.
- **Status:** in `grader_v2` umgesetzt (Regel «Ein Fix ohne Begründung des Problems ist partial» plus Beispiel). Probelauf mit v2: `partial`.
