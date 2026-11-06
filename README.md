# BabyCare AI

Clinic research assistant

BabyCare AI is a local clinical decision-support prototype for children aged 0 to 60 months. It combines deterministic safety rules, a hand-compiled pediatric knowledge graph, local guideline retrieval, evidence verification, and an optional Claude narrative layer.

It is not a diagnostic system, medical device, prescribing tool, or replacement for clinician judgement. Missing data is never treated as normal. The tool does not calculate probabilities, provide drug doses, or invent references.

## What is included

- `app.py`: Streamlit interface with an assessment screen and a report screen.
- `babycare_agentic_rag.ipynb`: workflow notebook covering ingestion, retrieval, safety rules, three demonstration cases, follow-up updates, and audit assertions.
- `babycare_engine.py`: shared engine used by both the app and the notebook.
- `data/sources.csv`: configured source manifest.
- `data/diseases.csv`: hand-compiled disease and symptom graph.
- `data/investigations.csv`: hand-compiled investigation considerations.
- `data/downloads/`: downloaded guideline documents, generated locally and not committed.
- `data/corpus.jsonl`: indexed text chunks, generated locally and not committed.
- `data/download_report.csv`: download status and failures.
- `data/ingestion_report.csv`: indexing status and failures.
- `docs/`: local document drop folder with `docs/manifest.csv`.

## Workflow

1. **Patient information agent** normalizes age, measurements, vital signs, symptoms, danger signs, and session-only child and parent names. History and observations are normalized when supplied to the engine.
2. **Safety and emergency agent** applies deterministic escalation rules before retrieval or any LLM call.
3. **Pediatric research agent** creates age-aware retrieval queries and searches the local index.
4. **Disease analysis agent** combines graph matches with retrieved passages.
5. **Evidence verification agent** keeps supported candidates, retains serious safety-only candidates, and rejects unsupported ones.
6. **Medical investigation agent** suggests clinician discussion prompts from the hand-compiled table.
7. **Medical report agent** produces the structured report and reference list.

The optional Claude layer is disabled by default. It is enabled only when `ANTHROPIC_API_KEY` is set and `BABYCARE_DISABLE_LLM` is not truthy. Only de-identified content is sent when enabled.

## Setup

```powershell
python -m pip install -r requirements.txt
```

Run the app:

```powershell
python -m streamlit run app.py
```

Open the provided local URL. On first use, select **Download / refresh and index documents** in the sidebar. The initial index build can take about 30 to 60 seconds after documents are downloaded.

Open `babycare_agentic_rag.ipynb` in your Jupyter environment (JupyterLab, Jupyter Notebook, or VS Code). The notebook is provided without saved outputs. Running it will reuse cached downloads, rebuild the index, run the demonstration cases, and write Markdown examples to `data/demo_reports/`.

## Indexed evidence

The locally generated corpus contains 12 indexed documents and 2,853 text chunks:

- Rwanda Standard Treatment Guidelines: Pediatrics Volume 2, 2022
- Rwanda Clinical Treatment Guidelines: Pediatrics, 2012
- Rwanda National Neonatal Care Protocol, 2020
- WHO Pocket Book of Hospital Care for Children, 2nd edition, 2013
- WHO/UNICEF Integrated Management of Childhood Illness Chart Booklet, 2014
- NICE NG143 fever in under 5s
- NICE NG9 bronchiolitis
- NICE CG84 gastroenteritis
- NICE NG195 neonatal infection
- NICE CG98 neonatal jaundice
- NICE NG240 bacterial meningitis and meningococcal disease
- NICE NG224 urinary tract infection
- NICE NG91 acute otitis media

### Known source failures

These sources are configured but were not indexed:

- Rwanda Paediatric Treatment Guidelines, 2023, and the Rwanda Basic Paediatric Protocol upload: the RBC filenames contain a special `U+2029` character. The server returns HTTP 500 for the encoded URL and HTTP 404 for the raw URL.
- The policyvault mirror of the 2012 Rwanda paediatric emergencies document: the host refused the connection.

Failures are shown in the report output and are never presented as indexed evidence.

## Safety behavior

- Dangerous findings such as low SpO2 (when supplied to the engine), seizures, shock signs, inability to feed, and fever in an infant under 3 months escalate to **Emergency**.
- Missing core information escalates to at least **Urgent**.
- Poor feeding with a normal feeding observation is flagged as a contradiction.
- Only conditions with retrieved passages, or serious conditions raised by a safety rule, remain visible.
- Rejected conditions and verification notes remain inspectable in the report.
- References are collected only from indexed chunks. If no passage is found, no reference is invented.
- The report intentionally omits numeric probability scores.

## Data and privacy

- Enter only the minimum necessary information. Child and parent names stay in the active session, are not sent to the optional LLM, and are withheld from downloaded reports.
- Other direct identifiers such as addresses, phone numbers, or national identifiers should not be entered.
- The optional LLM receives a de-identified summary only when configured.
- Do not use this prototype with identifiable patient information without a local data-protection review.

## Limitations and required review

- The disease graph and investigation table are hand-compiled and must be validated by local clinicians.
- Retrieval quality depends on the indexed documents; relevant passages can be missed.
- A missing passage does not mean a condition is absent.
- Local epidemiology, available tests, and national guidance may differ from the indexed sources.
- Deployment requires clinical governance, validation, security review, and ongoing monitoring.
