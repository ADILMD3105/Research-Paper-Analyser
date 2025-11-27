import streamlit as st
import pdfplumber
import os
import re
import cohere
import json
from dotenv import load_dotenv

# --- Load API Key ---
load_dotenv()
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
COHERE_MODEL = "command-a-03-2025"

# --- Initialize Cohere ---
co = cohere.Client(COHERE_API_KEY) if COHERE_API_KEY else None


# ---------- Utilities ----------
DOI_RE = re.compile(r'\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b', re.IGNORECASE)
URL_RE = re.compile(r'https?://\S+', re.IGNORECASE)


def clean_ai_json(text: str) -> str:
    """Strip common AI formatting around JSON (code fences, leading text)."""
    if not text:
        return ""
    s = text.strip()
    # Remove common leading explanations
    # Keep removing until it looks like JSON
    # Remove code fences
    s = s.replace("```json", "").replace("```", "")
    # Remove any leading text before the first { or [
    idx = min([i for i in (s.find("{"), s.find("[")) if i != -1], default=-1)
    if idx > 0:
        s = s[idx:]
    return s.strip()


def regex_fallback_metadata(text: str) -> dict:
    """Try to guess metadata via regex heuristics if AI JSON fails."""
    metadata = {"title": "", "authors": "", "journal": "", "year": "", "doi": ""}

    # Extract DOI
    m = DOI_RE.search(text)
    if m:
        metadata["doi"] = m.group(0)

    # Extract year (first 1900-2099 occurrence)
    ym = re.search(r'\b(19|20)\d{2}\b', text)
    if ym:
        metadata["year"] = ym.group(0)

    # Heuristic title: often the first non-empty line and longer than 5 words
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        # Try first few lines for a likely title: pick the longest early line
        candidate_title = ""
        for ln in lines[:8]:
            word_count = len(ln.split())
            if word_count >= 3 and word_count > len(candidate_title.split()):
                candidate_title = ln
        metadata["title"] = candidate_title or lines[0]

    # Heuristic authors: often the line after title, contains commas or ' and ' or initials
    if metadata["title"]:
        try:
            title_index = lines.index(metadata["title"])
            if title_index + 1 < len(lines):
                possible_authors = lines[title_index + 1]
                # Filter out lines that look like affiliations (contain 'university', 'department', '@' or 'lab')
                if not re.search(r'university|dept|department|@|institute|laboratory|school', possible_authors, re.I):
                    metadata["authors"] = possible_authors
        except ValueError:
            pass

    # Journal heuristics: look for common words like 'Proceedings', 'Journal', 'Conference', 'Transactions'
    for ln in lines[:120]:
        if re.search(r'\b(Journal|Proceedings|Conference|Transactions|IEEE|ACM|Springer|Elsevier)\b', ln, re.I):
            metadata["journal"] = ln
            break

    # Clean up whitespaces
    for k in metadata:
        metadata[k] = metadata[k].strip()

    return metadata


# ---------- PDF text extraction ----------
@st.cache_data(show_spinner=False)
def extract_text_from_pdf(uploaded_file):
    text = ""
    # pdfplumber accepts either a file-like object or a path
    try:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        # If pdfplumber fails, return empty string
        return ""
    return text.strip()


# ---------- Cohere API calls ----------
@st.cache_data(show_spinner=False)
def call_cohere_cached(prompt, max_tokens=600):
    if not co:
        return "❌ Cohere API key missing. Set COHERE_API_KEY in your .env."
    try:
        response = co.chat(
            message=prompt,
            model=COHERE_MODEL,
            temperature=0.5,
            max_tokens=max_tokens
        )
        return response.text
    except Exception as e:
        return f"❌ API Error: {e}"


@st.cache_data(show_spinner=False)
def extract_metadata_ai(text):
    """
    Ask the AI to return EXACT JSON with fields title/authors/journal/year/doi.
    We'll clean and parse it; if it fails we fallback to regex heuristics.
    """
    if not co:
        return json.dumps({"title": "", "authors": "", "journal": "", "year": "", "doi": ""})

    prompt = f"""
Extract the research paper metadata from the following text.
Return output in EXACT JSON format (no surrounding explanation) with these keys:
"title", "authors", "journal", "year", "doi".

If something is missing, return an empty string for that field.
Only return JSON.

TEXT:
{text[:5000]}
"""
    try:
        response = co.chat(
            message=prompt.strip(),
            model=COHERE_MODEL,
            temperature=0.1,
            max_tokens=400
        )
        raw = response.text or ""
    except Exception:
        raw = ""

    clean = clean_ai_json(raw)
    # Try parse
    try:
        parsed = json.loads(clean)
        # Ensure only expected keys exist
        metadata = {
            "title": parsed.get("title", "").strip() if isinstance(parsed.get("title", ""), str) else "",
            "authors": parsed.get("authors", "").strip() if isinstance(parsed.get("authors", ""), str) else "",
            "journal": parsed.get("journal", "").strip() if isinstance(parsed.get("journal", ""), str) else "",
            "year": str(parsed.get("year", "")).strip() if parsed.get("year", "") is not None else "",
            "doi": parsed.get("doi", "").strip() if isinstance(parsed.get("doi", ""), str) else "",
        }
        return json.dumps(metadata)
    except Exception:
        # Fallback: try to extract basic fields via regex heuristics
        metadata = regex_fallback_metadata(text)
        return json.dumps(metadata)


# ---------- Improved citation extraction ----------
def extract_citations(text):
    """
    Return a dict with:
      - 'citations': list of bracketed or author-year citations found
      - 'dois': list of DOIs found
      - 'reference_lines': last section lines that look like references (heuristic)
    """
    citation_patterns = [
        r"\[\d+\]",                                 # [1]
        r"\(\d+\)",                                 # (1)
        r"\([A-Z][A-Za-z]+ et al\.,? \d{4}\)",      # (Smith et al., 2020)
        r"\([A-Z][A-Za-z]+ and [A-Z][A-Za-z]+, \d{4}\)",  # (Smith and John, 2020)
        r"\([A-Z][A-Za-z]+, \d{4}\)",               # (Smith, 2020)
        r"\b\d{4}\b"                                # Years
    ]
    all_matches = []
    for p in citation_patterns:
        all_matches.extend(re.findall(p, text))
    # DOIs and URLs
    dois = list(set(DOI_RE.findall(text)))
    urls = list(set(URL_RE.findall(text)))

    # Heuristic to extract reference section lines
    refs = []
    m = re.search(r'(references|bibliography|reference list|works cited)', text, re.I)
    if m:
        # take text from that match to end, split lines
        tail = text[m.start():]
        lines = [ln.strip() for ln in tail.splitlines() if ln.strip()]
        # pick lines that look like reference entries (contain year or DOI or multiple authors or title quotes)
        for ln in lines[:400]:
            if re.search(r'\b\d{4}\b', ln) or DOI_RE.search(ln) or re.search(r'\".+\"|\'.+\'', ln):
                refs.append(ln)
            else:
                # also accept long lines with commas and periods (likely ref)
                if len(ln) > 40 and (ln.count(",") >= 2 or ln.count(".") >= 2):
                    refs.append(ln)
    else:
        # fallback: last 4000 chars split lines
        tail = text[-4000:]
        lines = [ln.strip() for ln in tail.splitlines() if ln.strip()]
        for ln in lines[-200:]:
            if DOI_RE.search(ln) or re.search(r'\b\d{4}\b', ln):
                refs.append(ln)

    return {
        "citations": sorted(set(all_matches)),
        "dois": dois,
        "urls": urls,
        "reference_lines": refs
    }


# ---------- Streamlit UI ----------
st.set_page_config(page_title="📘 Advanced Research Paper Analyzer", layout="wide")
st.title("📘 AI Research Paper Analyzer")

st.markdown(
    "Upload a research paper PDF. The app extracts text, then attempts to extract clean metadata (title, authors, journal, year, DOI), citations, summaries, and more."
)

uploaded_file = st.file_uploader("📤 Upload PDF", type=["pdf"])

if uploaded_file:
    with st.spinner("Extracting text from PDF..."):
        text = extract_text_from_pdf(uploaded_file)

    if not text or len(text) < 80:
        st.warning("PDF seems empty or scanned (image-based). Try another file or run OCR first.")
    else:
        st.success("✅ PDF text extracted successfully!")

        if st.checkbox("📜 Show extracted text"):
            st.text_area("Extracted Text", text, height=300)

        # Tabs
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📄 Metadata",
            "📝 Summary",
            "🔍 Key Findings",
            "❓ Critical Questions",
            "📚 Terminology",
            "📖 Citations"
        ])

        # ---------- TAB 1: METADATA ----------
        with tab1:
            st.subheader("📄 Extracted Paper Metadata")

            with st.spinner("Extracting metadata using AI (and heuristics)..."):
                metadata_json = extract_metadata_ai(text)

            # Clean AI JSON formatting
            metadata_json_clean = clean_ai_json(metadata_json)

            # Try parse; if fail, fallback to regex heuristics
            try:
                metadata = json.loads(metadata_json_clean)
                # Ensure keys exist
                metadata = {
                    "title": (metadata.get("title") or "").strip(),
                    "authors": (metadata.get("authors") or "").strip(),
                    "journal": (metadata.get("journal") or "").strip(),
                    "year": str(metadata.get("year") or "").strip(),
                    "doi": (metadata.get("doi") or "").strip(),
                }
                # If everything blank, run regex fallback
                if not any(metadata.values()):
                    metadata = regex_fallback_metadata(text)

            except Exception:
                # Fallback to regex heuristics
                metadata = regex_fallback_metadata(text)

            # Display metadata nicely
            st.subheader("📄 Paper Metadata")
            st.write(f"**Title:** {metadata.get('title') or 'N/A'}")
            st.write(f"**Authors:** {metadata.get('authors') or 'N/A'}")
            st.write(f"**Journal/Conference:** {metadata.get('journal') or 'N/A'}")
            st.write(f"**Year:** {metadata.get('year') or 'N/A'}")
            st.write(f"**DOI:** {metadata.get('doi') or 'N/A'}")

            # Offer a JSON view + download
            st.subheader("🧾 Full Metadata (JSON)")
            st.json(metadata)
            st.download_button("Download metadata as JSON", data=json.dumps(metadata, indent=2), file_name="metadata.json", mime="application/json")

        # ---------- TAB 2: SUMMARY ----------
        with tab2:
            st.subheader("🧾 Summary (200–250 words)")
            if st.button("Generate Summary"):
                if not co:
                    st.error("Cohere key missing. Set COHERE_API_KEY in .env to use AI features.")
                else:
                    prompt = f"Summarize this research paper in 200-250 words:\n\n{text[:5000]}"
                    with st.spinner("Generating summary..."):
                        out = call_cohere_cached(prompt, max_tokens=450)
                        st.write(out)

        # ---------- TAB 3: KEY FINDINGS ----------
        with tab3:
            st.subheader("🔑 Key Findings")
            if st.button("Extract Key Findings"):
                if not co:
                    st.error("Cohere key missing. Set COHERE_API_KEY in .env to use AI features.")
                else:
                    prompt = f"List the key findings and contributions of this paper in concise bullet points:\n\n{text[:5000]}"
                    with st.spinner("Extracting key findings..."):
                        out = call_cohere_cached(prompt, max_tokens=400)
                        st.write(out)

        # ---------- TAB 4: CRITICAL QUESTIONS ----------
        with tab4:
            st.subheader("🤔 Critical Questions")
            if st.button("Generate Questions"):
                if not co:
                    st.error("Cohere key missing. Set COHERE_API_KEY in .env to use AI features.")
                else:
                    prompt = (
                        "Generate 5 critical, thought-provoking questions about the methodology, "
                        "limitations, and future directions for this research paper:\n\n" + text[:5000]
                    )
                    with st.spinner("Generating questions..."):
                        out = call_cohere_cached(prompt, max_tokens=400)
                        st.write(out)

        # ---------- TAB 5: TERMINOLOGY ----------
        with tab5:
            st.subheader("📚 Explain Terms")
            user_terms = st.text_input("Enter terms (comma-separated):", placeholder="e.g., Transformer, backpropagation")
            if st.button("Explain Terms"):
                if not user_terms:
                    st.warning("Enter at least one term.")
                elif not co:
                    st.error("Cohere key missing. Set COHERE_API_KEY in .env to use AI features.")
                else:
                    prompt = f"Explain these technical terms in simple language:\n{user_terms}"
                    with st.spinner("Explaining terms..."):
                        out = call_cohere_cached(prompt, max_tokens=300)
                        st.write(out)

        # ---------- TAB 6: CITATIONS ----------
        with tab6:
            st.subheader("📖 Extracted Citations & References")
            cit_data = extract_citations(text)

            st.write("**Citation references (detected patterns):**")
            if cit_data["citations"]:
                st.write(cit_data["citations"])
            else:
                st.info("No inline citations detected with common patterns.")

            st.write("**DOIs found:**")
            if cit_data["dois"]:
                st.write(cit_data["dois"])
            else:
                st.info("No DOIs found.")

            st.write("**URLs found:**")
            if cit_data["urls"]:
                st.write(cit_data["urls"])
            else:
                st.info("No URLs found.")

            st.write("**Reference-like lines (heuristic):**")
            if cit_data["reference_lines"]:
                # show first 60 lines
                for ln in cit_data["reference_lines"][:60]:
                    st.markdown(f"- {ln}")
            else:
                st.info("No reference section lines detected (paper might be short or formatted unusually).")

else:
    st.info("Upload a PDF to begin.")
