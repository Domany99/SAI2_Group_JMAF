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
- **Status:** in `tutor_v2` umgesetzt (nicht Default), Probelauf v1 gegen v2 offen

### T4: Erklärungen für `new` erhöhen die Leak-Rate

- **Datum:** 20.11.2026, `tutor_v1`, `qwen3.8-27b`, Temperatur 0.7, ohne Cache
- **Beispiel:** Stufe 1, `strapi-auth-false`, `new`: «… welche konkreten Handlungen wie ein Eintrag anlegen, ändern oder löschen …» (Guard: «löschen», «ändern»). Derselbe Leak schon im Lauf davor.
- **Vermutete Ursache:** Die Ton-Regel für `new` verlangt, Begriffe zu erklären. Beim Erklären von «Aktionen» zählt das Modell die Aktionen auf, und damit genau die verbotenen Wörter.
- **Idee:** «Erkläre Begriffe, ohne Beispiele aus dem Code aufzuzählen.» Leak-Rate pro Einstufung in der Evaluation getrennt ausweisen.
- **Status:** in `tutor_v2` umgesetzt (nicht Default), Probelauf v1 gegen v2 offen

### T5: Tipps nennen Wörter, die der Hint vermeidet

- **Datum:** 20.11.2026, `tutor_v1`, `qwen3.8-27b`, Temperatur 0.7, ohne Cache
- **Beispiel:** Stufe 1, `xss-projektsuche`, `basics`: «(Tipp: … wo im HTML-Code der Begriff eingefügt wird.)» (Guard: «HTML»).
- **Vermutete Ursache:** Die Ton-Regel für `basics` verlangt «einen kurzen Hinweis, wo man nachschauen kann». Das Modell konkretisiert den Ort über den Hint hinaus.
- **Idee:** «Der Hinweis, wo man nachschaut, darf nicht konkreter sein als der Hint der Fachperson.»
- **Status:** in `tutor_v2` umgesetzt (nicht Default), Probelauf v1 gegen v2 offen

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
