# 📄 Research Paper Analyzer

An AI-powered research paper analysis tool that extracts text from PDF research papers and leverages Cohere's NLP models to generate summaries, key findings, terminology explanations, citations, and critical thinking questions through an interactive Streamlit interface.

---

## 🚀 Features

- Upload and analyze research papers in PDF format
- AI-generated summaries for faster understanding
- Extract key findings and research contributions
- Explain complex technical terminology
- Generate critical thinking questions
- Extract citations and references
- Display metadata including title and authors
- Interactive tab-based Streamlit interface
- Modular architecture for easy maintenance and extension

---

## 🛠 Tech Stack

- **Python**
- **Streamlit**
- **Cohere API**
- **pdfplumber**
- **python-dotenv**

---

## ⚙️ Project Workflow

```text
Upload PDF
      │
      ▼
Extract Text (pdfplumber)
      │
      ▼
Process with Cohere NLP
      │
      ├── Summary
      ├── Key Findings
      ├── Terminology
      ├── Questions
      └── Citations
      │
      ▼
Display Results in Streamlit
```

---

## 📂 Project Structure

```
Research-Paper-Analyzer/
│
├── app.py
├── analyzer.py
├── requirements.txt
├── .env
├── README.md
└── assets/
```

---

## ▶️ Installation

Clone the repository

```bash
git clone https://github.com/yourusername/research-paper-analyzer.git
cd research-paper-analyzer
```

Install dependencies

```bash
pip install -r requirements.txt
```

Create a `.env` file and add your Cohere API key.

```env
COHERE_API_KEY=your_api_key
```

Run the application

```bash
streamlit run app.py
```

---

## 🎯 Use Cases

- Students reviewing academic papers
- Researchers performing literature reviews
- Faculty and educators
- Final-year project research
- Learning unfamiliar research topics

---

## 📌 Future Improvements

- Support multiple LLM providers
- Multi-document comparison
- Semantic search across uploaded papers
- Export analysis as PDF or DOCX
- Citation graph visualization

---

## 📄 License

This project is intended for educational and research purposes.
