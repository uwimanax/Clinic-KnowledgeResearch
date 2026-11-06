"""Shared engine for BabyCare AI. Decision support only; not a diagnosis."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
DOWNLOAD_DIR = DATA_DIR / "downloads"
CORPUS_PATH = DATA_DIR / "corpus.jsonl"
SOURCES_PATH = DATA_DIR / "sources.csv"
DISEASES_PATH = DATA_DIR / "diseases.csv"
INVESTIGATIONS_PATH = DATA_DIR / "investigations.csv"
INGEST_REPORT_PATH = DATA_DIR / "ingestion_report.csv"
DOWNLOAD_REPORT_PATH = DATA_DIR / "download_report.csv"

DISCLAIMER = (
    "BabyCare AI is clinical decision support for qualified clinicians only. "
    "It does not provide a confirmed diagnosis, prescribing advice, or drug doses. "
    "Every finding must be checked against the indexed source and clinician judgement."
)

GRAPH_NOTE = "Hand-compiled knowledge-graph entry; needs clinician validation."
SAFETY_ONLY_LABEL = "listed by safety rule only"
SUPPORTED_LABEL = "supported by indexed source"
REJECTED_LABEL = "rejected - no indexed source retrieved"

SYMPTOM_OPTIONS = [
    {"key": "fever", "label": "Fever"},
    {"key": "cough", "label": "Cough"},
    {"key": "difficulty_breathing", "label": "Difficulty breathing"},
    {"key": "fast_breathing", "label": "Fast breathing"},
    {"key": "vomiting", "label": "Vomiting"},
    {"key": "diarrhea", "label": "Diarrhoea"},
    {"key": "constipation", "label": "Constipation"},
    {"key": "abdominal_pain", "label": "Abdominal pain"},
    {"key": "poor_feeding", "label": "Poor feeding"},
    {"key": "refusal_breastfeed", "label": "Refusal to breastfeed"},
    {"key": "rash", "label": "Rash"},
    {"key": "seizures", "label": "Seizures"},
    {"key": "excessive_crying", "label": "Excessive crying"},
    {"key": "unusual_sleepiness", "label": "Unusual sleepiness"},
    {"key": "weakness", "label": "Weakness"},
    {"key": "dehydration", "label": "Dehydration signs"},
    {"key": "ear_pain", "label": "Ear pain or discharge"},
    {"key": "jaundice", "label": "Jaundice"},
    {"key": "swelling", "label": "Swelling"},
    {"key": "other", "label": "Other"},
]
SYMPTOM_LABELS = {item["key"]: item["label"] for item in SYMPTOM_OPTIONS}

DANGER_SIGNS = [
    {"key": "blue_lips", "label": "Blue/grey lips or skin"},
    {"key": "unresponsive", "label": "Unresponsive"},
    {"key": "unable_to_feed", "label": "Unable to feed"},
    {"key": "shock", "label": "Signs of shock"},
]
DANGER_LABELS = {item["key"]: item["label"] for item in DANGER_SIGNS}

VITAL_FIELDS = [
    ("temperature_c", "Temperature", 30.0, 45.0, "C"),
    ("heart_rate", "Heart rate", 30, 260, "bpm"),
    ("respiratory_rate", "Respiratory rate", 5, 130, "breaths/min"),
    ("spo2", "SpO2", 50, 100, "percent"),
    ("bp_systolic", "Systolic BP", 30, 160, "mmHg"),
    ("bp_diastolic", "Diastolic BP", 15, 110, "mmHg"),
]
VITAL_LABELS = {key: label for key, label, *_ in VITAL_FIELDS}
CORE_VITALS = ["temperature_c", "heart_rate", "respiratory_rate", "spo2", "bp_systolic"]

AGE_UNIT_TO_MONTHS = {"days": 1 / 30.4375, "months": 1.0, "years": 12.0}

DISEASE_ALIASES = {
    "bronchiolitis": ["bronchiolitis"],
    "pneumonia": ["pneumonia"],
    "severe pneumonia": ["severe pneumonia", "very severe pneumonia"],
    "sepsis / serious bacterial infection": ["sepsis", "septicaemia", "septicemia", "serious bacterial infection"],
    "neonatal sepsis": ["neonatal sepsis", "sepsis of newborn", "newborn sepsis"],
    "meningitis": ["meningitis"],
    "meningococcal disease": ["meningococcal", "meningococcus"],
    "urinary tract infection": ["urinary tract infection", "uti", "pyelonephritis"],
    "gastroenteritis": ["gastroenteritis", "acute diarrhoea", "acute diarrhea"],
    "dehydration": ["dehydration"],
    "acute otitis media": ["otitis media", "acute otitis media", "ear infection"],
    "upper respiratory tract infection": ["upper respiratory tract infection", "common cold", "viral upper respiratory"],
    "croup": ["croup", "laryngotracheobronchitis"],
    "asthma / reactive airway disease": ["asthma", "wheez", "reactive airway"],
    "malaria": ["malaria"],
    "measles": ["measles"],
    "severe acute malnutrition": ["severe acute malnutrition", "severe malnutrition", "malnutrition"],
    "hypoglycaemia": ["hypoglycaemia", "hypoglycemia", "low blood glucose"],
    "shock": ["shock", "circulatory collapse"],
    "seizure / status epilepticus": ["seizure", "convulsion", "status epilepticus", "fits"],
    "anaemia": ["anaemia", "anemia", "low haemoglobin", "low hemoglobin"],
    "kawasaki disease": ["kawasaki"],
    "appendicitis": ["appendicitis"],
    "intussusception": ["intussusception"],
    "constipation": ["constipation"],
    "tuberculosis": ["tuberculosis", " tb "],
    "hiv infection": ["hiv", "human immunodeficiency virus"],
    "congenital heart disease": ["congenital heart", "heart disease", "cardiac defect"],
}

SAFETY_CONDITION_MAP = {
    "seizures": ["seizure / status epilepticus", "meningitis", "hypoglycaemia"],
    "blue_lips": ["severe pneumonia", "shock", "congenital heart disease"],
    "unresponsive": ["shock", "meningitis", "hypoglycaemia", "sepsis / serious bacterial infection"],
    "unable_to_feed": ["sepsis / serious bacterial infection", "dehydration", "meningitis"],
    "shock": ["shock", "sepsis / serious bacterial infection"],
    "difficulty_breathing": ["pneumonia", "bronchiolitis", "severe pneumonia"],
    "fast_breathing": ["pneumonia", "bronchiolitis"],
    "dehydration": ["dehydration", "gastroenteritis"],
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _split_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean(v) for v in value if _clean(v)]
    return [_clean(v) for v in re.split(r"[;|]", str(value)) if _clean(v)]


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in columns})


def load_sources(path: Path | str = SOURCES_PATH) -> list[dict[str, Any]]:
    return _read_csv(Path(path))


def load_diseases(path: Path | str = DISEASES_PATH) -> list[dict[str, Any]]:
    rows = _read_csv(Path(path))
    for row in rows:
        row["symptoms"] = _split_list(row.get("symptoms", ""))
        row["risk_factors"] = _split_list(row.get("risk_factors", ""))
        row["complications"] = _split_list(row.get("complications", ""))
        row["investigations"] = _split_list(row.get("investigations", ""))
        row["age_min_months"] = _safe_float(row.get("age_min_months")) or 0.0
        row["age_max_months"] = _safe_float(row.get("age_max_months")) or 60.0
        row["serious"] = _clean(row.get("serious", "")).lower() in {"yes", "true", "1"}
        for key in ("id", "name", "category", "graph_note"):
            row[key] = _clean(row.get(key, ""))
    return rows


def load_investigations(path: Path | str = INVESTIGATIONS_PATH) -> list[dict[str, Any]]:
    rows = _read_csv(Path(path))
    for row in rows:
        row["diseases"] = _split_list(row.get("diseases", ""))
        row["age_min_months"] = _safe_float(row.get("age_min_months")) or 0.0
        row["age_max_months"] = _safe_float(row.get("age_max_months")) or 60.0
        for key in ("id", "test", "why", "age_consideration", "source_note"):
            row[key] = _clean(row.get(key, ""))
    return rows


def compute_age_months(patient: dict[str, Any], assessment_date: Any = None) -> float | None:
    dob = _parse_date(patient.get("dob"))
    on = _parse_date(assessment_date) or date.today()
    if dob:
        days = (on - dob).days
        if days < 0:
            return None
        return round(days / 30.4375, 2)
    value = _safe_float(patient.get("age_value"))
    if value is None and patient.get("age_months") is not None:
        return round(_safe_float(patient.get("age_months")) or 0.0, 2)
    unit = _clean(patient.get("age_unit", "months")).lower()
    if value is None or unit not in AGE_UNIT_TO_MONTHS:
        return None
    return round(value * AGE_UNIT_TO_MONTHS[unit], 2)


def fast_breathing_threshold(age_months: float | None) -> int | None:
    if age_months is None:
        return None
    if age_months < 2:
        return 60
    if age_months < 12:
        return 50
    return 40


def age_band(age_months: float | None) -> str:
    if age_months is None:
        return "age not recorded"
    if age_months < 1:
        return "newborn under 1 month"
    if age_months < 3:
        return "infant under 3 months"
    if age_months < 12:
        return "infant 3 to 11 months"
    if age_months < 36:
        return "child 12 to 35 months"
    return "child 36 to 60 months"


def normalize_patient(patient: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(json.dumps(patient, default=str))
    data["symptoms"] = [s for s in data.get("symptoms", []) if s in SYMPTOM_LABELS]
    data["danger_signs"] = [s for s in data.get("danger_signs", []) if s in DANGER_LABELS]
    data["age_months"] = compute_age_months(data)
    vitals = data.get("vitals") or {}
    data["vitals"] = {key: _safe_float(vitals.get(key)) for key in [v[0] for v in VITAL_FIELDS]}
    for key in ("weight_kg", "length_cm", "head_circumference_cm"):
        data[key] = _safe_float(data.get(key))
    data["history"] = data.get("history") or {}
    data["observations"] = data.get("observations") or {}
    data["followup_answers"] = data.get("followup_answers") or {}
    data["lab_files"] = data.get("lab_files") or []
    return data


def validate_patient(patient: dict[str, Any]) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    data = normalize_patient(patient)
    age = data.get("age_months")
    if age is None:
        errors.append("Age is required. Enter date of birth or age in days, months or years.")
    elif age < 0:
        errors.append("Age cannot be negative.")
    elif age > 60:
        errors.append("Age must be 0 to 60 months for this tool.")
    if not _clean(data.get("sex")):
        errors.append("Sex is required.")
    if not data.get("symptoms") and not data.get("danger_signs"):
        warnings.append("No symptom or danger sign selected. Add the presenting problem.")
    weight = data.get("weight_kg")
    if weight is not None and not (0.4 <= weight <= 40):
        errors.append("Weight is outside the plausible range for a child aged 0 to 60 months.")
    length = data.get("length_cm")
    if length is not None and not (20 <= length <= 140):
        errors.append("Length is outside the plausible range.")
    head = data.get("head_circumference_cm")
    if head is not None and not (20 <= head <= 65):
        errors.append("Head circumference is outside the plausible range.")
    for key, label, low, high, _unit in VITAL_FIELDS:
        value = data["vitals"].get(key)
        if value is not None and not (low <= value <= high):
            errors.append(f"{label} is outside the plausible range ({low} to {high}).")
    birth_weight = _safe_float(data["history"].get("birth_weight_kg"))
    if birth_weight is not None and not (0.3 <= birth_weight <= 7):
        errors.append("Birth weight is outside the plausible range.")
    ga = _safe_float(data["history"].get("gestational_age_weeks"))
    if ga is not None and not (20 <= ga <= 45):
        errors.append("Gestational age must be between 20 and 45 weeks.")
    if data.get("lab_files"):
        warnings.append("Uploaded laboratory files are stored locally and are not sent to any external service.")
    return {"errors": errors, "warnings": warnings}


def find_contradictions(patient: dict[str, Any]) -> list[str]:
    data = normalize_patient(patient)
    symptoms = set(data.get("symptoms", []))
    dangers = set(data.get("danger_signs", []))
    vitals = data.get("vitals", {})
    age = data.get("age_months")
    found: list[str] = []
    temp = vitals.get("temperature_c")
    rr = vitals.get("respiratory_rate")
    spo2 = vitals.get("spo2")
    if "fever" in symptoms and temp is not None and temp < 38.0:
        found.append("Fever is selected, but the recorded temperature is below 38 C.")
    if temp is not None and temp >= 38.0 and "fever" not in symptoms:
        found.append("The recorded temperature is elevated, but fever was not selected.")
    threshold = fast_breathing_threshold(age)
    if rr is not None and threshold is not None and rr >= threshold and "fast_breathing" not in symptoms:
        found.append(
            f"Respiratory rate is at or above the age-specific fast-breathing threshold "
            f"({threshold}/min), but fast breathing was not selected."
        )
    if "fast_breathing" in symptoms and rr is not None and threshold is not None and rr < threshold:
        found.append(
            f"Fast breathing is selected, but the recorded respiratory rate is below the "
            f"age-specific threshold ({threshold}/min)."
        )
    if "seizures" in symptoms and "seizures" not in dangers:
        found.append("Seizures are selected as a symptom. Confirm whether this is current or recent.")
    feeding = _clean(data.get("observations", {}).get("feeding", "")).lower()
    if ("unable_to_feed" in dangers or "poor_feeding" in symptoms) and feeding in {"feeding well", "normal", "good"}:
        found.append("Poor or unable feeding is reported, but the feeding observation says feeding well.")
    urine = _clean(data.get("observations", {}).get("urine_stool", "")).lower()
    if "dehydration" in symptoms and urine in {"normal", "normal urine output"}:
        found.append("Dehydration signs are selected, but the urine/stool observation says normal.")
    if spo2 is not None and spo2 < 90 and "blue_lips" not in dangers:
        found.append("SpO2 is below 90, but blue/grey lips or skin was not selected. Treat the low reading seriously.")
    duration = _safe_float(data.get("duration_days"))
    if duration is not None and age is not None and duration > age * 30.4375 + 1:
        found.append("Symptom duration is longer than the child's recorded age.")
    if age is not None and age < 3 and "fever" in symptoms:
        found.append("Fever in an infant under 3 months is a safety-rule emergency regardless of other findings.")
    return found


def assess_emergency(patient: dict[str, Any]) -> dict[str, Any]:
    data = normalize_patient(patient)
    age = data.get("age_months")
    symptoms = set(data.get("symptoms", []))
    dangers = set(data.get("danger_signs", []))
    vitals = data.get("vitals", {})
    temp = vitals.get("temperature_c")
    rr = vitals.get("respiratory_rate")
    spo2 = vitals.get("spo2")
    pb = vitals.get("bp_systolic")
    emergency: list[str] = []
    urgent: list[str] = []
    missing: list[str] = []
    safety_conditions: set[str] = set()

    for key, label in DANGER_LABELS.items():
        if key in dangers:
            emergency.append(f"Danger sign: {label}.")
            for condition in SAFETY_CONDITION_MAP.get(key, []):
                safety_conditions.add(condition)
    if "seizures" in symptoms:
        emergency.append("Seizure reported. Treat as an emergency until the child is assessed.")
        for condition in SAFETY_CONDITION_MAP["seizures"]:
            safety_conditions.add(condition)
    if spo2 is not None and spo2 < 90:
        emergency.append(f"SpO2 is {spo2:g}, below 90. This is an emergency.")
        for condition in ["severe pneumonia", "shock", "congenital heart disease"]:
            safety_conditions.add(condition)
    elif spo2 is not None and 90 <= spo2 < 94:
        urgent.append(f"SpO2 is {spo2:g}. Recheck and review urgently.")
    if age is not None and age < 3 and temp is not None and temp >= 38.0:
        emergency.append("Fever at or above 38 C in an infant under 3 months is an emergency.")
        for condition in ["neonatal sepsis", "meningitis", "urinary tract infection"]:
            safety_conditions.add(condition)
    if age is not None and age < 3 and "difficulty_breathing" in symptoms:
        emergency.append("Difficulty breathing in an infant under 3 months is an emergency.")
        for condition in ["severe pneumonia", "bronchiolitis", "sepsis / serious bacterial infection"]:
            safety_conditions.add(condition)
    threshold = fast_breathing_threshold(age)
    if rr is not None and threshold is not None and rr >= threshold:
        urgent.append(f"Respiratory rate is at or above the age-specific fast-breathing threshold ({threshold}/min).")
        for condition in ["pneumonia", "bronchiolitis"]:
            safety_conditions.add(condition)
    if "fast_breathing" in symptoms:
        urgent.append("Fast breathing is reported.")
        for condition in ["pneumonia", "bronchiolitis"]:
            safety_conditions.add(condition)
    if "difficulty_breathing" in symptoms and not (age is not None and age < 3):
        urgent.append("Difficulty breathing is reported.")
        for condition in ["pneumonia", "bronchiolitis", "asthma / reactive airway disease"]:
            safety_conditions.add(condition)
    if "dehydration" in symptoms:
        urgent.append("Dehydration signs are reported.")
        for condition in ["dehydration", "gastroenteritis"]:
            safety_conditions.add(condition)
    if "poor_feeding" in symptoms or "refusal_breastfeed" in symptoms:
        urgent.append("Poor feeding or refusal to breastfeed requires urgent review in a young child.")
    if "unusual_sleepiness" in symptoms or "weakness" in symptoms:
        urgent.append("Unusual sleepiness or weakness requires urgent review.")
    if temp is not None and (temp >= 40.0 or temp < 35.5):
        urgent.append(f"Temperature is {temp:g} C and needs urgent review.")
    if age is not None and age < 1:
        urgent.append("Infant under 1 month: lower threshold for urgent clinical review.")
    if pb is not None and age is not None and age < 12 and pb < 70:
        urgent.append(f"Systolic blood pressure is {pb:g} mmHg in an infant. Review for shock.")
        safety_conditions.add("shock")

    if age is None:
        missing.append("Exact age in months")
    if not _clean(data.get("sex")):
        missing.append("Sex")
    if data.get("weight_kg") is None:
        missing.append("Weight")
    omitted_vitals = {_clean(item) for item in data.get("vitals_not_collected", [])}
    for key in CORE_VITALS:
        if key in omitted_vitals:
            continue
        if vitals.get(key) is None:
            missing.append(VITAL_LABELS.get(key, key))
    if not data.get("symptoms") and not data.get("danger_signs"):
        missing.append("Presenting problem or symptom")

    if emergency:
        level = "Emergency"
    elif urgent or missing:
        level = "Urgent"
    else:
        level = "Routine"
    reasons = emergency + urgent
    if missing:
        reasons.append("Missing information: " + ", ".join(missing) + ". Missing values are not assumed normal.")
    return {
        "level": level,
        "reasons": reasons,
        "emergency_reasons": emergency,
        "urgent_reasons": urgent,
        "missing": missing,
        "safety_conditions": sorted(safety_conditions),
        "age_months": age,
        "fast_breathing_threshold": threshold,
        "rule_note": "Deterministic safety rules ran before retrieval and before any LLM call.",
    }

def patient_profile(patient: dict[str, Any]) -> dict[str, Any]:
    data = normalize_patient(patient)
    age = data.get("age_months")
    contradictions = find_contradictions(data)
    missing = []
    if age is None:
        missing.append("Exact age")
    if not data.get("sex"):
        missing.append("Sex")
    if data.get("weight_kg") is None:
        missing.append("Weight")
    omitted_vitals = {_clean(item) for item in data.get("vitals_not_collected", [])}
    for key in CORE_VITALS:
        if key in omitted_vitals:
            continue
        if data["vitals"].get(key) is None:
            missing.append(VITAL_LABELS.get(key, key))
    history = data.get("history", {})
    for key, label in [
        ("immunisation", "Immunisation status"),
        ("feeding_type", "Feeding type"),
        ("gestational_age_weeks", "Gestational age"),
    ]:
        if not _clean(history.get(key)):
            missing.append(label)
    symptoms = [SYMPTOM_LABELS.get(s, s) for s in data.get("symptoms", [])]
    dangers = [DANGER_LABELS.get(s, s) for s in data.get("danger_signs", [])]
    return {
        "name": _clean(data.get("name")),
        "parent_name": _clean(data.get("parent_name")),
        "patient_id": _clean(data.get("patient_id")),
        "age_months": age,
        "age_band": age_band(age),
        "sex": _clean(data.get("sex")),
        "weight_kg": data.get("weight_kg"),
        "length_cm": data.get("length_cm"),
        "head_circumference_cm": data.get("head_circumference_cm"),
        "symptoms": symptoms,
        "danger_signs": dangers,
        "vitals": data["vitals"],
        "missing": sorted(set(missing)),
        "contradictions": contradictions,
        "fast_breathing_threshold": fast_breathing_threshold(age),
    }


def graph_candidates(patient: dict[str, Any], diseases: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    data = normalize_patient(patient)
    diseases = diseases if diseases is not None else load_diseases()
    age = data.get("age_months")
    symptoms = set(data.get("symptoms", [])) | set(data.get("danger_signs", []))
    history = data.get("history", {})
    risks: set[str] = set()
    ga = _safe_float(history.get("gestational_age_weeks"))
    if ga is not None and ga < 37:
        risks.add("prematurity")
    bw = _safe_float(history.get("birth_weight_kg"))
    if bw is not None and bw < 2.5:
        risks.add("low_birth_weight")
    if age is not None and age < 1:
        risks.add("neonate")
    immunisation = _clean(history.get("immunisation", "")).lower()
    if immunisation and any(word in immunisation for word in ["incomplete", "not", "none", "unknown"]):
        risks.add("unimmunized")
    chronic = _clean(history.get("chronic_conditions", "")).lower()
    if "hiv" in chronic:
        risks.add("HIV_exposure")
    if _clean(history.get("sick_contacts", "")).lower() in {"yes", "true", "1"}:
        risks.add("sick_contact")
    if _clean(history.get("malaria_area_travel", "")).lower() in {"yes", "true", "1"}:
        risks.add("malaria_travel")
    if "yes" in _clean(history.get("birth_complications", "")).lower():
        risks.add("birth_complications")
    if _clean(history.get("family_history", "")).lower() not in {"", "no", "none"}:
        risks.add("family_history")
    if "severe acute malnutrition" in _clean(history.get("previous_illnesses", "")).lower():
        risks.add("malnutrition")
    if "allerg" in _clean(history.get("allergies", "")).lower():
        risks.add("allergy")

    candidates = []
    for disease in diseases:
        if age is not None and not (disease["age_min_months"] <= age <= disease["age_max_months"]):
            continue
        disease_symptoms = set(disease["symptoms"])
        disease_risks = set(disease["risk_factors"])
        matched_symptoms = sorted(symptoms & disease_symptoms)
        matched_risks = sorted(risks & disease_risks)
        score = len(matched_symptoms) * 2.0 + len(matched_risks) * 1.5
        if disease["serious"]:
            score += 0.25
        if score <= 0:
            continue
        absent = [s for s in disease["symptoms"] if s not in symptoms]
        candidates.append(
            {
                "id": disease.get("id", ""),
                "name": disease["name"],
                "category": disease.get("category", ""),
                "serious": disease["serious"],
                "age_min_months": disease["age_min_months"],
                "age_max_months": disease["age_max_months"],
                "score": round(score, 2),
                "matched_symptoms": matched_symptoms,
                "matched_risks": matched_risks,
                "missing_information": absent[:6],
                "complications": disease["complications"],
                "investigations": disease["investigations"],
                "graph_note": disease.get("graph_note") or GRAPH_NOTE,
            }
        )
    candidates.sort(key=lambda item: (item["serious"], item["score"]), reverse=True)
    return candidates[:10]


def _chunk_id(doc_id: str, page: int, index: int, text: str) -> str:
    raw = f"{doc_id}|{page}|{index}|{text[:120]}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def _normalise_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_text(text: str, max_chars: int = 1100, overlap: int = 160) -> list[str]:
    text = _normalise_text(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", text)
    chunks: list[str] = []
    current = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            for start in range(0, len(part), max_chars - overlap):
                pieces = part[start : start + max_chars].strip()
                if pieces:
                    chunks.append(pieces)
        elif len(current) + len(part) + 1 <= max_chars:
            current = f"{current} {part}".strip()
        else:
            if current:
                chunks.append(current.strip())
            current = part[-overlap:] if overlap and len(part) > overlap else part
    if current:
        chunks.append(current.strip())
    return [c for c in chunks if len(c) >= 60]


def _match_diseases(text: str, diseases: list[dict[str, Any]]) -> list[str]:
    lower = text.lower()
    names = []
    for disease in diseases:
        name = disease["name"]
        aliases = DISEASE_ALIASES.get(name.lower(), [name.lower()])
        if any(alias in lower for alias in aliases):
            names.append(name)
    return sorted(set(names))


def _extract_pdf(path: Path) -> list[dict[str, Any]]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for index, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            pages.append({"page": index + 1, "text": "", "error": str(exc)})
            continue
        pages.append({"page": index + 1, "text": _normalise_text(text)})
    return pages


def _extract_html(path: Path) -> list[dict[str, Any]]:
    from bs4 import BeautifulSoup

    raw = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text("\n", strip=True)
    return [{"page": 1, "text": _normalise_text(text)}]


def _extract_txt(path: Path) -> list[dict[str, Any]]:
    return [{"page": 1, "text": _normalise_text(path.read_text(encoding="utf-8", errors="ignore"))}]


def extract_document(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix in {".html", ".htm"}:
        return _extract_html(path)
    if suffix in {".txt", ".md"}:
        return _extract_txt(path)
    return []


def _source_for_local_file(path: Path, manifest: dict[str, dict[str, str]]) -> dict[str, Any]:
    row = manifest.get(path.name.lower(), {})
    return {
        "id": "local_" + hashlib.sha1(path.name.encode("utf-8")).hexdigest()[:10],
        "organization": _clean(row.get("organization")) or "Local document",
        "title": _clean(row.get("title")) or path.stem,
        "date": _clean(row.get("date")) or datetime.fromtimestamp(path.stat().st_mtime).date().isoformat(),
        "url": _clean(row.get("url")) or "",
        "doc_type": path.suffix.lstrip("."),
        "filename": path.name,
        "category": "local",
        "notes": "Local document supplied by the user.",
    }


def _manifest_map(docs_dir: Path) -> dict[str, dict[str, str]]:
    rows = _read_csv(docs_dir / "manifest.csv")
    return {_clean(row.get("filename", "")).lower(): row for row in rows if _clean(row.get("filename"))}


def _headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 BabyCareAI/1.0"
        ),
        "Accept": "application/pdf,text/html,application/xhtml+xml,*/*;q=0.8",
    }


def download_sources(
    sources: list[dict[str, Any]] | None = None,
    dest_dir: Path | str = DOWNLOAD_DIR,
    timeout: int = 90,
    force: bool = False,
) -> list[dict[str, Any]]:
    import requests

    sources = sources if sources is not None else load_sources()
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    report = []
    for source in sources:
        source_id = _clean(source.get("id")) or hashlib.sha1(_clean(source.get("url")).encode()).hexdigest()[:10]
        url = _clean(source.get("url"))
        fallback_name = _clean(source.get("filename")) or f"{source_id}.pdf"
        stem = Path(fallback_name).stem
        existing = list(dest.glob(f"{stem}.*"))
        if existing and not force:
            path = existing[0]
            report.append(
                {
                    "id": source_id,
                    "organization": _clean(source.get("organization")),
                    "title": _clean(source.get("title")),
                    "url": url,
                    "file": str(path),
                    "status": "OK",
                    "reason": "cached download",
                    "bytes": path.stat().st_size,
                    "downloaded": False,
                }
            )
            continue
        if not url:
            report.append(
                {
                    "id": source_id,
                    "organization": _clean(source.get("organization")),
                    "title": _clean(source.get("title")),
                    "url": "",
                    "file": "",
                    "status": "FAIL",
                    "reason": "no URL configured",
                    "bytes": 0,
                    "downloaded": False,
                }
            )
            continue
        try:
            response = requests.get(url, headers=_headers(), timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            content = response.content
            content_type = response.headers.get("content-type", "").lower()
            suffix = Path(urlparse(response.url).path).suffix.lower()
            if content.lstrip().startswith(b"%PDF") or "pdf" in content_type:
                suffix = ".pdf"
            elif "html" in content_type or suffix in {".html", ".htm", ""}:
                suffix = ".html"
            elif not suffix:
                suffix = ".txt"
            path = dest / f"{stem}{suffix}"
            path.write_bytes(content)
            is_pdf = content.lstrip().startswith(b"%PDF")
            status = "OK"
            reason = "downloaded"
            if suffix == ".pdf" and not is_pdf:
                status = "FAIL"
                reason = "response was not a valid PDF"
            if len(content) < 1000:
                status = "FAIL"
                reason = f"response too small ({len(content)} bytes)"
            report.append(
                {
                    "id": source_id,
                    "organization": _clean(source.get("organization")),
                    "title": _clean(source.get("title")),
                    "url": url,
                    "file": str(path),
                    "status": status,
                    "reason": reason,
                    "bytes": len(content),
                    "downloaded": True,
                }
            )
        except Exception as exc:
            report.append(
                {
                    "id": source_id,
                    "organization": _clean(source.get("organization")),
                    "title": _clean(source.get("title")),
                    "url": url,
                    "file": "",
                    "status": "FAIL",
                    "reason": str(exc)[:300],
                    "bytes": 0,
                    "downloaded": False,
                }
            )
    _write_csv(
        DOWNLOAD_REPORT_PATH,
        report,
        ["id", "organization", "title", "url", "file", "status", "reason", "bytes", "downloaded"],
    )
    return report


def _source_file(source: dict[str, Any]) -> Path | None:
    filename = _clean(source.get("filename"))
    if filename:
        candidate = DOWNLOAD_DIR / filename
        if candidate.exists():
            return candidate
        matches = list(DOWNLOAD_DIR.glob(Path(filename).stem + ".*"))
        if matches:
            return matches[0]
    source_id = _clean(source.get("id"))
    matches = list(DOWNLOAD_DIR.glob(source_id + ".*")) if source_id else []
    return matches[0] if matches else None


def build_corpus(
    docs_dir: Path | str = DOCS_DIR,
    data_dir: Path | str = DATA_DIR,
    download: bool = True,
    sources_path: Path | str = SOURCES_PATH,
    force_download: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    docs_path = Path(docs_dir)
    data_path = Path(data_dir)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    sources = load_sources(sources_path)
    diseases = load_diseases()
    download_report = download_sources(sources, force=force_download) if download else []

    corpus: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()

    for source in sources:
        source_id = _clean(source.get("id"))
        title = _clean(source.get("title")) or source_id
        path = _source_file(source)
        if path is None:
            report.append(
                {
                    "id": source_id,
                    "organization": _clean(source.get("organization")),
                    "title": title,
                    "date": _clean(source.get("date")),
                    "url": _clean(source.get("url")),
                    "file": "",
                    "status": "FAIL",
                    "pages": 0,
                    "chunks": 0,
                    "chars": 0,
                    "reason": "not downloaded - not in the knowledge base",
                }
            )
            continue
        seen_paths.add(path.resolve())
        try:
            pages = extract_document(path)
        except Exception as exc:
            report.append(
                {
                    "id": source_id,
                    "organization": _clean(source.get("organization")),
                    "title": title,
                    "date": _clean(source.get("date")),
                    "url": _clean(source.get("url")),
                    "file": str(path),
                    "status": "FAIL",
                    "pages": 0,
                    "chunks": 0,
                    "chars": 0,
                    "reason": f"extraction error: {str(exc)[:240]}",
                }
            )
            continue
        doc_chunks: list[dict[str, Any]] = []
        for page in pages:
            for index, chunk in enumerate(_split_text(page.get("text", ""))):
                doc_chunks.append(
                    {
                        "chunk_id": _chunk_id(source_id, page["page"], index, chunk),
                        "doc_id": source_id,
                        "organization": _clean(source.get("organization")),
                        "title": title,
                        "date": _clean(source.get("date")),
                        "url": _clean(source.get("url")),
                        "page": page["page"],
                        "text": chunk,
                        "mentions": _match_diseases(chunk, diseases),
                        "source_type": _clean(source.get("doc_type")) or path.suffix.lstrip("."),
                        "category": _clean(source.get("category")),
                    }
                )
        chars = sum(len(page.get("text", "")) for page in pages)
        if not doc_chunks:
            report.append(
                {
                    "id": source_id,
                    "organization": _clean(source.get("organization")),
                    "title": title,
                    "date": _clean(source.get("date")),
                    "url": _clean(source.get("url")),
                    "file": str(path),
                    "status": "FAIL",
                    "pages": len(pages),
                    "chunks": 0,
                    "chars": chars,
                    "reason": "no extractable text - not in the knowledge base",
                }
            )
            continue
        corpus.extend(doc_chunks)
        report.append(
            {
                "id": source_id,
                "organization": _clean(source.get("organization")),
                "title": title,
                "date": _clean(source.get("date")),
                "url": _clean(source.get("url")),
                "file": str(path),
                "status": "OK",
                "pages": len(pages),
                "chunks": len(doc_chunks),
                "chars": chars,
                "reason": "indexed",
            }
        )

    manifest = _manifest_map(docs_path)
    if docs_path.exists():
        for path in sorted(docs_path.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".pdf", ".html", ".htm", ".txt", ".md"}:
                continue
            if path.resolve() in seen_paths:
                continue
            source = _source_for_local_file(path, manifest)
            try:
                pages = extract_document(path)
            except Exception as exc:
                report.append(
                    {
                        "id": source["id"],
                        "organization": source["organization"],
                        "title": source["title"],
                        "date": source["date"],
                        "url": source["url"],
                        "file": str(path),
                        "status": "FAIL",
                        "pages": 0,
                        "chunks": 0,
                        "chars": 0,
                        "reason": f"extraction error: {str(exc)[:240]}",
                    }
                )
                continue
            doc_chunks = []
            for page in pages:
                for index, chunk in enumerate(_split_text(page.get("text", ""))):
                    doc_chunks.append(
                        {
                            "chunk_id": _chunk_id(source["id"], page["page"], index, chunk),
                            "doc_id": source["id"],
                            "organization": source["organization"],
                            "title": source["title"],
                            "date": source["date"],
                            "url": source["url"],
                            "page": page["page"],
                            "text": chunk,
                            "mentions": _match_diseases(chunk, diseases),
                            "source_type": path.suffix.lstrip("."),
                            "category": "local",
                        }
                    )
            chars = sum(len(page.get("text", "")) for page in pages)
            status = "OK" if doc_chunks else "FAIL"
            if doc_chunks:
                corpus.extend(doc_chunks)
            report.append(
                {
                    "id": source["id"],
                    "organization": source["organization"],
                    "title": source["title"],
                    "date": source["date"],
                    "url": source["url"],
                    "file": str(path),
                    "status": status,
                    "pages": len(pages),
                    "chunks": len(doc_chunks),
                    "chars": chars,
                    "reason": "indexed local document" if doc_chunks else "no extractable text - not in the knowledge base",
                }
            )

    corpus.sort(key=lambda item: (item["doc_id"], item["page"], item["chunk_id"]))
    data_path.mkdir(parents=True, exist_ok=True)
    corpus_file = data_path / "corpus.jsonl"
    with corpus_file.open("w", encoding="utf-8") as handle:
        for chunk in corpus:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    _write_csv(
        data_path / "ingestion_report.csv",
        report,
        ["id", "organization", "title", "date", "url", "file", "status", "pages", "chunks", "chars", "reason"],
    )
    return corpus, report


def load_corpus(path: Path | str = CORPUS_PATH) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    chunks = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                chunks.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return chunks


class TfidfVectorStore:
    def __init__(self, chunks: list[dict[str, Any]]):
        self.chunks = chunks
        self.vectorizer = None
        self.matrix = None
        self.available = False
        if chunks:
            from sklearn.feature_extraction.text import TfidfVectorizer

            self.vectorizer = TfidfVectorizer(
                stop_words="english",
                ngram_range=(1, 2),
                min_df=1,
                max_features=90000,
                sublinear_tf=True,
                strip_accents="unicode",
            )
            self.matrix = self.vectorizer.fit_transform([chunk.get("text", "") for chunk in chunks])
            self.available = True

    def search(
        self,
        query: str,
        k: int = 6,
        prefer_diseases: Iterable[str] | None = None,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        if not self.available or not query.strip():
            return []
        from sklearn.metrics.pairwise import cosine_similarity

        query_vector = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vector, self.matrix).ravel()
        preferred = {p.lower() for p in (prefer_diseases or [])}
        if preferred:
            for index, chunk in enumerate(self.chunks):
                mentions = {m.lower() for m in chunk.get("mentions", [])}
                if any(name in mentions for name in preferred):
                    scores[index] = scores[index] * 1.25 + 0.05
        order = scores.argsort()[::-1]
        results = []
        for index in order:
            score = float(scores[index])
            if score <= min_score:
                break
            chunk = dict(self.chunks[int(index)])
            chunk["score"] = round(score, 5)
            results.append(chunk)
            if len(results) >= k:
                break
        return results

    def search_many(self, queries: list[str], per_query: int = 5, prefer_diseases: Iterable[str] | None = None) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for query in queries:
            for result in self.search(query, k=per_query, prefer_diseases=prefer_diseases):
                existing = merged.get(result["chunk_id"])
                if existing is None or result["score"] > existing["score"]:
                    merged[result["chunk_id"]] = result
        return sorted(merged.values(), key=lambda item: item["score"], reverse=True)

def _symptom_query_map() -> dict[str, str]:
    return {
        "fever": "fever assessment child under five",
        "cough": "cough or difficult breathing child",
        "difficulty_breathing": "difficult breathing pneumonia child",
        "fast_breathing": "fast breathing age threshold child",
        "vomiting": "vomiting child assessment",
        "diarrhea": "diarrhoea dehydration child",
        "constipation": "constipation child",
        "abdominal_pain": "abdominal pain child",
        "poor_feeding": "poor feeding young infant",
        "refusal_breastfeed": "breastfeeding refusal young infant",
        "rash": "rash fever child",
        "seizures": "seizure convulsion child",
        "excessive_crying": "excessive crying infant",
        "unusual_sleepiness": "lethargy unconscious child",
        "weakness": "weakness lethargy child",
        "dehydration": "dehydration signs child diarrhoea",
        "ear_pain": "ear pain discharge otitis media child",
        "jaundice": "jaundice newborn infant",
        "swelling": "swelling child oedema",
    }


def plan_research_queries(patient: dict[str, Any], candidates: list[dict[str, Any]], llm: Any = None) -> list[str]:
    data = normalize_patient(patient)
    band = age_band(data.get("age_months"))
    queries = [f"danger signs assessment {band}"]
    query_map = _symptom_query_map()
    for symptom in data.get("symptoms", []):
        if symptom in query_map:
            queries.append(f"{query_map[symptom]} {band}")
    for danger in data.get("danger_signs", []):
        queries.append(f"{DANGER_LABELS.get(danger, danger)} {band} emergency")
    threshold = fast_breathing_threshold(data.get("age_months"))
    if threshold:
        queries.append(f"respiratory rate fast breathing threshold {threshold} per minute {band}")
    for candidate in candidates[:6]:
        queries.append(f"{candidate['name']} {band} clinical features")
    queries.append(f"sick child {band} assessment and classification")
    if llm is not None and getattr(llm, "enabled", False):
        planned = llm.plan_queries(deidentify_patient(patient), candidates)
        if planned:
            queries = planned + queries
    seen = []
    seen_lower = set()
    for query in queries:
        query = re.sub(r"\s+", " ", query).strip()
        if query and query.lower() not in seen_lower:
            seen.append(query)
            seen_lower.add(query.lower())
    return seen[:12]


def run_research(patient: dict[str, Any], store: TfidfVectorStore, candidates: list[dict[str, Any]], llm: Any = None) -> dict[str, Any]:
    queries = plan_research_queries(patient, candidates, llm=llm)
    prefer = [candidate["name"] for candidate in candidates]
    passages = store.search_many(queries, per_query=4, prefer_diseases=prefer)
    sufficient = len(passages) >= 4 and any(p.get("score", 0) > 0.08 for p in passages)
    expanded = False
    if not sufficient:
        expanded = True
        band = age_band(normalize_patient(patient).get("age_months"))
        broad = [f"child health guideline {band}", "integrated management childhood illness", "paediatric hospital care children"]
        broad += [candidate["name"] for candidate in candidates[:6]]
        extra = store.search_many(broad, per_query=5, prefer_diseases=prefer)
        merged = {p["chunk_id"]: p for p in passages + extra}
        passages = sorted(merged.values(), key=lambda item: item["score"], reverse=True)
        sufficient = len(passages) >= 3 and any(p.get("score", 0) > 0.05 for p in passages)
    return {
        "queries": queries,
        "passages": passages[:30],
        "sufficient": sufficient,
        "expanded": expanded,
        "note": "Evidence retrieval completed." if sufficient else "Evidence is thin or absent. Do not treat unsupported items as guideline-backed.",
    }


def _passages_for_disease(disease: str, passages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aliases = DISEASE_ALIASES.get(disease.lower(), [disease.lower()])
    matches = []
    for passage in passages:
        text = passage.get("text", "").lower()
        mentions = {m.lower() for m in passage.get("mentions", [])}
        if disease.lower() in mentions or any(alias in text for alias in aliases):
            matches.append(passage)
    return matches


def _excerpt(text: str, limit: int = 460) -> str:
    text = _clean(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last = max(cut.rfind(". "), cut.rfind("; "))
    if last > limit * 0.55:
        cut = cut[: last + 1]
    return cut.strip() + " ..."


def _reference_key(ref: dict[str, Any]) -> str:
    return f"{ref.get('doc_id')}|{ref.get('page')}"


def analyse_diseases(
    patient: dict[str, Any],
    candidates: list[dict[str, Any]],
    passages: list[dict[str, Any]],
    llm: Any = None,
) -> list[dict[str, Any]]:
    analyses = []
    for candidate in candidates:
        evidence = _passages_for_disease(candidate["name"], passages)[:4]
        supporting_labels = [SYMPTOM_LABELS.get(s, s) for s in candidate["matched_symptoms"]]
        risk_labels = [r.replace("_", " ") for r in candidate["matched_risks"]]
        info_needed = [SYMPTOM_LABELS.get(s, s) for s in candidate["missing_information"]]
        explanation = (
            "Candidate proposed by the hand-compiled knowledge graph because the reported findings include "
            f"{', '.join(supporting_labels) if supporting_labels else 'no directly matching symptom'}"
        )
        if risk_labels:
            explanation += f" and risk factors include {', '.join(risk_labels)}"
        explanation += ". This is not a diagnosis."
        llm_note = ""
        if llm is not None and getattr(llm, "enabled", False) and evidence:
            llm_note = llm.comment_on_candidate(candidate, evidence, deidentify_patient(patient))
        references = []
        seen = set()
        for passage in evidence:
            key = _reference_key(passage)
            if key in seen:
                continue
            seen.add(key)
            references.append(
                {
                    "doc_id": passage.get("doc_id"),
                    "organization": passage.get("organization"),
                    "title": passage.get("title"),
                    "date": passage.get("date"),
                    "url": passage.get("url"),
                    "page": passage.get("page"),
                    "doc_type": passage.get("source_type"),
                }
            )
        analyses.append(
            {
                "id": candidate["id"],
                "name": candidate["name"],
                "category": candidate.get("category", ""),
                "serious": candidate["serious"],
                "score": candidate["score"],
                "why_considered": supporting_labels,
                "risk_factors": risk_labels,
                "explanation": explanation,
                "llm_note": llm_note,
                "information_needed": info_needed,
                "complications": candidate["complications"],
                "graph_investigations": candidate["investigations"],
                "evidence": evidence,
                "references": references,
                "graph_note": candidate.get("graph_note", GRAPH_NOTE),
                "evidence_status": SUPPORTED_LABEL if evidence else "no evidence retrieved yet",
            }
        )
    return analyses


def _conflict_notes(disease: dict[str, Any]) -> list[str]:
    notes = []
    text = " ".join(p.get("text", "").lower() for p in disease.get("evidence", []))
    if not text:
        return notes
    name = disease["name"].lower().split("/")[0].strip()
    negation = re.search(r"\b(no|not|without|unlikely|exclude|excludes|does not)\b.{0,80}" + re.escape(name), text)
    affirmative = name in text
    if negation and affirmative:
        notes.append(f"Possible conflicting wording involving {disease['name']} in the retrieved excerpts. Clinician review required.")
    return notes


def verify_diseases(
    diseases: list[dict[str, Any]],
    store: TfidfVectorStore,
    safety_conditions: Iterable[str],
    patient: dict[str, Any],
    llm: Any = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    safety_set = {s.lower() for s in safety_conditions}
    kept = []
    rejected = []
    notes = []
    band = age_band(normalize_patient(patient).get("age_months"))
    for disease in diseases:
        evidence = disease.get("evidence", [])
        if not evidence:
            extra = store.search(f"{disease['name']} {band} diagnosis management", k=6, prefer_diseases=[disease["name"]])
            extra = _passages_for_disease(disease["name"], extra)
            if extra:
                disease["evidence"] = extra[:4]
                disease["references"] = [
                    {
                        "doc_id": p.get("doc_id"),
                        "organization": p.get("organization"),
                        "title": p.get("title"),
                        "date": p.get("date"),
                        "url": p.get("url"),
                        "page": p.get("page"),
                        "doc_type": p.get("source_type"),
                    }
                    for p in extra[:4]
                ]
                evidence = disease["evidence"]
        if evidence:
            disease["evidence_status"] = SUPPORTED_LABEL
            notes.extend(_conflict_notes(disease))
            kept.append(disease)
            continue
        safety_listed = disease["name"].lower() in safety_set or any(
            disease["name"].lower() in condition or condition in disease["name"].lower()
            for condition in safety_set
        )
        if disease["serious"] and safety_listed:
            disease["evidence_status"] = SAFETY_ONLY_LABEL
            disease["information_needed"] = ["No indexed passage retrieved for this condition; clinician validation required."] + disease.get("information_needed", [])
            kept.append(disease)
            notes.append(f"{disease['name']}: {SAFETY_ONLY_LABEL}. It is kept only because a deterministic safety rule raised it; no indexed source was retrieved.")
        else:
            disease["evidence_status"] = REJECTED_LABEL
            rejected.append(disease)
            notes.append(f"{disease['name']}: {REJECTED_LABEL}. It was not shown as a supported candidate.")
    kept.sort(
        key=lambda item: (
            item["evidence_status"] != SUPPORTED_LABEL,
            item["evidence_status"] != SAFETY_ONLY_LABEL,
            not item["serious"],
            -item["score"],
        )
    )
    return kept, rejected, notes


def recommend_investigations(diseases: list[dict[str, Any]], patient: dict[str, Any]) -> list[dict[str, Any]]:
    data = normalize_patient(patient)
    age = data.get("age_months")
    all_investigations = load_investigations()
    suggestions = []
    for item in all_investigations:
        if age is not None and not (item["age_min_months"] <= age <= item["age_max_months"]):
            continue
        linked = [d["name"] for d in diseases if d["name"].lower() in {x.lower() for x in item["diseases"]}]
        if not linked and "any" not in {x.lower() for x in item["diseases"]}:
            continue
        suggestions.append(
            {
                "test": item["test"],
                "why": item["why"],
                "helps_assess": linked or item["diseases"],
                "age_consideration": item["age_consideration"],
                "source_note": item["source_note"],
            }
        )
    seen = set()
    unique = []
    for item in suggestions:
        key = item["test"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def build_followup_questions(patient: dict[str, Any], profile: dict[str, Any], diseases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    data = normalize_patient(patient)
    questions = []
    vitals = data.get("vitals", {})
    omitted_vitals = {_clean(item) for item in data.get("vitals_not_collected", [])}
    for key in CORE_VITALS:
        if key in omitted_vitals:
            continue
        if vitals.get(key) is None:
            questions.append(
                {
                    "id": f"vital_{key}",
                    "question": f"What is the recorded {VITAL_LABELS[key]}?",
                    "reason": "Missing vital; it cannot be assumed normal.",
                    "kind": "vital",
                }
            )
    if data.get("weight_kg") is None:
        questions.append({"id": "weight_kg", "question": "What is the child's current weight?", "reason": "Missing weight.", "kind": "measurement"})
    if not _clean(data.get("history", {}).get("immunisation")):
        questions.append({"id": "history_immunisation", "question": "What is the immunisation status?", "reason": "Missing history that affects risk assessment.", "kind": "history"})
    if not _clean(data.get("history", {}).get("feeding_type")):
        questions.append({"id": "history_feeding_type", "question": "How is the child fed (breast, formula, mixed, other)?", "reason": "Feeding information is missing.", "kind": "history"})
    for contradiction in profile.get("contradictions", [])[:3]:
        questions.append({"id": "contradiction_" + str(len(questions)), "question": f"Please clarify: {contradiction}", "reason": "Contradictory information found.", "kind": "clarification"})
    if data.get("symptoms"):
        questions.append({"id": "symptom_duration", "question": "When did the symptoms start and are they getting worse?", "reason": "Onset and trajectory guide urgency review.", "kind": "symptom"})
        questions.append({"id": "symptom_feeding", "question": "Is the child feeding and drinking, and how many wet nappies in the last 24 hours?", "reason": "Feeding and urine output are key safety information.", "kind": "symptom"})
    for disease in diseases[:5]:
        for missing in disease.get("information_needed", [])[:2]:
            if missing.startswith("No indexed passage"):
                continue
            questions.append(
                {
                    "id": f"info_{disease['id']}_{len(questions)}",
                    "question": f"For {disease['name']}: is {missing.lower()} present or reported?",
                    "reason": f"Information needed to assess {disease['name']}.",
                    "kind": "disease",
                }
            )
    seen = set()
    unique = []
    for question in questions:
        if question["question"].lower() in seen:
            continue
        seen.add(question["question"].lower())
        unique.append(question)
    return unique[:12]


def apply_followup_answers(patient: dict[str, Any], answers: dict[str, str]) -> dict[str, Any]:
    data = normalize_patient(patient)
    data["followup_answers"] = {**data.get("followup_answers", {}), **{k: v for k, v in answers.items() if _clean(v)}}
    for key, value in answers.items():
        value = _clean(value)
        if not value:
            continue
        if key.startswith("vital_"):
            vital_key = key.replace("vital_", "", 1)
            if vital_key in data["vitals"]:
                data["vitals"][vital_key] = _safe_float(value)
        elif key == "weight_kg":
            data["weight_kg"] = _safe_float(value)
        elif key.startswith("history_"):
            history_key = key.replace("history_", "", 1)
            data["history"][history_key] = value
        elif key.startswith("symptom_"):
            if value.lower() in {"yes", "y", "true", "present"}:
                symptom_key = key.replace("symptom_", "", 1)
                if symptom_key in SYMPTOM_LABELS and symptom_key not in data["symptoms"]:
                    data["symptoms"].append(symptom_key)
        else:
            note = data["observations"].get("other_findings", "")
            data["observations"]["other_findings"] = (note + f" Follow-up: {value}.").strip()
    return data

def _collect_references(diseases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs = []
    seen = set()
    for disease in diseases:
        for ref in disease.get("references", []):
            key = _reference_key(ref)
            if key in seen:
                continue
            seen.add(key)
            refs.append(ref)
    refs.sort(key=lambda item: (item.get("organization", ""), item.get("title", ""), item.get("page", 0)))
    return refs


def _report_summary(patient: dict[str, Any], urgency: dict[str, Any], diseases: list[dict[str, Any]], llm: Any = None) -> str:
    supported = [d["name"] for d in diseases if d.get("evidence_status") == SUPPORTED_LABEL]
    safety_only = [d["name"] for d in diseases if d.get("evidence_status") == SAFETY_ONLY_LABEL]
    summary = (
        f"Urgency level: {urgency['level']}. "
        f"Supported graph candidates: {', '.join(supported) if supported else 'none retrieved'}. "
        f"Safety-rule-only considerations: {', '.join(safety_only) if safety_only else 'none'}."
    )
    if llm is not None and getattr(llm, "enabled", False):
        generated = llm.summarise(deidentify_patient(patient), urgency, diseases)
        if generated:
            summary = sanitize_generated_text(generated)
    return summary


def sanitize_generated_text(text: str) -> str:
    text = re.sub(r"\b\d+(?:\.\d+)?\s*%", "", text)
    text = re.sub(r"\b\d+(?:\.\d+)?\s*percent\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def deidentify_text(text: str, patient: dict[str, Any] | None = None) -> str:
    text = _clean(text)
    if patient:
        for value in (patient.get("name"), patient.get("parent_name"), patient.get("patient_id")):
            if value and len(str(value)) >= 3:
                text = text.replace(str(value), "[removed]")
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[email removed]", text)
    text = re.sub(r"\+?\d[\d\s-]{7,}\d", "[number removed]", text)
    return text


def deidentify_patient(patient: dict[str, Any]) -> dict[str, Any]:
    data = normalize_patient(patient)
    safe = {
        "age_months": data.get("age_months"),
        "age_band": age_band(data.get("age_months")),
        "sex": _clean(data.get("sex")),
        "weight_kg": data.get("weight_kg"),
        "length_cm": data.get("length_cm"),
        "head_circumference_cm": data.get("head_circumference_cm"),
        "vitals": data.get("vitals"),
        "symptoms": data.get("symptoms"),
        "danger_signs": data.get("danger_signs"),
        "duration_days": data.get("duration_days"),
        "getting_worse": _clean(data.get("getting_worse")),
        "history": {
            key: value
            for key, value in data.get("history", {}).items()
            if key not in {"current_medications", "allergies"}
            and not any(word in key for word in ["name", "id", "address"])
        },
        "observations": {
            key: deidentify_text(value, patient)
            for key, value in data.get("observations", {}).items()
            if isinstance(value, str)
        },
        "symptom_notes": deidentify_text(data.get("symptom_notes", ""), patient),
    }
    return safe


class LLMClient:
    def __init__(self, enabled: bool | None = None, model: str | None = None):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        disable = os.getenv("BABYCARE_DISABLE_LLM", "").strip().lower() in {"1", "true", "yes"}
        if enabled is None:
            self.enabled = bool(self.api_key) and not disable
        else:
            self.enabled = bool(enabled) and bool(self.api_key) and not disable
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
        self.last_error = ""

    def _complete(self, system: str, user: str, max_tokens: int = 600) -> str:
        if not self.enabled:
            return ""
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            parts = []
            for block in response.content:
                if getattr(block, "type", "") == "text":
                    parts.append(block.text)
            return sanitize_generated_text("\n".join(parts).strip())
        except Exception as exc:
            self.last_error = str(exc)[:300]
            return ""

    def plan_queries(self, safe_patient: dict[str, Any], candidates: list[dict[str, Any]]) -> list[str]:
        system = (
            "You plan literature searches for a pediatric clinical decision-support tool. "
            "Return only a JSON array of 4 to 8 short search queries. Do not provide diagnoses, "
            "drug doses, probabilities, references, or invented facts. Use age-specific terms."
        )
        user = json.dumps({"patient": safe_patient, "candidate_names": [c["name"] for c in candidates[:8]]}, ensure_ascii=False)
        raw = self._complete(system, user, max_tokens=400)
        if not raw:
            return []
        try:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            parsed = json.loads(match.group(0)) if match else []
            return [sanitize_generated_text(str(q)) for q in parsed if isinstance(q, str)][:8]
        except Exception:
            return []

    def comment_on_candidate(self, candidate: dict[str, Any], evidence: list[dict[str, Any]], safe_patient: dict[str, Any]) -> str:
        system = (
            "You are assisting clinicians. Comment ONLY on the single candidate provided. "
            "Use ONLY the supplied guideline excerpts for medical claims. Do not add diagnoses, "
            "probabilities, percentages, numbers, drug doses, references, or facts not in the excerpts. "
            "If evidence is insufficient, say so. Keep under 70 words."
        )
        user = json.dumps(
            {
                "candidate": candidate["name"],
                "reported_symptoms": candidate.get("matched_symptoms", []),
                "patient": safe_patient,
                "excerpts": [
                    {"title": p.get("title"), "page": p.get("page"), "text": _excerpt(p.get("text", ""), 700)}
                    for p in evidence[:3]
                ],
            },
            ensure_ascii=False,
        )
        return self._complete(system, user, max_tokens=220)

    def summarise(self, safe_patient: dict[str, Any], urgency: dict[str, Any], diseases: list[dict[str, Any]]) -> str:
        system = (
            "Write a clinical decision-support summary in no more than 120 words. "
            "Use only the supplied facts. Do not diagnose, prescribe, give drug doses, "
            "invent references, or include probabilities or percentages. State uncertainty."
        )
        user = json.dumps(
            {
                "patient": safe_patient,
                "urgency": {"level": urgency.get("level"), "reasons": urgency.get("reasons", [])[:8]},
                "candidates": [
                    {
                        "name": d["name"],
                        "status": d.get("evidence_status"),
                        "why": d.get("why_considered"),
                        "evidence_titles": [r.get("title") for r in d.get("references", [])],
                    }
                    for d in diseases[:8]
                ],
            },
            ensure_ascii=False,
        )
        text = self._complete(system, user, max_tokens=240)
        words = text.split()
        return " ".join(words[:120])


def run_agents(
    patient: dict[str, Any],
    store: TfidfVectorStore,
    llm: LLMClient | None = None,
    diseases_data: list[dict[str, Any]] | None = None,
    agent_log: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    log = agent_log if agent_log is not None else []
    data = normalize_patient(patient)
    profiles = patient_profile(data)
    log.append({"agent": "Patient Information Agent", "status": "complete", "detail": f"Age {profiles.get('age_months')} months; {len(profiles['missing'])} missing item(s); {len(profiles['contradictions'])} contradiction(s).", "elapsed_ms": 0})

    safety_start = time.time()
    urgency = assess_emergency(data)
    log.append({"agent": "Safety & Emergency Agent", "status": "complete", "detail": f"{urgency['level']} by deterministic rules before retrieval/LLM.", "elapsed_ms": int((time.time() - safety_start) * 1000)})

    candidates = graph_candidates(data, diseases_data)
    research = run_research(data, store, candidates, llm=llm)
    log.append({"agent": "Pediatric Research Agent", "status": "complete", "detail": f"{len(research['queries'])} queries; {len(research['passages'])} passages; sufficient={research['sufficient']}; expanded={research['expanded']}.", "elapsed_ms": 0})

    analysed = analyse_diseases(data, candidates, research["passages"], llm=llm)
    log.append({"agent": "Disease Analysis Agent", "status": "complete", "detail": f"{len(analysed)} graph candidates analysed; no probabilities generated.", "elapsed_ms": 0})

    kept, rejected, verification_notes = verify_diseases(analysed, store, urgency["safety_conditions"], data, llm=llm)
    log.append({"agent": "Evidence Verification Agent", "status": "complete", "detail": f"{sum(1 for d in kept if d['evidence_status'] == SUPPORTED_LABEL)} supported; {sum(1 for d in kept if d['evidence_status'] == SAFETY_ONLY_LABEL)} safety-only; {len(rejected)} rejected.", "elapsed_ms": 0})

    investigations = recommend_investigations(kept, data)
    log.append({"agent": "Medical Investigation Agent", "status": "complete", "detail": f"{len(investigations)} suggestions; clinician decides.", "elapsed_ms": 0})

    followups = build_followup_questions(data, profiles, kept)
    references = _collect_references(kept)
    summary = _report_summary(data, urgency, kept, llm=llm)
    log.append({"agent": "Medical Report Agent", "status": "complete", "detail": f"{len(kept)} candidates, {len(investigations)} investigations, {len(followups)} follow-up questions, {len(references)} references.", "elapsed_ms": 0})

    must_not_miss = [d["name"] for d in kept if d["serious"]]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "disclaimer": DISCLAIMER,
        "profile": profiles,
        "patient_summary": {
            "age_months": profiles["age_months"],
            "age_band": profiles["age_band"],
            "sex": profiles["sex"],
            "weight_kg": profiles["weight_kg"],
            "length_cm": profiles["length_cm"],
            "head_circumference_cm": profiles["head_circumference_cm"],
            "symptoms": profiles["symptoms"],
            "danger_signs": profiles["danger_signs"],
            "vitals": profiles["vitals"],
        },
        "urgency": urgency,
        "summary": summary,
        "diseases": kept,
        "must_not_miss": must_not_miss,
        "rejected": rejected,
        "investigations": investigations,
        "followup_questions": followups,
        "references": references,
        "contradictions": profiles["contradictions"],
        "verification_notes": verification_notes,
        "research": {
            "queries": research["queries"],
            "sufficient": research["sufficient"],
            "expanded": research["expanded"],
            "note": research["note"],
            "passage_count": len(research["passages"]),
        },
        "agent_log": log,
        "graph_note": GRAPH_NOTE,
    }


def _format_value(value: Any, unit: str = "") -> str:
    if value is None or value == "":
        return "not recorded"
    return f"{value}{unit}"


def report_to_markdown(report: dict[str, Any], include_identifiers: bool = False, primary_only: bool = False) -> str:
    urgency = report.get("urgency", {})
    lines = [
        "# BabyCare AI Clinical Decision-Support Report",
        "",
        f"Generated: {report.get('generated_at', '')}",
        "",
        f"> {report.get('disclaimer', DISCLAIMER)}",
        "",
        "## A. Patient summary",
        "",
    ]
    profile = report.get("profile", {})
    if include_identifiers and (profile.get("name") or profile.get("patient_id")):
        lines.append(f"- Name or ID: {profile.get('name') or profile.get('patient_id')}")
    else:
        lines.append("- Name or ID: withheld in download")
    lines.extend(
        [
            f"- Age: {_format_value(profile.get('age_months'), ' months')} ({profile.get('age_band', '')})",
            f"- Sex: {profile.get('sex') or 'not recorded'}",
            f"- Weight: {_format_value(profile.get('weight_kg'), ' kg')}",
            f"- Length: {_format_value(profile.get('length_cm'), ' cm')}",
            f"- Head circumference: {_format_value(profile.get('head_circumference_cm'), ' cm')}",
            f"- Symptoms: {', '.join(profile.get('symptoms', [])) or 'none selected'}",
            f"- Danger signs: {', '.join(profile.get('danger_signs', [])) or 'none selected'}",
            "",
            "## B. Urgency",
            "",
            f"**{urgency.get('level', 'not assessed')}**",
            "",
        ]
    )
    for reason in urgency.get("reasons", []):
        lines.append(f"- {reason}")
    all_diseases = report.get("diseases", [])
    primary = all_diseases[0] if all_diseases else None
    diseases = all_diseases[:1] if primary_only else all_diseases
    section_title = "## C. Best-supported condition (not a confirmed diagnosis)" if primary_only else "## C. Possible diseases (not diagnoses)"
    lines.extend(["", section_title, ""])
    if not diseases:
        lines.append("No condition met the evidence rules. This does not exclude serious illness.")
    for disease in diseases:
        lines.extend(
            [
                f"### {disease['name']}",
                "",
                f"- Status: {disease.get('evidence_status', '')}",
                f"- Serious: {'yes' if disease.get('serious') else 'no'}",
                f"- Why considered: {', '.join(disease.get('why_considered', [])) or 'graph match'}",
                f"- Risk factors: {', '.join(disease.get('risk_factors', [])) or 'none recorded'}",
                f"- Information needed: {', '.join(disease.get('information_needed', [])) or 'none listed'}",
                f"- Possible complications: {', '.join(disease.get('complications', [])) or 'not listed'}",
                f"- Knowledge-graph note: {disease.get('graph_note', GRAPH_NOTE)}",
            ]
        )
        if disease.get("llm_note"):
            lines.append(f"- Digital assistant note: {disease['llm_note']}")
        for passage in disease.get("evidence", []):
            lines.extend(
                [
                    "",
                    f"> {_excerpt(passage.get('text', ''), 600)}",
                    "",
                    f"Source: {passage.get('organization')}; {passage.get('title')}; {passage.get('date')}; page {passage.get('page')}",
                ]
            )
        lines.append("")
    lines.extend(["## D. Recommended investigations", ""])
    investigations = report.get("investigations", [])
    if primary_only and primary:
        investigations = [
            item
            for item in investigations
            if primary.get("name") in item.get("helps_assess", [])
            or any(str(value).lower() == "any" for value in item.get("helps_assess", []))
        ]
    if not investigations:
        lines.append("No investigation suggestion was generated. The clinician decides all testing.")
    for item in investigations:
        lines.append(f"- **{item['test']}**: {item['why']} (helps assess: {', '.join(item['helps_assess'])}). Age note: {item['age_consideration']}.")
    lines.extend(["", "## E. Follow-up questions", ""])
    followups = report.get("followup_questions", [])
    if primary_only and primary:
        primary_id = str(primary.get("id", ""))
        followups = [
            question
            for question in followups
            if not str(question.get("id", "")).startswith("info_")
            or str(question.get("id", "")).startswith(f"info_{primary_id}_")
        ]
    for question in followups:
        lines.append(f"- {question['question']} ({question['reason']})")
    lines.extend(["", "## F. References", ""])
    if primary_only and primary:
        refs = primary.get("references", [])
    else:
        refs = report.get("references", [])
    if not refs:
        lines.append("No indexed reference was retrieved. No reference is invented.")
    else:
        lines.append("| Organization | Title | Date | Page | Link |")
        lines.append("|---|---|---|---|---|")
        for ref in refs:
            lines.append(
                f"| {ref.get('organization', '')} | {ref.get('title', '')} | {ref.get('date', '')} | {ref.get('page', '')} | {ref.get('url', '')} |"
            )
    lines.extend(["", "## Verification notes", ""])
    verification_notes = report.get("verification_notes", [])
    if primary_only and primary:
        primary_name = str(primary.get("name", "")).lower()
        other_names = [str(disease.get("name", "")).lower() for disease in all_diseases[1:]]
        verification_notes = [
            note
            for note in verification_notes
            if primary_name in note.lower()
            and not any(other and other in note.lower() for other in other_names)
        ]
        if not verification_notes:
            verification_notes = ["Automated verification completed. Clinician review is still required."]
    for note in verification_notes or ["No automated verification conflict detected. Clinician review is still required."]:
        lines.append(f"- {note}")
    lines.extend(["", "## Contradictions and information gaps", ""])
    contradictions = report.get("contradictions", [])
    if contradictions:
        for item in contradictions:
            lines.append(f"- {item}")
    else:
        lines.append("- None detected automatically.")
    lines.extend(["", "## Agent activity log", ""])
    for entry in report.get("agent_log", []):
        lines.append(f"- {entry.get('agent')}: {entry.get('detail')}")
    lines.extend(["", "## Safety statement", "", DISCLAIMER, ""])
    return "\n".join(lines)



