# modules/remittance_classifier.py
from __future__ import annotations

import functools
import math
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from modules.logger import get_logger
from modules.master_lookups import load_nature_options, load_purpose_grouped

logger = get_logger()

STOPWORDS = {
    "the", "and", "or", "to", "of", "for", "in", "on", "a", "an", "by", "with",
    "fee", "fees", "charge", "charges", "amount", "total", "invoice", "inv",
    "services", "service", "payment", "paid", "bill", "billing",
}

def _norm(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"[\u00A0\t\r]+", " ", t)
    t = re.sub(r"[^\w\s\-/&.]", " ", t)  # keep word chars, space, -, /, &, .
    t = re.sub(r"\s+", " ", t).strip()
    return t

def _tokens(text: str) -> List[str]:
    t = _norm(text)
    toks = []
    for w in re.split(r"[ \-/&.]+", t):
        w = w.strip()
        if not w or w in STOPWORDS or len(w) <= 2:
            continue
        toks.append(w)
    return toks

@dataclass(frozen=True)
class PurposeRecord:
    gr_no: str
    group_name: str
    purpose_code: str
    description: str

@dataclass(frozen=True)
class NatureRecord:
    code: str
    label: str

@dataclass(frozen=True)
class Classification:
    purpose: PurposeRecord
    nature: NatureRecord
    confidence: float
    needs_review: bool
    evidence: List[str]

# -----------------------------
# Load + indexes
# -----------------------------

@functools.lru_cache(maxsize=1)
def _purpose_records() -> Dict[str, PurposeRecord]:
    grouped = load_purpose_grouped()
    out: Dict[str, PurposeRecord] = {}
    for group_name, rows in grouped.items():
        for r in rows:
            code = str(r.get("purpose_code") or "").strip().upper()
            if not code:
                continue
            out[code] = PurposeRecord(
                gr_no=str(r.get("gr_no") or "").strip(),
                group_name=str(group_name or "").strip(),
                purpose_code=code,
                description=str(r.get("description") or "").strip(),
            )
    return out

@functools.lru_cache(maxsize=1)
def _nature_records() -> Dict[str, NatureRecord]:
    out: Dict[str, NatureRecord] = {}
    for r in load_nature_options():
        code = str(r.get("code") or "").strip()
        label = str(r.get("label") or "").strip()
        if not code or not label or code == "-1":  # ignore Select
            continue
        out[code] = NatureRecord(code=code, label=label)
    return out

@functools.lru_cache(maxsize=1)
def _nature_by_label() -> Dict[str, NatureRecord]:
    return {nr.label.strip(): nr for nr in _nature_records().values()}

@functools.lru_cache(maxsize=1)
def _idf_for_purpose_desc() -> Dict[str, float]:
    # IDF across purpose descriptions (N=137) for robust fallback
    recs = list(_purpose_records().values())
    N = len(recs) or 1
    df: Dict[str, int] = {}
    for r in recs:
        seen = set(_tokens(r.description))
        for tok in seen:
            df[tok] = df.get(tok, 0) + 1
    idf = {tok: (math.log((N + 1) / (c + 1)) + 1.0) for tok, c in df.items()}
    return idf

# -----------------------------
# High-signal CA-style rules
# -----------------------------

# Each rule targets a purpose_code and optionally a nature_code.
# patterns are regex on normalized invoice text.
HIGH_SIGNAL_RULES: List[Dict[str, object]] = [
    # Advertising / marketing
    {"purpose_code": "S1007", "nature_code": "16.1", "weight": 60,
     "patterns": [r"\bgoogle\s+ads\b", r"\bfacebook\s+ads\b", r"\blinkedin\s+ads\b",
                  r"\badwords\b", r"\badvertis", r"\bmedia\s+buy\b", r"\btrade\s+fair\b", r"\bexhibition\b"]},
    {"purpose_code": "S1007", "nature_code": "16.49", "weight": 45,
     "patterns": [r"\bmarketing\b", r"\bpromotion\b", r"\blead\s+gen", r"\bmarket\s+research\b"]},

    # Consulting / management / PR
    {"purpose_code": "S1006", "nature_code": "16.13", "weight": 55,
     "patterns": [r"\bconsult", r"\badvisory\b", r"\bmanagement\s+fee\b", r"\bpublic\s+relations\b", r"\bpr\s+services\b"]},
    {"purpose_code": "S1006", "nature_code": "16.46", "weight": 40,
     "patterns": [r"\bretainer\b", r"\bretainership\b"]},
    {"purpose_code": "S1006", "nature_code": "16.47", "weight": 40,
     "patterns": [r"\bretention\s+fee\b"]},

    # Legal / accounting / audit -> Professional services
    {"purpose_code": "S1004", "nature_code": "16.40", "weight": 70,
     "patterns": [r"\blegal\b", r"\blaw\s+firm\b", r"\battorney\b", r"\bsolicitor\b", r"\blitigation\b"]},
    {"purpose_code": "S1005", "nature_code": "16.40", "weight": 70,
     "patterns": [r"\baudit\b", r"\bbook\s*keeping\b", r"\bbook-keeping\b", r"\baccounting\b"]},

    # Architecture / engineering / R&D
    {"purpose_code": "S1009", "nature_code": "16.3", "weight": 60,
     "patterns": [r"\barchitect", r"\barchitectural\b"]},
    {"purpose_code": "S1014", "nature_code": "16.18", "weight": 55,
     "patterns": [r"\bengineering\s+services?\b", r"\bcad\b", r"\bcae\b", r"\bdesign\s+engineering\b"]},
    {"purpose_code": "S1008", "nature_code": "16.42", "weight": 60,
     "patterns": [r"\br&d\b", r"\bresearch\s+and\s+development\b", r"\bprototype\b", r"\blab\b"]},

    # Software: implementation vs maintenance vs purchase vs license/subscription
    {"purpose_code": "S0802", "nature_code": "16.21", "weight": 65,
     "patterns": [r"\bimplementation\b", r"\bintegration\b", r"\bcustomi[sz]ation\b", r"\bconfiguration\b", r"\bdeployment\b", r"\bonboarding\b"]},
    {"purpose_code": "S0804", "nature_code": "16.2", "weight": 65,
     "patterns": [r"\bamc\b", r"\bannual\s+maintenance\b", r"\bmaintenance\s+fee\b", r"\bsupport\s+and\s+maintenance\b"]},
    {"purpose_code": "S0804", "nature_code": "16.61", "weight": 55,
     "patterns": [r"\bwarranty\b", r"\bextended\s+warranty\b"]},
    {"purpose_code": "S0807", "nature_code": "16.41", "weight": 70,
     "patterns": [r"\boff-?site\s+software\b", r"\bsoftware\s+purchase\b", r"\bdownload\s+software\b", r"\blicen[cs]e\s+key\b"]},
    {"purpose_code": "S0902", "nature_code": "16.54", "weight": 60,
     "patterns": [r"\bsaas\b", r"\bsubscription\b", r"\baccess\s+fee\b", r"\bper\s+seat\b", r"\bper\s+user\b"]},
    {"purpose_code": "S0902", "nature_code": "16.52", "weight": 55,
     "patterns": [r"\bsoftware\s+licen[cs]e\b", r"\blicen[cs]ing\b"]},
    {"purpose_code": "S0902", "nature_code": "16.48", "weight": 80,
     "patterns": [r"\broyalty\b"]},

    # Telecom
    {"purpose_code": "S0808", "nature_code": "16.4", "weight": 60,
     "patterns": [r"\bbandwidth\b", r"\bleased\s+line\b", r"\bmpls\b"]},
    {"purpose_code": "S0808", "nature_code": "16.8", "weight": 60,
     "patterns": [r"\broaming\b"]},
    {"purpose_code": "S0808", "nature_code": "16.12", "weight": 50,
     "patterns": [r"\btelecom\b", r"\bcommunication\s+charges\b", r"\bcall\s+charges\b"]},

    # Freight / logistics
    {"purpose_code": "S0220", "nature_code": "16.22", "weight": 70,
     "patterns": [r"\bfreight\b", r"\bawb\b", r"\bair\s+waybill\b", r"\bbill\s+of\s+lading\b", r"\bcourier\b", r"\bdhl\b", r"\bfedex\b", r"\bups\b"]},
    {"purpose_code": "S0220", "nature_code": "16.10", "weight": 60,
     "patterns": [r"\bcustoms\s+clearance\b", r"\bcha\b", r"\bc&f\b", r"\bforwarding\b"]},
    {"purpose_code": "S0220", "nature_code": "16.7", "weight": 55,
     "patterns": [r"\blogistics\b", r"\bcargo\s+handling\b", r"\binspection\b", r"\bterminal\s+handling\b"]},

    # Commission / brokerage / insurance commission
    {"purpose_code": "S1002", "nature_code": "16.11", "weight": 65,
     "patterns": [r"\bcommission\b", r"\breferral\b", r"\bagency\s+commission\b"]},
    {"purpose_code": "S0702", "nature_code": "16.5", "weight": 65,
     "patterns": [r"\bbrokerage\b", r"\bunderwriting\b"]},
    {"purpose_code": "S0605", "nature_code": "16.26", "weight": 70,
     "patterns": [r"\binsurance\s+commission\b"]},

    # Education / telecast / tender
    {"purpose_code": "S1107", "nature_code": "16.37", "weight": 70,
     "patterns": [r"\btuition\b", r"\buniversity\b", r"\bcourse\s+fee\b", r"\bstudent\s+fee\b"]},
    {"purpose_code": "S1103", "nature_code": "16.57", "weight": 60,
     "patterns": [r"\btelecast\b", r"\bbroadcast\b", r"\bradio\b", r"\btelevision\b"]},
    {"purpose_code": "S1503", "nature_code": "16.58", "weight": 65,
     "patterns": [r"\btender\s+fee\b", r"\bbid\s+fee\b", r"\brfp\b"]},

    # Generic fallback bucket (last resort)
    {"purpose_code": "S1099", "nature_code": "16.6", "weight": 5,
     "patterns": [r"\bservice\b", r"\bcharges\b", r"\bfee\b"]},
]

_S_CODE_RE = re.compile(r"\bS\d{4}\b", re.IGNORECASE)

def _explicit_s_code(text: str) -> Optional[str]:
    m = _S_CODE_RE.search(text or "")
    if not m:
        return None
    return m.group(0).upper()

def _score_by_rules(norm_text: str) -> Tuple[Dict[str, float], Dict[str, float], List[str]]:
    # returns (purpose_scores, nature_scores, evidence_hits)
    p_scores: Dict[str, float] = {}
    n_scores: Dict[str, float] = {}
    hits: List[str] = []

    for rule in HIGH_SIGNAL_RULES:
        patterns = rule.get("patterns") or []
        weight = float(rule.get("weight") or 0.0)
        pcode = str(rule.get("purpose_code") or "").upper().strip()
        ncode = str(rule.get("nature_code") or "").strip()

        matched = False
        for pat in patterns:
            if re.search(pat, norm_text, flags=re.IGNORECASE):
                matched = True
                hits.append(pat)
                break
        if not matched:
            continue

        if pcode:
            p_scores[pcode] = p_scores.get(pcode, 0.0) + weight
        if ncode:
            n_scores[ncode] = n_scores.get(ncode, 0.0) + weight

    return p_scores, n_scores, hits[:6]

def _score_by_description_similarity(evidence_tokens: set) -> Dict[str, float]:
    # IDF-weighted token overlap between evidence and purpose descriptions
    idf = _idf_for_purpose_desc()
    scores: Dict[str, float] = {}
    for code, rec in _purpose_records().items():
        desc_toks = set(_tokens(rec.description))
        inter = evidence_tokens.intersection(desc_toks)
        if not inter:
            continue
        scores[code] = sum(idf.get(t, 1.0) for t in inter)
    return scores

def _pick_best(scores: Dict[str, float]) -> Tuple[str, float, float]:
    if not scores:
        return "", 0.0, 0.0
    items = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_code, best = items[0]
    second = items[1][1] if len(items) > 1 else 0.0
    return best_code, best, second

def _confidence(best: float, second: float, explicit: bool) -> float:
    if explicit:
        return 0.95
    if best <= 0.0:
        return 0.30
    # ratio + margin
    ratio = best / (best + second + 1e-6)
    margin = min(1.0, max(0.0, (best - second) / (best + 1e-6)))
    return float(max(0.0, min(1.0, 0.55 * ratio + 0.45 * margin)))

def classify_remittance(invoice_text: str, extracted: Optional[Dict[str, str]] = None) -> Optional[Classification]:
    """
    Returns best (purpose, nature) with confidence + needs_review.
    Always returns something as long as master lists are present.
    """
    extracted = extracted or {}
    raw = invoice_text or ""
    # enrich evidence slightly using extracted key fields (helps for image-only extraction)
    raw += "\n" + " ".join([
        str(extracted.get("purpose_code") or ""),
        str(extracted.get("purpose_group") or ""),
        str(extracted.get("nature_of_remittance") or ""),
        str(extracted.get("remitter_name") or ""),
        str(extracted.get("beneficiary_name") or ""),
    ])
    norm = _norm(raw)

    purpose_map = _purpose_records()
    nature_map = _nature_records()

    # 1) explicit S#### wins (if valid)
    explicit = _explicit_s_code(norm)
    if explicit and explicit in purpose_map:
        p = purpose_map[explicit]
        # choose nature using rules if possible, else best label overlap fallback
        p_scores, n_scores, hits = _score_by_rules(norm)
        ncode, _, _ = _pick_best(n_scores)
        if not ncode:
            ncode = "16.6" if "16.6" in nature_map else next(iter(nature_map.keys()))
        n = nature_map.get(ncode) or next(iter(nature_map.values()))
        conf = _confidence(1.0, 0.0, explicit=True)
        needs_review = conf < 0.75
        return Classification(purpose=p, nature=n, confidence=conf, needs_review=needs_review, evidence=hits[:2] or [explicit])

    # 2) rule scoring
    p_scores, n_scores, hits = _score_by_rules(norm)

    # 3) description similarity fallback (covers all codes)
    ev_tokens = set(_tokens(norm))
    sim_scores = _score_by_description_similarity(ev_tokens)
    # blend: keep rules dominant
    for code, sc in sim_scores.items():
        p_scores[code] = p_scores.get(code, 0.0) + 0.35 * sc

    best_code, best, second = _pick_best(p_scores)
    if not best_code or best_code not in purpose_map:
        best_code = "S1099" if "S1099" in purpose_map else next(iter(purpose_map.keys()))
        best, second = 0.1, 0.0

    p = purpose_map[best_code]

    # Nature selection: rule-based if available; else pick best overlap with nature labels
    ncode, nb, ns = _pick_best(n_scores)
    if not ncode or ncode not in nature_map:
        # token overlap fallback against labels
        best_n = ("16.6" if "16.6" in nature_map else next(iter(nature_map.keys())))
        best_sc = -1.0
        for code, nr in nature_map.items():
            sc = len(set(_tokens(nr.label)).intersection(ev_tokens))
            if sc > best_sc:
                best_sc = sc
                best_n = code
        ncode = best_n

    n = nature_map[ncode]

    conf = _confidence(best, second, explicit=False)
    needs_review = (conf < 0.75) or (best_code == "S1099") or (n.code in {"16.6", "16.99"})
    ev = hits[:2]
    if not ev:
        # use a short evidence phrase from tokens
        ev = [" ".join(list(ev_tokens)[:6])] if ev_tokens else []
    return Classification(purpose=p, nature=n, confidence=conf, needs_review=needs_review, evidence=ev)