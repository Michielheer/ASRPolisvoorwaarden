### ASR AI polisvergelijker (AI-only)

Deze Streamlit-app vergelijkt polisvoorwaarden van ASR met die van een andere verzekeraar via een AI-model. De vergelijking is volledig AI-gedreven: geen lokale diff, maar een tabel met letterlijke teksten en verschillen, plus samenvatting en CSV-export.

## Functionaliteit
- Upload 2 PDF’s: `ASR` en `Andere verzekeraar`.
- AI produceert één tabel: Onderwerp | ASR | Andere verzekeraar | Verschillen.
- Na de tabel: Samenvatting en slotanalyse, Bijzonderheden alleen in ASR, Bijzonderheden alleen in ANDER, Eindconclusie.
- Probeert tevens de tabel als CSV in de output te geven; deze kun je downloaden.

## Vereisten
- Python 3.9+ aanbevolen
- Een geldige AI API key voor het gebruikte model

## Installatie
```bash
cd "/Users/michielheerkens/Desktop/Hoi/ASRPolisvoorwaarden"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Secrets (veilig)
- Zet je sleutel lokaal in `.streamlit/secrets.toml` (dit staat in `.gitignore`):
```toml
AI_API_KEY = "PLAATS_HIER_DE_SLEUTEL"
```
- Alternatief: exporteer als omgevingsvariabele:
```bash
export AI_API_KEY="PLAATS_HIER_DE_SLEUTEL"
```

## Starten
```bash
streamlit run app.py
```
Open de app in de browser: `http://localhost:8501`.

## Gebruik
1) Upload twee PDF’s (ASR en Andere verzekeraar).
2) Kies modus: Simpel (bullets) of Uitgebreid (tabel + CSV), en optioneel “Toon resultaat als tabel”.
3) Klik “Genereer AI-vergelijking”.
4) Bekijk de resultaten. Indien de AI een CSV-codeblok teruggeeft, kun je deze direct downloaden in de app.

## CSV-export
- De app probeert automatisch een ```csv codeblok uit de AI-output te extraheren. Als dit lukt, zie je een downloadknop.
- Lukt het niet, kopieer het CSV-codeblok handmatig uit de AI-output.

## Veilig naar GitHub pushen
Deze repo is voorbereid om je sleutel niet te lekken:
- `.streamlit/secrets.toml` staat in `.gitignore` en wordt niet gecommit.
- Een voorbeeldbestand staat klaar: `.streamlit/secrets.example.toml`.

Push instructies:
```bash
git remote add origin git@github.com:<jouw-user>/<jouw-repo>.git
git push -u origin main
```
Op andere machines vul je lokaal `.streamlit/secrets.toml` in aan de hand van `secrets.example.toml`.

## Troubleshooting
- “Kon geen tekst uit PDF extraheren”: probeer een betere scan of tekstgebaseerde PDF (geen afbeelding). OCR is optioneel toe te voegen.
- “Geen AI_API_KEY gevonden”: voeg je sleutel toe in `.streamlit/secrets.toml` of als env var.
- Voor performance tijdens development: installeer Watchdog (macOS):
```bash
xcode-select --install
pip install watchdog
```

## Disclaimer
Resultaten zijn AI-gegenereerd en moeten door professionals worden gevalideerd.
