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
    "4) Na de tabel: geef een ‘Samenvatting en Slotanalyse’, daarna twee lijsten (‘Bijzonderheden alleen in ASR’ en ‘Bijzonderheden alleen in ANDER’), en sluit af met een ‘Eindconclusie over impact op de verzekeringspraktijk’.\n\n"
    "Inhoudsregels\n"
    "- In ‘ASR’ en ‘Andere verzekeraar’: ALTIJD de volledige, letterlijke tekst zoals in het document. Niet samenvatten.\n"
    "- Verboden: ‘idem’, ‘zelfde’, ‘zoals’, ‘zoals eerder’, ‘zoals onder meer’, ‘zoals bijvoorbeeld’, ‘o.a.’, ‘e.d.’, ‘gelijk aan’.\n"
    "- Als iets alleen in één document staat: zet in de andere kolom expliciet ‘Niet aanwezig in ASR’ of ‘Niet aanwezig in ANDER’ en citeer aan de aanwezige zijde volledig en letterlijk.\n"
    "- Uitsluitingen: ALLE punten afzonderlijk, puntsgewijs en letterlijk opnemen.\n"
    "- Waarderegelingen: ALTIJD volledig uitschrijven (bedragen, limieten, afschrijvingen, maxima, wachttijden, eigen risico’s).\n"
    "- Niet verwijzen naar andere artikelen; citeer relevante tekst hier integraal.\n\n"
    "Outputformat (strikt)\n"
    "- Eén tabel met de kolommen: Onderwerp | ASR | Andere verzekeraar | Verschillen.\n"
    "- In ‘Verschillen’: benoem concreet, letterlijk wat afwijkt (bijv. ‘ASR bevat uitsluiting X: “…”’; ‘Ander bevat limiet €…’).\n"
    "- Na de tabel, geef in deze volgorde:\n  A) Samenvatting en Slotanalyse\n  B) Bijzonderheden alleen in ASR\n  C) Bijzonderheden alleen in ANDER\n  D) Eindconclusie over impact op verzekeringspraktijk.\n\n"
    "Belangrijk\n"
    "- Wanneer een onderwerp niet voorkomt: zet ‘Niet aanwezig in ASR’ of ‘Niet aanwezig in ANDER’.\n"
    "- Behoud opsommingen/nummering waar mogelijk.\n"
    "- Reageer altijd in het Nederlands.\n"
    "- Geen juridisch advies of interpretatie; uitsluitend letterlijke vergelijking en feitelijke vaststelling.\n\n"
    "Extra instructie voor export\n"
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

# Aanvullende instructie om ook een compacte CSV-tabel te leveren
SIMPLE_TABLE_ADDON = (
    "\n\nGeef daarnaast dezelfde verschillen in een compacte tabel met 4 kolommen (Onderwerp, ASR, Andere verzekeraar, Verschillen).\n"
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

        def trunc(s: str) -> str:
            return s[: max_chars]

        if mode.startswith("Simpel"):
            system_prompt = SIMPLE_SYSTEM_PROMPT + (SIMPLE_TABLE_ADDON if want_table_simple else "")
            user_msg = (
                "Geef beknopt de belangrijkste verschillen."
                + (" Voeg ook de compacte tabel en CSV toe." if want_table_simple else "")
                + "\n\n"
                f"ASR (ingekort):\n{trunc(text_asr)}\n\n"
                f"Andere verzekeraar (ingekort):\n{trunc(text_other)}\n"
            )
        else:
            system_prompt = COMPARER_SYSTEM_PROMPT
            user_msg = (
                "Vergelijk onderstaande polisvoorwaarden. Houd je strikt aan de system prompt.\n\n"
                f"ASR (volledige tekst, mogelijk ingekort):\n{trunc(text_asr)}\n\n"
                f"Andere verzekeraar (volledige tekst, mogelijk ingekort):\n{trunc(text_other)}\n"
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