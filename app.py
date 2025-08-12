import io
import os
import re
from typing import Optional

import pandas as pd
import streamlit as st

# PDF extractie
try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None  # type: ignore


def detect_insurer_name_from_text(text: str) -> Optional[str]:
    """Heuristische detectie van maatschappijnaam in de eerste pagina/regels."""
    snippet = text[:4000]
    lines = [l.strip() for l in snippet.splitlines() if l.strip()]

    known_brands = [
        "ASR", "Achmea", "Centraal Beheer", "Interpolis", "Allianz", "Aegon", "NN", "Nationale-Nederlanden",
        "Univé", "Inshared", "OHRA", "FBTO", "VGZ", "Zilveren Kruis", "Reaal", "de Goudse", "Klaverblad",
        "a.s.r.", "ASR Verzekeringen", "Allsecur", "ANWB Verzekeren"
    ]
    for l in lines[:40]:
        for brand in known_brands:
            if brand.lower() in l.lower():
                return brand

    # Algemene patronen: bedrijfsnaam + NV/BV/Verzekeringen
    company_pattern = re.compile(
        r"\b([A-Z][A-Za-z0-9&\-.,' ]{2,}?)(?:\s+(?:N\.?V\.?|B\.?V\.?|Verzekeringen|Schadeverzekeringen|Levensverzekeringen|Verzekeraar))\b",
        re.IGNORECASE,
    )
    for l in lines[:60]:
        m = company_pattern.search(l)
        if m:
            candidate = m.group(1).strip(" -,.')(")
            # voorkom te generieke woorden
            if len(candidate) >= 2 and not candidate.lower().startswith("polis"):
                return candidate
    return None


COMPARER_SYSTEM_PROMPT = (
    "Rol\n"
    "Jij bent een polisvoorwaardenvergelijker, gespecialiseerd in ASR en vergelijking met andere verzekeraars. Je werkt voor professionele gebruikers (intermediairs, acceptanten, schadebehandelaars).\n\n"
    "Doel\n"
    "Lever een volledige, letterlijke en gestructureerde vergelijking in TABELVORM tussen ASR en een andere verzekeraar. Geen samenvattingen of interpretaties: uitsluitend volledige inhoud per bepaling.\n\n"
    "Werkwijze (algemeen)\n"
    "1) Lees beide documenten volledig (ASR en Andere verzekeraar).\n"
    "2) Bepaal onderwerpen/artikelen op basis van de kop- en nummerstructuur in de teksten. Neem alle relevante onderwerpen op.\n"
    "3) Produceer één tabel met exact 4 kolommen:\n"
    "   - Onderwerp\n   - ASR\n   - Andere verzekeraar\n   - Verschillen\n"
    "4) Voeg als eerste rij toe: Onderwerp='Maatschappij', ASR='ASR', Andere verzekeraar='<gedetecteerde naam of onbekend>'.\n"
    "5) Na de tabel: geef een ‘Samenvatting en Slotanalyse’, daarna twee lijsten (‘Bijzonderheden alleen in ASR’ en ‘Bijzonderheden alleen in ANDER’), en sluit af met een ‘Eindconclusie over impact op de verzekeringspraktijk’.\n\n"
    "Inhoudsregels\n"
    "- In ‘ASR’ en ‘Andere verzekeraar’: ALTIJD de volledige, letterlijke tekst zoals in het document. Niet samenvatten.\n"
    "- Verboden: ‘idem’, ‘zelfde’, ‘zoals’, ‘zoals eerder’, ‘zoals onder meer’, ‘zoals bijvoorbeeld’, ‘o.a.’, ‘e.d.’, ‘gelijk aan’.\n"
    "- Als iets alleen in één document staat: zet in de andere kolom expliciet ‘Niet aanwezig in ASR’ of ‘Niet aanwezig in ANDER’ en citeer aan de aanwezige zijde volledig en letterlijk.\n"
    "- Uitsluitingen: ALLE punten afzonderlijk, puntsgewijs en letterlijk opnemen.\n"
    "- Waarderegelingen: ALTIJD volledig uitschrijven (bedragen, limieten, afschrijvingen, maxima, wachttijden, eigen risico’s).\n"
    "- Niet verwijzen naar andere artikelen; citeer relevante tekst hier integraal.\n\n"
    "Kolom ‘Verschillen’ (strikt)\n"
    "- Gebruik labels per onderdeel: [ADDED], [REMOVED], [CHANGED], [UNCHANGED].\n"
    "- Citeer steeds kort letterlijk (‘…’) wat verschilt of nieuw/weg is, met bedragen/limieten in cijfers.\n"
    "- Splits meerdere punten in sub-bullets of puntkomma’s. Geen interpretatie, alleen verifieerbare tekst.\n\n"
    "Output en export\n"
    "- Na de volledige weergave: geef exact dezelfde tabel ook als CSV in één codeblock met taal-tag csv (alleen de tabel, geen extra tekst).\n"
)

SIMPLE_SYSTEM_PROMPT = (
    "Je vergelijkt kort en duidelijk de inhoud van twee polisdocumenten (ASR vs Andere verzekeraar).\n"
    "Geef alleen de belangrijkste inhoudelijke verschillen in simpele bullets: dekking, uitsluitingen, limieten/bedragen, voorwaarden/wachttijden, plichten/meldingen, schadeafhandeling.\n"
    "- Vermijd tabellen en jargon.\n"
    "- Maximaal ~12 bullets, puntsgewijs.\n"
    "- Benoem per bullet het verschil en citeer kort een relevante zinsnede tussen aanhalingstekens indien nuttig.\n"
    "- Reageer in het Nederlands.\n"
)

# Aanvullende instructie om ook een compacte CSV-tabel te leveren, met maatschappij-rij en verschil-labels
SIMPLE_TABLE_ADDON = (
    "\n\nGeef daarnaast dezelfde verschillen in een compacte tabel met 4 kolommen (Onderwerp, ASR, Andere verzekeraar, Verschillen).\n"
    "- Voeg als eerste rij toe: Onderwerp='Maatschappij', ASR='ASR', Andere verzekeraar='<gedetecteerde naam of onbekend>'.\n"
    "- In kolom ‘Verschillen’ gebruik labels [ADDED]/[REMOVED]/[CHANGED]/[UNCHANGED] met korte letterlijke citaten en bedragen.\n"
    "Geef exact dezelfde tabel ook als CSV in één codeblock met taal-tag csv (alleen de tabel, geen extra tekst).\n"
)


def read_pdf_bytes(file_bytes: bytes) -> str:
    parts = []
    if fitz is not None:
        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                for page in doc:
                    parts.append(page.get_text("text"))
        except Exception:
            pass
    if not parts and pdfplumber is not None:
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    parts.append(page.extract_text() or "")
        except Exception:
            pass
    return "\n".join(parts)


def get_model_api_key() -> Optional[str]:
    # Prefer generieke sleutelnaam, met fallback voor compatibiliteit
    key = None
    try:
        key = st.secrets.get("AI_API_KEY")  # type: ignore
    except Exception:
        key = None
    if not key:
        try:
            key = st.secrets.get("OPENAI_API_KEY")  # type: ignore
        except Exception:
            key = None
    if not key:
        key = os.environ.get("AI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    return key


def extract_csv_block(text: str) -> Optional[str]:
    match = re.search(r"```csv\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def main():
    st.set_page_config(page_title="ASR vs Andere verzekeraar – AI polisvergelijker", layout="wide")
    st.title("ASR vs Andere verzekeraar – AI polisvergelijker")
    st.caption("Upload twee PDF's (ASR en andere verzekeraar). Kies ‘Simpel’ voor bullets of ‘Uitgebreid’ voor tabel+CSV.")

    col1, col2 = st.columns(2)
    with col1:
        file_asr = st.file_uploader("PDF – ASR", type=["pdf"], key="pdf_asr")
    with col2:
        file_other = st.file_uploader("PDF – Andere verzekeraar", type=["pdf"], key="pdf_other")

    mode = st.selectbox("Vergelijkingsmodus", ["Simpel (inhoud)", "Uitgebreid (tabel + CSV)"])
    want_table_simple = st.checkbox("Toon resultaat als tabel (ook bij Simpel)", value=True)
    max_chars = st.slider("Max. tekens per document", 5_000, 200_000, 40_000, step=5_000)

    st.sidebar.header("AI-instellingen")
    provided_key = st.sidebar.text_input("AI_API_KEY (laat leeg voor secrets/env)", type="password")
    effective_key = provided_key or get_model_api_key()
    model_name = "gpt-4o-mini"

    if OpenAI is None:
        st.sidebar.error("AI client niet gevonden. Installeer afhankelijkheden en herstart: pip install -r requirements.txt")
        return

    if st.button("Genereer AI-vergelijking", type="primary"):
        if not file_asr or not file_other:
            st.error("Upload zowel ASR als Andere verzekeraar.")
            return
        if not effective_key:
            st.error("Geen AI_API_KEY gevonden. Vul in of configureer via secrets/env.")
            return

        with st.spinner("PDF's lezen..."):
            text_asr = read_pdf_bytes(file_asr.read()).strip()
            text_other = read_pdf_bytes(file_other.read()).strip()

        if not text_asr or not text_other:
            st.error("Kon geen tekst uit een of beide PDF's extraheren. Probeer andere bestanden of hogere kwaliteit.")
            return

        other_name = detect_insurer_name_from_text(text_other)
        if other_name:
            st.info(f"Gedetecteerde maatschappij (Andere): {other_name}")

        def trunc(s: str) -> str:
            return s[: max_chars]

        if mode.startswith("Simpel"):
            system_prompt = SIMPLE_SYSTEM_PROMPT + (SIMPLE_TABLE_ADDON if want_table_simple else "")
            user_msg = (
                "Geef beknopt de belangrijkste verschillen."
                + (" Voeg ook de compacte tabel en CSV toe." if want_table_simple else "")
                + (f" Gebruik voor de maatschappij-rij indien mogelijk: '{other_name}'." if other_name else "")
                + "\n\n"
                f"ASR (ingekort):\n{trunc(text_asr)}\n\n"
                f"Andere verzekeraar (ingekort):\n{trunc(text_other)}\n"
            )
        else:
            system_prompt = COMPARER_SYSTEM_PROMPT
            user_msg = (
                "Vergelijk onderstaande polisvoorwaarden. Houd je strikt aan de system prompt.\n\n"
                + (f"Indien je de andere maatschappij kunt vaststellen, gebruik die in de eerste rij 'Maatschappij': '{other_name}'.\n\n" if other_name else "")
                + f"ASR (volledige tekst, mogelijk ingekort):\n{trunc(text_asr)}\n\n"
                + f"Andere verzekeraar (volledige tekst, mogelijk ingekort):\n{trunc(text_other)}\n"
            )

        client = OpenAI(api_key=effective_key)
        with st.spinner("AI-vergelijking genereren..."):
            try:
                resp = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.2 if mode.startswith("Simpel") else 0.1,
                )
                content = resp.choices[0].message.content or ""
            except Exception as e:
                st.error(f"Fout bij AI-aanroep: {e}")
                return

        st.subheader("AI-resultaat")
        st.markdown(content)

        # Tabelweergave via CSV, zowel in Uitgebreid als in Simpel (indien aangevinkt)
        if (not mode.startswith("Simpel")) or (mode.startswith("Simpel") and want_table_simple):
            csv_text = extract_csv_block(content)
            if csv_text:
                try:
                    df = pd.read_csv(io.StringIO(csv_text))
                    st.subheader("Tabel (CSV omgezet)")
                    st.dataframe(df, use_container_width=True)
                    st.download_button(
                        "Download tabel (CSV)",
                        data=csv_text.encode("utf-8"),
                        file_name="asr_vs_ander_vergelijking.csv",
                        mime="text/csv",
                    )
                except Exception:
                    st.info("Kon CSV-onderdeel niet parseren. Download of kopieer het CSV-codeblok handmatig.")
            else:
                st.info("Geen CSV-codeblok gedetecteerd in AI-output. Kies ‘Uitgebreid’ of laat de AI een tabel/CSV genereren.")

    st.caption("Snel: ‘Simpel (inhoud)’. Mooie tabel: vink ‘Toon resultaat als tabel’ aan of kies ‘Uitgebreid’.\nSecrets via Cloud instellen onder AI_API_KEY.")


if __name__ == "__main__":
    main()