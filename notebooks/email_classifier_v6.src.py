#%% [markdown]
# ML Phil — Email Classifier v6: LEGITIMATE vs SPAM vs PHISHING

One notebook, top to bottom: **imports → data + EDA → preprocessing → training → evaluation → stability tests**.
Model: DistilBERT, 3 classes (`0 = LEGITIMATE`, `1 = SPAM`, `2 = PHISHING`).
Output: **`email_security_model/`** (drop-in for the website: same files as v5) + **`reports/`**.

### What changed from v5, and why
v5 scored 98.9% phishing recall internally but **54.2% on modern phishing** (phishing_pot) and flagged **13.5% of Enron** legitimate mail.
An error analysis of v5 on phishing_pot found: newer phishing is caught less (2023: 66%, 2026: 54%), most misses go to SPAM,
and Enron false alerts are mostly called PHISHING. The source of an email was 97–99.8% predictable from its text, so v5 partly learned dataset style.

| v5 problem | v6 change |
|---|---|
| Phishing training data is old (Nazario, Nigerian fraud) | Train also on **phishing_pot up to 2024**; tune on **2025**; test on **2026 and later**, never seen |
| Office mail (Enron) flagged as phishing | Enron split **by near-duplicate cluster**: half train, a quarter dev, a quarter test. **Ling stays fully unseen** |
| Small edits flip predictions (forwarded: 9%, half body: 19% of phishing) | **Train-time augmentation** with those edits; the stability test adds two edits never used in training |
| Temperature and threshold tuned on in-domain validation | Tuned on an **external dev set** (phishing_pot 2025 + Enron dev), never on the test set |
| 256 tokens | **384 tokens** (start + end of long emails) |
| One headline number | Adds **malicious caught** (called SPAM or PHISHING), results **by year and language**, and **v5 vs v6 on the same test** if v5 is attached |

### Kaggle setup
1. Accelerator **GPU T4 x1**, **Internet ON** (phishing_pot is cloned from GitHub).
2. Add Input → Dataset **`naserabdullahalam/phishing-email-dataset`**.
3. *Optional, for a fair comparison:* Add Input → your **v5 notebook output** (the one with `email_security_model/`).
4. **Save Version → Save & Run All (Commit)**. Quick Save stores no files.

### Honesty notes
* The **locked test** = phishing_pot 2026+, Ling, Enron test clusters. Nothing is tuned on it.
* Enron is no longer fully unseen (its other clusters are in training), so it is reported separately from Ling.
* phishing_pot is a honeypot: everything in it is labelled PHISHING, including some plain spam. *Malicious caught* is reported next to phishing recall for that reason.

#%% [markdown]
## 1. Imports and configuration

#%% [code]
import os, sys, re, json, time, math, random, zlib, hashlib, shutil, subprocess, platform, inspect, importlib.util
import email
from email import policy as email_policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import torch
import transformers
import sklearn
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, accuracy_score, classification_report
from transformers import (AutoTokenizer, AutoModelForSequenceClassification, TrainingArguments,
                          Trainer, DataCollatorWithPadding, set_seed)

pd.set_option("display.width", 200); pd.set_option("display.max_columns", 30)
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False})
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print("python", platform.python_version(), "| torch", torch.__version__, "| transformers", transformers.__version__,
      "| sklearn", sklearn.__version__, "| device", DEVICE, torch.cuda.get_device_name(0) if DEVICE == "cuda" else "")

#%% [code]
CFG = dict(
    MODEL_NAME="distilbert-base-uncased",   # for more non-English mail try "distilbert-base-multilingual-cased"
    INPUT_ROOT="/kaggle/input",
    WORK_DIR="/kaggle/working",
    TMP_DIR="/tmp/email_model_tmp",          # checkpoints + phishing_pot clone (not saved as output)
    SEED=42,
    MAX_LENGTH=384, TAIL_TOKENS=96,          # head + tail truncation
    CAP_PER_SOURCE_LABEL=6000,               # training-pool rows per (source, label)
    DEV_CAP_PER_SOURCE_LABEL=2000,           # external dev rows per (source, label)
    EXTERNAL_CAP_PER_SOURCE_LABEL=4000,      # locked test rows per (source, label)
    MIN_BODY_CHARS=20,
    NEAR_DUP_JACCARD=0.80,
    # phishing_pot split by the email's Date header year
    USE_PHISHING_POT=True, POT_LOCAL_DIR=None,
    POT_TRAIN_MAX_YEAR=2024, POT_DEV_YEAR=2025, POT_TEST_MIN_YEAR=2026,
    POT_MAX={"train": 4000, "dev": 1500, "external": 3000},
    ENRON_SPLIT={"train": 50, "dev": 25, "external": 25},   # percent of Enron near-duplicate clusters
    AUGMENT_FRACTION=0.25,                   # extra edited copies of training emails
    EPOCHS=3, LR=3e-5, BATCH=32, EVAL_BATCH=64, WARMUP_RATIO=0.06, WEIGHT_DECAY=0.01,
    TARGET_DEV_MAX_LEGIT_TO_PHISH=0.05,      # threshold: most dev phishing caught while <= 5% of dev legit called PHISHING
    UNCERTAIN_BELOW=0.60,
    BOOTSTRAP=1000,
    STABILITY_PER_CLASS=600,
    EXTRA_SEEDS=[7, 123],                    # each extra seed = one more training run; [] to skip
    PREVIOUS_MODEL_DIR=None,                 # None = look for an attached v5 email_security_model/ under INPUT_ROOT
    TARGET_EXT_PHISH_RECALL=0.90, TARGET_EXT_PHISH_TO_LEGIT=0.05, TARGET_EXT_LEGIT_FALSE_ALERT=0.05,
)
if os.environ.get("NB_TEST") == "1":            # local smoke test only; ignored on Kaggle
    CFG.update(json.loads(os.environ["NB_TEST_CFG"]))

WORK, TMP = Path(CFG["WORK_DIR"]), Path(CFG["TMP_DIR"])
OUT = WORK / "email_security_model"
REPORTS = WORK / "reports"; FIGS = REPORTS / "figures"
for d in (OUT, REPORTS):
    if d.exists():
        shutil.rmtree(d)
for d in (FIGS, TMP):
    d.mkdir(parents=True, exist_ok=True)
os.chdir(WORK)
if str(WORK) not in sys.path:
    sys.path.insert(0, str(WORK))

SEED = CFG["SEED"]
def seed_all(s):
    random.seed(s); np.random.seed(s); torch.manual_seed(s); set_seed(s)
seed_all(SEED)

def strat_sample(df, by, n):
    return pd.concat([g.sample(min(len(g), n), random_state=SEED) for _, g in df.groupby(by)], ignore_index=True)

def savefig(name):
    plt.tight_layout(); plt.savefig(FIGS / f"{name}.png", bbox_inches="tight"); plt.show(); plt.close()

#%% [markdown]
## 2. Helper functions (cleaning, tokenisation, prediction)
Written to `email_preprocess.py`, imported here, and copied into the model folder, so the website uses identical code.
Same functions and file names as v5, so the website loads v6 without changes.

#%% [code]
%%writefile email_preprocess.py
"""
email_preprocess.py — text cleaning, tokenisation and prediction for the ML Phil email model (v6).
Written by the training notebook and copied into the saved model folder, so training,
evaluation and the website backend all use exactly the same code.
Labels: 0 = LEGITIMATE, 1 = SPAM, 2 = PHISHING
"""
import html
import json
import re
import unicodedata
from pathlib import Path

LABELS = ["LEGITIMATE", "SPAM", "PHISHING"]
ID2LABEL = {i: l for i, l in enumerate(LABELS)}
LABEL2ID = {l: i for i, l in enumerate(LABELS)}

MAX_INPUT_CHARS = 100_000
CLEAN_HEAD_CHARS = 15_000
CLEAN_TAIL_CHARS = 5_000
SOURCE_ARTIFACT_TOKENS = ["escapenumber", "escapelong"]   # dataset placeholders, not meaning

_SCRIPT = re.compile(r"(?is)<(script|style|head)[^>]*>.*?</\1>")
_BREAK = re.compile(r"(?i)<\s*(br|/p|/div|/tr|/li|/h\d)\s*/?>")
_TAG = re.compile(r"(?s)<[^>]{1,2000}>")
URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"'()\[\]{}]+")
_EMAIL = re.compile(r"(?i)\b[\w.+-]+@[\w-]+(?:\.[\w-]+)*\b")   # TLD optional: also catches placeholders like "user@pot"
_LONGNUM = re.compile(r"\b\d{5,}\b")
_ZW = re.compile(r"[​-‏⁠﻿­]")
_ARTIFACT = re.compile(r"(?i)\b(" + "|".join(SOURCE_ARTIFACT_TOKENS) + r")\b")
_SPACES = re.compile(r"[ \t\r\f\v]+")
_BLANKS = re.compile(r"\n\s*\n+")


def url_host(u):
    h = re.sub(r"(?i)^(https?://)?", "", u)
    h = re.split(r"[/?#]", h, maxsplit=1)[0]
    h = h.split("@")[-1].split(":")[0].lower().strip(".")
    return h[:80] or "unknown"


def clean_text(text):
    """Strip HTML, keep URL hosts (signal), drop URL paths, addresses and long numbers (noise)."""
    if text is None:
        return ""
    s = str(text)
    if s.lower() in {"nan", "none", "null"}:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = _ZW.sub("", s)
    if "<" in s and ">" in s:
        s = _SCRIPT.sub(" ", s)
        s = _BREAK.sub("\n", s)
        s = _TAG.sub(" ", s)
    s = html.unescape(s)
    s = URL_RE.sub(lambda m: f" [url] {url_host(m.group(0))} ", s)
    s = _EMAIL.sub(" [email] ", s)
    s = _LONGNUM.sub(" [num] ", s)
    s = _ARTIFACT.sub(" ", s)
    s = _SPACES.sub(" ", s)
    s = _BLANKS.sub("\n", s)
    s = "\n".join(line.strip() for line in s.split("\n")).strip()
    if len(s) > CLEAN_HEAD_CHARS + CLEAN_TAIL_CHARS:
        s = s[:CLEAN_HEAD_CHARS] + "\n...\n" + s[-CLEAN_TAIL_CHARS:]
    return s


def build_text(subject, body):
    """The one canonical model input string."""
    subj = clean_text(subject).replace("\n", " ")[:300]
    return f"subject: {subj or '(none)'}\nbody: {clean_text(body)}"


_SPECIAL = {}


def _special_template(tokenizer):
    key = id(tokenizer)
    if key not in _SPECIAL:
        t = tokenizer("", add_special_tokens=True)["input_ids"]
        _SPECIAL[key] = (list(t[:1]), list(t[1:])) if len(t) >= 2 else ([], list(t))
    return _SPECIAL[key]


def encode(tokenizer, text, max_len, tail_tokens):
    """Head + tail truncation: keeps the start and the end of long emails."""
    prefix, suffix = _special_template(tokenizer)
    ids = tokenizer(text, add_special_tokens=False, truncation=False, verbose=False)["input_ids"]
    budget = max_len - len(prefix) - len(suffix)
    truncated = len(ids) > budget
    if truncated:
        tail = max(0, min(tail_tokens, budget // 2))
        ids = ids[: budget - tail] + (ids[-tail:] if tail else [])
    ids = prefix + ids + suffix
    return {"input_ids": ids, "attention_mask": [1] * len(ids), "truncated": truncated}


def decide(probs, phishing_threshold, uncertain_below):
    """PHISHING if p(phishing) >= threshold or it is the top class, else top class.
    Verdict UNCERTAIN when the top probability is below `uncertain_below`."""
    p = [float(x) for x in probs]
    top = max(range(3), key=lambda i: p[i])
    label = 2 if (p[2] >= phishing_threshold or top == 2) else top
    verdict = LABELS[label] if max(p) >= uncertain_below else "UNCERTAIN"
    return label, verdict


class ModelNotReady(RuntimeError):
    pass


class EmailClassifier:
    """Loads the saved model folder. Refuses to start if anything is missing or wrong."""

    def __init__(self, model_dir, device=None):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        d = Path(model_dir)
        missing = [f for f in ("config.json", "inference_config.json") if not (d / f).exists()]
        if not any((d / w).exists() for w in ("model.safetensors", "pytorch_model.bin")):
            missing.append("model weights")
        if missing:
            raise ModelNotReady(f"model folder incomplete, missing: {missing}")
        self.cfg = json.loads((d / "inference_config.json").read_text())
        self.tok = AutoTokenizer.from_pretrained(d, local_files_only=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(d, local_files_only=True)
        got = {int(k): v for k, v in self.model.config.id2label.items()}
        if self.model.config.num_labels != 3 or got != ID2LABEL:
            raise ModelNotReady(f"label map mismatch: {got}")
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device).eval()
        self._torch = torch

    def probs_batch(self, texts, batch_size=64):
        """texts = strings from build_text(). Returns (list of [p_legit, p_spam, p_phish], truncated flags)."""
        torch = self._torch
        enc = [encode(self.tok, t, self.cfg["max_length"], self.cfg["tail_tokens"]) for t in texts]
        trunc = [e.pop("truncated") for e in enc]
        order = sorted(range(len(enc)), key=lambda i: len(enc[i]["input_ids"]))
        out = [None] * len(enc)
        for s in range(0, len(order), batch_size):
            idx = order[s:s + batch_size]
            batch = self.tok.pad([enc[i] for i in idx], return_tensors="pt")
            batch = {k: v.to(self.device) for k, v in batch.items()}
            with torch.inference_mode():
                logits = self.model(**batch).logits.float()
            probs = torch.softmax(logits / self.cfg["temperature"], dim=-1).cpu().tolist()
            for i, row in zip(idx, probs):
                out[i] = row
        return out, trunc

    def predict(self, subject="", body=""):
        if not (str(subject or "").strip() or str(body or "").strip()):
            raise ValueError("empty email")
        if len(str(subject or "")) + len(str(body or "")) > MAX_INPUT_CHARS:
            raise ValueError(f"email longer than {MAX_INPUT_CHARS} characters")
        (p,), (truncated,) = self.probs_batch([build_text(subject, body)])
        label, verdict = decide(p, self.cfg["phishing_threshold"], self.cfg["uncertain_below"])
        return {
            "prediction": LABELS[label],
            "verdict": verdict,
            "confidence": round(p[label], 4),
            "probabilities": {LABELS[i]: round(p[i], 4) for i in range(3)},
            "truncated": truncated,
            "note": "Temperature-scaled model probability. Advisory only: a low phishing score is not a safety guarantee.",
        }

#%% [code]
import importlib, email_preprocess as EP
importlib.reload(EP)
LABELS = EP.LABELS
print(EP.build_text("URGENT: verify account", "<p>Click https://paypa1-login.example/x?id=998877 now or mail j@x.com</p>"))

# Meaning-preserving edits. Used twice: to augment training data (section 5.4) and to test stability (section 10).
# The last two are used ONLY in the stability test, never in training, so they show robustness to unseen edits.
prng = random.Random(SEED)
def typos(s, rate=0.02):
    w = s.split(" ")
    for i in range(len(w)):
        if len(w[i]) > 3 and prng.random() < rate:
            j = prng.randrange(len(w[i]) - 1); w[i] = w[i][:j] + w[i][j + 1] + w[i][j] + w[i][j + 2:]
    return " ".join(w)
PERTURB = {
    "lowercase":        lambda s, b: (s.lower(), b.lower()),
    "uppercase_subject":lambda s, b: (s.upper(), b),
    "extra_whitespace": lambda s, b: (s, re.sub(r" ", "  ", b).replace("\n", "\n\n")),
    "typos_2pct":       lambda s, b: (typos(s), typos(b)),
    "no_subject":       lambda s, b: ("", b),
    "add_signature":    lambda s, b: (s, b + "\n\nBest regards,\nAlex\nSent from my phone"),
    "forwarded":        lambda s, b: ("Fwd: " + s, "---------- Forwarded message ---------\n" + b),
    "html_wrapped":     lambda s, b: (s, "<html><body><p>" + b.replace("\n", "<br>") + "</p></body></html>"),
    "new_link_domain":  lambda s, b: (s, EP.URL_RE.sub(lambda m: f"http://site{prng.randint(1, 999)}.example.com/a", b)),
    "half_body":        lambda s, b: (s, b[: max(1, len(b) // 2)]),
    # unseen in training:
    "reply_quoted":     lambda s, b: ("Re: " + s, "Thanks, see below.\n\n" + "\n".join("> " + line for line in b.split("\n"))),
    "legal_footer":     lambda s, b: (s, b + "\n\nThis message and any attachments are confidential and intended only for the addressee."),
}
AUGMENT_EDITS = ["no_subject", "add_signature", "forwarded", "html_wrapped", "half_body", "typos_2pct", "new_link_domain"]

# Rough language guess from marker words, used only to break results down.
_LANG_MARKERS = {
    "english": re.compile(r"\b(your|you|the|account|please|click|verify|password)\b"),
    "portuguese": re.compile(r"\b(você|voce|sua|seu|não|nao|para|conta|acesso|senha|pagamento|boleto|cartão|cliente|olá)\b"),
    "spanish": re.compile(r"\b(usted|su cuenta|contraseña|pago|estimado|haga clic)\b"),
}
def language_of(subject, body):
    t = (str(subject) + " " + str(body)).lower()
    hits = {k: len(rx.findall(t)) for k, rx in _LANG_MARKERS.items()}
    best = max(hits, key=hits.get)
    return best if hits[best] >= 3 else "unclear"

#%% [markdown]
## 3. Load data

Label meanings follow the corpus families in the MeAJOR corpus paper (arXiv 2507.17978): CEAS-08, Ling-Spam, SpamAssassin and TREC are
**spam** corpora; Nazario and Nigerian Fraud are **phishing** corpora; Enron is mostly benign (this copy also has spam).
In these CSVs `label = 1` marks the corpus's malicious class. **Check the counts and samples printed below.**

Roles: `train` = training pool; `split` = divided later by near-duplicate cluster (Enron); `external` = locked test only.

#%% [code]
DATA_HINT = "phishing-email-dataset"
SPAM = {"0": "LEGITIMATE", "1": "SPAM"}
PHISH = {"0": "LEGITIMATE", "1": "PHISHING"}
SOURCES = [
    # name,            file,                 role,       label map,               labels kept
    ("CEAS_08",        "CEAS_08.csv",        "train",    SPAM,                    ["LEGITIMATE", "SPAM"]),
    ("SpamAssassin",   "SpamAssasin.csv",    "train",    SPAM,                    ["LEGITIMATE", "SPAM"]),
    ("TREC_07",        "TREC_07.csv",        "train",    SPAM,                    ["LEGITIMATE", "SPAM"]),
    ("Nazario",        "Nazario.csv",        "train",    PHISH,                   ["PHISHING"]),
    ("Nigerian_Fraud", "Nigerian_Fraud.csv", "train",    {"1": "PHISHING"},       ["PHISHING"]),
    ("Enron",          "Enron.csv",          "split",    SPAM,                    ["LEGITIMATE", "SPAM"]),
    ("Ling",           "Ling.csv",           "external", SPAM,                    ["LEGITIMATE", "SPAM"]),
    ("TREC_06",        "TREC_06.csv",        "external", SPAM,                    ["LEGITIMATE", "SPAM"]),
]
# To add your own CSV: ("MySource", "file.csv", "train"/"split"/"external", {"raw label": "LEGITIMATE"/"SPAM"/"PHISHING"}, [labels kept])

SUBJ_COLS = ["subject", "title"]
BODY_COLS = ["body", "text", "email_text", "text_combined", "message", "content", "email", "mail", "email text"]
LABEL_COLS = ["label", "class", "category", "type", "is_phishing", "target", "label_text", "email type"]

def norm_label(x):
    s = str(x).strip().lower()
    try:
        f = float(s)
        return str(int(f)) if f.is_integer() else s
    except ValueError:
        return s

def find_file(fname):
    hits = sorted(Path(CFG["INPUT_ROOT"]).rglob(fname))
    return ([p for p in hits if DATA_HINT in str(p)] or hits or [None])[0]

def read_csv_any(p):
    for enc in ("utf-8", "latin-1"):
        try:
            return pd.read_csv(p, encoding=enc, on_bad_lines="skip", low_memory=False, dtype=str)
        except UnicodeDecodeError:
            continue

frames, LOAD_LOG = [], []
for name, fname, role, lmap, keep in SOURCES:
    p = find_file(fname)
    if p is None:
        print(f"[missing] {name}: {fname} not found -> skipped"); continue
    raw = read_csv_any(p); raw.columns = [c.strip().lower() for c in raw.columns]
    sc = next((c for c in SUBJ_COLS if c in raw.columns), None)
    bc = next((c for c in BODY_COLS if c in raw.columns), None)
    lc = next((c for c in LABEL_COLS if c in raw.columns), None)
    assert bc and lc, f"{name}: no body/label column in {list(raw.columns)}"
    d = pd.DataFrame({"source": name, "role": role,
                      "subject": raw[sc].fillna("") if sc else "", "body": raw[bc].fillna(""),
                      "raw_label": raw[lc].map(norm_label)})
    d["row_id"] = [f"{name}:{i}" for i in range(len(d))]
    d["label"] = d["raw_label"].map(lmap)
    d["year"] = np.nan
    raw_counts = d["raw_label"].value_counts().to_dict()
    d = d[d["label"].isin(keep)].copy()
    for lab in keep:
        assert (d["label"] == lab).any(), f"{name}: no {lab} rows -> check label map"
    LOAD_LOG.append({"source": name, "role": role, "file": p.name, "raw_rows": len(raw),
                     "raw_label_counts": raw_counts, "kept_rows": len(d)})
    frames.append(d)
    print(f"[{role:8}] {name:<15} raw labels {raw_counts} -> kept {d['label'].value_counts().to_dict()}")
    for lab in keep:
        for s_, b_ in d[d.label == lab].sample(min(2, (d.label == lab).sum()), random_state=SEED)[["subject", "body"]].values:
            print(f"      {lab:<10}| {str(s_)[:60]!r} | {str(b_)[:100]!r}")

#%% [code]
# Modern phishing: rf-peixoto/phishing_pot (honeypot .eml files, CC BY-NC 4.0 -> non-commercial use, cite the repo).
# Split by the year in each email's Date header: older years train, one year dev, newest years = locked test.
PHISHING_POT_COMMIT = None
def eml_subject_body(path):
    msg = email.message_from_bytes(Path(path).read_bytes(), policy=email_policy.default)
    subject, body = str(msg.get("subject", "") or ""), ""
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
        body = part.get_content() if part is not None else ""
    except Exception:
        pass
    if not body:
        for part in msg.walk():
            if part.get_content_maintype() == "text":
                body = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", errors="replace")
                break
    return subject, body

def eml_year(path):
    try:
        with open(path, "rb") as f:
            hdr = BytesParser(policy=email_policy.default).parse(f, headersonly=True)
        return parsedate_to_datetime(str(hdr.get("date"))).year
    except Exception:
        return None

def pot_role(year):
    if year is None or year > time.gmtime().tm_year:      # missing or impossible dates are left out
        return None
    if year <= CFG["POT_TRAIN_MAX_YEAR"]:
        return "train"
    if year == CFG["POT_DEV_YEAR"]:
        return "dev"
    return "external" if year >= CFG["POT_TEST_MIN_YEAR"] else None

if CFG["USE_PHISHING_POT"]:
    dest = Path(CFG["POT_LOCAL_DIR"]) if CFG["POT_LOCAL_DIR"] else TMP / "phishing_pot"
    if not dest.exists():
        r = subprocess.run(["git", "clone", "--depth", "1", "https://github.com/rf-peixoto/phishing_pot.git", str(dest)],
                           capture_output=True, text=True, timeout=3600)
        if r.returncode:
            print("phishing_pot not available (Internet off?):", r.stderr[-300:])
    if dest.exists():
        git = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True, text=True)
        PHISHING_POT_COMMIT = git.stdout.strip() or "local copy"
        files = sorted(dest.rglob("*.eml"))
        t0 = time.time()
        by_role = {}
        for f in files:
            y = eml_year(f); role = pot_role(y)
            if role:
                by_role.setdefault(role, []).append((f, y))
        print(f"phishing_pot @ {PHISHING_POT_COMMIT[:10]}: {len(files)} files, dated in {time.time()-t0:.0f}s ->",
              {k: len(v) for k, v in by_role.items()}, f"| left out (no/impossible date): {len(files) - sum(map(len, by_role.values()))}")
        rows = []
        for role, items in by_role.items():
            for f, y in random.Random(SEED).sample(items, min(CFG["POT_MAX"][role], len(items))):
                try:
                    s_, b_ = eml_subject_body(f)
                    rows.append({"source": "phishing_pot", "role": role, "subject": s_, "body": b_, "raw_label": "phish",
                                 "label": "PHISHING", "row_id": f"phishing_pot:{f.name}", "year": y})
                except Exception:
                    pass
        frames.append(pd.DataFrame(rows))
        LOAD_LOG.append({"source": "phishing_pot", "role": "train (<=%d) / dev (%d) / external (>=%d)" % (
            CFG["POT_TRAIN_MAX_YEAR"], CFG["POT_DEV_YEAR"], CFG["POT_TEST_MIN_YEAR"]), "commit": PHISHING_POT_COMMIT,
            "raw_rows": len(files), "kept_rows": len(rows),
            "by_role": pd.DataFrame(rows).role.value_counts().to_dict() if rows else {}})

DF = pd.concat(frames, ignore_index=True)
DF["y"] = DF["label"].map(EP.LABEL2ID).astype(int)
print("total emails:", len(DF))

#%% [markdown]
## 4. Exploratory data analysis
### 4.1 Class balance per source

#%% [code]
counts = pd.crosstab([DF.role, DF.source], DF.label).reindex(columns=LABELS, fill_value=0)
print(counts)
ax = counts.droplevel(0).plot(kind="barh", stacked=True, figsize=(8, 4.5), color=["#4C9F70", "#E0A030", "#C8463C"])
ax.set_xlabel("emails"); ax.set_title("Emails per source and class (before cleaning)")
savefig("eda_class_balance")
print("Overall class share:", DF.label.value_counts(normalize=True).round(3).to_dict())
pot = DF[DF.source == "phishing_pot"]
if len(pot):
    print("phishing_pot by year and role:\n", pd.crosstab(pot.year.astype(int), pot.role))
    print("phishing_pot language (marker words):", pot.apply(lambda r: language_of(r.subject, r.body), axis=1).value_counts(normalize=True).round(3).to_dict())

#%% [markdown]
### 4.2 Missing fields and duplicates

#%% [code]
DF["_norm_body"] = DF.body.astype(str).str.lower().str.replace(r"[^a-z0-9]+", " ", regex=True).str.strip()
eda_q = DF.groupby("source").agg(
    emails=("body", "size"),
    empty_subject_pct=("subject", lambda s: round(100 * (s.astype(str).str.strip() == "").mean(), 1)),
    empty_body_pct=("_norm_body", lambda s: round(100 * (s == "").mean(), 1)),
    dup_body_within_source_pct=("_norm_body", lambda s: round(100 * s.duplicated().mean(), 1)))
print(eda_q)
dup_srcs = DF[DF._norm_body != ""].groupby("_norm_body").source.nunique()
print(f"\nbodies appearing in more than one source: {int((dup_srcs > 1).sum())}")
conf = DF[DF._norm_body != ""].groupby("_norm_body").label.nunique()
print(f"bodies with conflicting labels: {int((conf > 1).sum())}")
eda_q.to_csv(REPORTS / "eda_quality.csv")

#%% [markdown]
### 4.3 Length and structure by class

#%% [code]
body = DF.body.astype(str)
DF["_chars"] = body.str.len()
DF["_words"] = body.str.split().str.len()
DF["_urls"] = body.str.count(EP.URL_RE.pattern)
DF["_html"] = body.str.contains(r"<\s*(?:html|div|p|br|a|table)\b", case=False, regex=True)
DF["_excl"] = (DF.subject.astype(str) + " " + body).str.count("!")
DF["_upper_subject"] = DF.subject.astype(str).apply(lambda s: sum(c.isupper() for c in s) / max(1, sum(c.isalpha() for c in s)) > 0.5)

struct = DF.groupby("label").agg(median_chars=("_chars", "median"), median_words=("_words", "median"),
                                 pct_with_url=("_urls", lambda s: round(100 * (s > 0).mean(), 1)),
                                 mean_urls=("_urls", "mean"), pct_html=("_html", lambda s: round(100 * s.mean(), 1)),
                                 mean_exclamations=("_excl", "mean"),
                                 pct_shouting_subject=("_upper_subject", lambda s: round(100 * s.mean(), 1))).reindex(LABELS)
print(struct.round(2)); struct.to_csv(REPORTS / "eda_structure_by_class.csv")

fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
for lab, col in zip(LABELS, ["#4C9F70", "#E0A030", "#C8463C"]):
    w = DF.loc[DF.label == lab, "_words"].clip(lower=1)
    axes[0].hist(np.log10(w), bins=50, alpha=0.5, label=lab, color=col, density=True)
axes[0].set_xlabel("log10(words in body)"); axes[0].set_ylabel("density"); axes[0].legend(); axes[0].set_title("Body length")
struct[["pct_with_url", "pct_html", "pct_shouting_subject"]].plot(kind="bar", ax=axes[1], rot=0)
axes[1].set_ylabel("% of emails"); axes[1].set_title("Structural signals")
savefig("eda_length_structure")

#%% [markdown]
### 4.4 How many emails exceed the model's token limit?

#%% [code]
tok = AutoTokenizer.from_pretrained(CFG["MODEL_NAME"])
sample = strat_sample(DF, "label", 1500)
lens = [len(tok(EP.build_text(s, b), add_special_tokens=True, verbose=False)["input_ids"]) for s, b in zip(sample.subject, sample.body)]
sample = sample.assign(_tokens=lens)
over = sample.groupby("label")._tokens.apply(lambda s: round(100 * (s > CFG["MAX_LENGTH"]).mean(), 1)).reindex(LABELS)
print(f"% of emails longer than {CFG['MAX_LENGTH']} tokens (kept as head + last {CFG['TAIL_TOKENS']} tokens):", over.to_dict())
plt.figure(figsize=(6, 3.5))
for lab in LABELS:
    plt.hist(np.log10(sample.loc[sample.label == lab, "_tokens"]), bins=40, alpha=0.5, label=lab, density=True)
plt.axvline(np.log10(CFG["MAX_LENGTH"]), color="k", ls="--", label=f"limit {CFG['MAX_LENGTH']}")
plt.xlabel("log10(tokens)"); plt.legend(); plt.title("Token length after cleaning")
savefig("eda_token_length")

#%% [markdown]
### 4.5 Most indicative words per class

#%% [code]
samp = strat_sample(DF, ["source", "label"], 3000)
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
cv = CountVectorizer(min_df=5, max_features=50_000, stop_words=list(ENGLISH_STOP_WORDS | {"subject", "body", "url", "email", "num", "none"}), token_pattern=r"(?u)\b[a-z][a-z]{2,}\b", binary=True)
X = cv.fit_transform([EP.build_text(s, b) for s, b in zip(samp.subject, samp.body)])
vocab = np.array(cv.get_feature_names_out())
TOP_WORDS = {}
for lab in LABELS:
    m = (samp.label == lab).values
    p_in = np.asarray(X[m].mean(0)).ravel() + 1e-3; p_out = np.asarray(X[~m].mean(0)).ravel() + 1e-3
    TOP_WORDS[lab] = list(vocab[np.argsort(np.log(p_in / p_out))[::-1][:20]])
    print(f"{lab:<11}: {', '.join(TOP_WORDS[lab])}")

#%% [markdown]
## 5. Preprocessing
### 5.1 Clean text and drop near-empty emails

#%% [code]
t0 = time.time()
DF["text"] = [EP.build_text(s, b) for s, b in zip(DF.subject, DF.body)]
DF["_clean_body_chars"] = DF.text.str.split("\nbody: ", n=1).str[1].str.len().fillna(0)
short = DF._clean_body_chars < CFG["MIN_BODY_CHARS"]
DF = DF[~short].drop(columns=[c for c in DF.columns if c.startswith("_")]).reset_index(drop=True)
print(f"cleaned in {time.time()-t0:.0f}s, dropped {int(short.sum())} near-empty, {len(DF)} remain")

#%% [markdown]
### 5.2 Remove duplicates, split Enron by cluster, stop leakage
* Same text with different labels → all copies dropped.
* Exact duplicates → one copy kept, preferring the locked test, then dev, then training.
* Near-duplicates (MinHash on word 5-grams, Jaccard ≥ 0.8) → clusters. **Enron is split by cluster** (whole clusters go to train, dev or test).
* Training emails near-copies of dev/test emails are removed; dev emails near-copies of test emails are removed.

#%% [code]
DEDUP = {}
ROLE_RANK = {"external": 0, "dev": 1, "split": 2, "train": 3}
DF["key"] = [hashlib.sha1(re.sub(r"[^a-z0-9]+", " ", t.lower()).strip().encode()).hexdigest() for t in DF.text]
n0 = len(DF)
nlab = DF.groupby("key").label.nunique()
bad = set(nlab[nlab > 1].index)
DEDUP["label_conflicts_dropped"] = int(DF.key.isin(bad).sum())
DF = DF[~DF.key.isin(bad)]
DF = DF.assign(_rank=DF.role.map(ROLE_RANK)).sort_values(["_rank", "row_id"]) \
       .drop_duplicates("key").drop(columns="_rank").reset_index(drop=True)
DEDUP["exact_duplicates_dropped"] = n0 - DEDUP["label_conflicts_dropped"] - len(DF)

NUM_PERM, BANDS = 64, 8; ROWS = NUM_PERM // BANDS
_P = np.uint64((1 << 31) - 1); _r = np.random.default_rng(SEED)
_A = _r.integers(1, (1 << 31) - 1, NUM_PERM, dtype=np.uint64); _B = _r.integers(0, (1 << 31) - 1, NUM_PERM, dtype=np.uint64)
def minhash(t):
    w = re.findall(r"[a-z0-9]+", t.lower()[:3000])
    sh = {" ".join(w[i:i + 5]) for i in range(max(1, len(w) - 4))} or {""}
    x = np.fromiter((zlib.crc32(s.encode()) for s in sh), dtype=np.uint64, count=len(sh)) % _P
    return ((np.outer(x, _A) + _B) % _P).min(axis=0)
t0 = time.time()
SIG = np.vstack([minhash(t) for t in DF.text])
parent = np.arange(len(DF))
def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]; i = parent[i]
    return i
for b in range(BANDS):
    buckets = {}
    for i, k in enumerate(map(bytes, SIG[:, b * ROWS:(b + 1) * ROWS])):
        buckets.setdefault(k, []).append(i)
    for mem in buckets.values():
        if len(mem) > 1:
            sim = (SIG[mem[1:]] == SIG[mem[0]]).mean(1)
            for j, s in zip(mem[1:], sim):
                if s >= CFG["NEAR_DUP_JACCARD"]:
                    a, c = find(mem[0]), find(j)
                    if a != c:
                        parent[c] = a
DF["cluster"] = [find(i) for i in range(len(DF))]

# Enron: whole clusters to train / dev / external, by a stable hash of the cluster's first row id
first_id = DF.groupby("cluster").row_id.min()
def enron_role(cluster):
    h = int(hashlib.md5(first_id[cluster].encode()).hexdigest(), 16) % 100
    cut1, cut2 = CFG["ENRON_SPLIT"]["train"], CFG["ENRON_SPLIT"]["train"] + CFG["ENRON_SPLIT"]["dev"]
    return "train" if h < cut1 else ("dev" if h < cut2 else "external")
is_split = DF.role == "split"
DF.loc[is_split, "role"] = DF.loc[is_split, "cluster"].map(enron_role)

ext_clusters = set(DF.loc[DF.role == "external", "cluster"])
dev_clusters = set(DF.loc[DF.role == "dev", "cluster"])
leak_train = (DF.role == "train") & DF.cluster.isin(ext_clusters | dev_clusters)
leak_dev = (DF.role == "dev") & DF.cluster.isin(ext_clusters)
DEDUP["train_near_copies_of_dev_or_test_dropped"] = int(leak_train.sum())
DEDUP["dev_near_copies_of_test_dropped"] = int(leak_dev.sum())
DF = DF[~(leak_train | leak_dev)].reset_index(drop=True)
DEDUP["near_duplicate_clusters"] = int((DF.groupby("cluster").size() > 1).sum())
print(f"MinHash in {time.time()-t0:.0f}s ->", DEDUP)
print(pd.crosstab([DF.role, DF.source], DF.label))

#%% [markdown]
### 5.3 Split: train / validation / internal test (grouped by cluster) + external dev + locked external test

#%% [code]
pool = DF[DF.role == "train"]
rs = np.random.RandomState(SEED)
pool = pd.concat([g.sample(min(len(g), CFG["CAP_PER_SOURCE_LABEL"]), random_state=rs)
                  for _, g in pool.groupby(["source", "label"])]).reset_index(drop=True)
folds = [te for _, te in StratifiedGroupKFold(10, shuffle=True, random_state=SEED)
         .split(pool, pool.source + "|" + pool.label, groups=pool.cluster)]
pool["split"] = "train"; pool.loc[folds[0], "split"] = "test"; pool.loc[folds[1], "split"] = "val"
TRAIN, VAL, TEST = (pool[pool.split == s].reset_index(drop=True) for s in ("train", "val", "test"))
assert not set(TRAIN.cluster) & (set(VAL.cluster) | set(TEST.cluster)), "cluster leakage"

def capped(role, cap):
    part = DF[DF.role == role]
    if not len(part):
        return part.iloc[:0].assign(split=role)
    return pd.concat([g.sample(min(len(g), cap), random_state=rs) for _, g in part.groupby(["source", "label"])]) \
             .reset_index(drop=True).assign(split=role)
DEV = capped("dev", CFG["DEV_CAP_PER_SOURCE_LABEL"])
EXT = capped("external", CFG["EXTERNAL_CAP_PER_SOURCE_LABEL"])
for a_, b_ in [(TRAIN, DEV), (TRAIN, EXT), (DEV, EXT)]:
    assert not set(a_.cluster) & set(b_.cluster), "cluster leakage between training/dev/test"

ALL_SPLITS = pd.concat([TRAIN, VAL, TEST, DEV, EXT], ignore_index=True)
split_table = pd.crosstab([ALL_SPLITS.split, ALL_SPLITS.source], ALL_SPLITS.label).reindex(columns=LABELS, fill_value=0)
print(split_table); split_table.to_csv(REPORTS / "split_counts.csv")
ALL_SPLITS[["row_id", "source", "label", "split", "cluster"]].to_csv(REPORTS / "split_assignment.csv.gz", index=False)
for name, f in [("dev", DEV), ("external test", EXT)]:
    if not (f.label == "PHISHING").any():
        print(f"WARNING: no phishing in {name} -> phishing recall cannot be measured there (turn Internet on for phishing_pot).")

#%% [markdown]
### 5.4 Augmentation: edited copies of training emails
A share of training emails get one meaning-preserving edit (forwarded header, signature, no subject, HTML wrapping, half the body, typos, new link domain),
same label. v5 changed its answer on up to 19% of phishing under these edits. Two other edits are kept out of training to test on later.

#%% [code]
aug_src = TRAIN.sample(frac=CFG["AUGMENT_FRACTION"], random_state=SEED)
aug_rows = []
for _, r in aug_src.iterrows():
    edit = prng.choice(AUGMENT_EDITS)
    s_, b_ = PERTURB[edit](str(r.subject), str(r.body))
    aug_rows.append({**r.to_dict(), "subject": s_, "body": b_, "text": EP.build_text(s_, b_), "row_id": r.row_id + f"#aug:{edit}"})
AUG = pd.DataFrame(aug_rows)
TRAIN_FIT = pd.concat([TRAIN, AUG], ignore_index=True)
print(f"training emails: {len(TRAIN)} + {len(AUG)} edited copies = {len(TRAIN_FIT)} |", AUG.row_id.str.split("#aug:").str[1].value_counts().to_dict())

#%% [markdown]
### 5.5 Shortcut check (bag-of-words baseline)
If a simple TF-IDF model scores near-perfectly, or the *source* of an email is easy to predict from its text,
the model could learn dataset style instead of intent. The external test shows whether that happened.

#%% [code]
vec = TfidfVectorizer(min_df=3, max_features=200_000, ngram_range=(1, 2), sublinear_tf=True)
Xtr = vec.fit_transform(TRAIN.text)
base = LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced").fit(Xtr, TRAIN.y)
SHORTCUT = {"tfidf_val_macro_f1": round(float(f1_score(VAL.y, base.predict(vec.transform(VAL.text)), average="macro")), 4)}
if len(EXT):
    SHORTCUT["tfidf_external_macro_f1"] = round(float(f1_score(EXT.y, base.predict(vec.transform(EXT.text)),
                                                               labels=sorted(EXT.y.unique()), average="macro")), 4)
SHORTCUT["source_predictability"] = {}
for lab, g in TRAIN.groupby("label"):
    gv = VAL[VAL.label == lab]
    if g.source.nunique() > 1 and gv.source.nunique() > 1:
        m = LogisticRegression(max_iter=2000).fit(vec.transform(g.text), g.source)
        SHORTCUT["source_predictability"][lab] = {
            "accuracy": round(float(accuracy_score(gv.source, m.predict(vec.transform(gv.text)))), 3),
            "chance": round(float(gv.source.value_counts(normalize=True).iloc[0]), 3)}
print(json.dumps(SHORTCUT, indent=1))

#%% [markdown]
### 5.6 Tokenise

#%% [code]
class EncodedEmails(torch.utils.data.Dataset):
    """Plain PyTorch dataset of already-tokenised emails. (Hugging Face `datasets` is not needed, and its
    fingerprinting breaks with some pyarrow/dill versions.)"""
    def __init__(self, frame):
        self.items = []
        for t, y in zip(frame.text, frame.y.astype(int)):
            e = EP.encode(tok, t, CFG["MAX_LENGTH"], CFG["TAIL_TOKENS"])
            self.items.append({"input_ids": e["input_ids"], "attention_mask": e["attention_mask"], "labels": int(y)})
    def __len__(self):
        return len(self.items)
    def __getitem__(self, i):
        return self.items[i]

def to_ds(frame):
    return EncodedEmails(frame)
t0 = time.time()
DS = {name: to_ds(f) for name, f in [("train", TRAIN_FIT), ("val", VAL), ("test", TEST), ("dev", DEV), ("external", EXT)] if len(f)}
print({k: len(v) for k, v in DS.items()}, f"in {time.time()-t0:.0f}s")

#%% [markdown]
## 6. Model training
Class-weighted cross-entropy; best epoch chosen by validation macro-F1. Wrapped in a function so the stability section can retrain with other seeds.

#%% [code]
counts = np.bincount(TRAIN_FIT.y, minlength=3).astype(float)
CLASS_WEIGHTS = torch.tensor(counts.sum() / (3 * np.maximum(counts, 1)), dtype=torch.float)
print("train counts", dict(zip(LABELS, counts.astype(int))), "| class weights", [round(float(w), 3) for w in CLASS_WEIGHTS])

class WeightedTrainer(Trainer):
    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        out = model(**inputs)
        loss = torch.nn.functional.cross_entropy(out.logits.float(), labels, weight=CLASS_WEIGHTS.to(out.logits.device))
        return (loss, out) if return_outputs else loss

def cm_of(y, p):
    return np.bincount(np.asarray(y) * 3 + np.asarray(p), minlength=9).reshape(3, 3)

def compute_metrics(ev):
    logits, y = ev; p = logits.argmax(-1); cm = cm_of(y, p)
    return {"macro_f1": f1_score(y, p, average="macro"),
            "phish_recall": cm[2, 2] / max(cm[2].sum(), 1),
            "legit_false_alert": (cm[0, 1] + cm[0, 2]) / max(cm[0].sum(), 1)}

def train_model(seed, run_dir):
    seed_all(seed)
    model = AutoModelForSequenceClassification.from_pretrained(
        CFG["MODEL_NAME"], num_labels=3, id2label=EP.ID2LABEL, label2id=EP.LABEL2ID)
    steps = math.ceil(len(DS["train"]) / CFG["BATCH"]) * CFG["EPOCHS"]
    ta = dict(output_dir=str(run_dir), learning_rate=CFG["LR"], per_device_train_batch_size=CFG["BATCH"],
              per_device_eval_batch_size=CFG["EVAL_BATCH"], num_train_epochs=CFG["EPOCHS"],
              weight_decay=CFG["WEIGHT_DECAY"], warmup_steps=int(steps * CFG["WARMUP_RATIO"]),
              save_strategy="epoch", load_best_model_at_end=True, metric_for_best_model="macro_f1",
              greater_is_better=True, save_total_limit=1, logging_steps=50, fp16=(DEVICE == "cuda"),
              report_to="none", seed=seed, data_seed=seed)
    ta["eval_strategy" if "eval_strategy" in inspect.signature(TrainingArguments.__init__).parameters else "evaluation_strategy"] = "epoch"
    kw = dict(model=model, args=TrainingArguments(**ta), train_dataset=DS["train"], eval_dataset=DS["val"],
              data_collator=DataCollatorWithPadding(tok), compute_metrics=compute_metrics)
    kw["processing_class" if "processing_class" in inspect.signature(Trainer.__init__).parameters else "tokenizer"] = tok
    trainer = WeightedTrainer(**kw)
    t0 = time.time(); trainer.train()
    return trainer, time.time() - t0

trainer, TRAIN_SECONDS = train_model(SEED, TMP / "run_main")
HISTORY = pd.DataFrame([h for h in trainer.state.log_history if "eval_macro_f1" in h])
print(HISTORY[["epoch", "eval_loss", "eval_macro_f1", "eval_phish_recall", "eval_legit_false_alert"]].round(4))
print(f"trained in {TRAIN_SECONDS/60:.1f} min | best: {trainer.state.best_model_checkpoint}")

tr_loss = pd.DataFrame([h for h in trainer.state.log_history if "loss" in h and "eval_loss" not in h])
fig, ax = plt.subplots(1, 2, figsize=(10, 3.5))
if len(tr_loss):
    ax[0].plot(tr_loss.epoch, tr_loss.loss, label="train loss")
ax[0].plot(HISTORY.epoch, HISTORY.eval_loss, "o-", label="val loss"); ax[0].set_xlabel("epoch"); ax[0].legend()
for c in ["eval_macro_f1", "eval_phish_recall", "eval_legit_false_alert"]:
    ax[1].plot(HISTORY.epoch, HISTORY[c], "o-", label=c.replace("eval_", ""))
ax[1].set_xlabel("epoch"); ax[1].legend(); ax[1].set_title("Validation metrics")
savefig("training_curves")

#%% [markdown]
## 7. Calibration and decision threshold (validation + external dev; never the test set)
* **Temperature** is fitted on validation + external dev together, so probabilities match newer email too.
* **Phishing threshold**: the lowest threshold whose external-dev legitimate→PHISHING rate stays ≤ 5%, which catches the most dev phishing.

#%% [code]
def logits_of(trn, name):
    return torch.tensor(trn.predict(DS[name]).predictions, dtype=torch.float)

def ece(probs, y, bins=15):
    probs = probs.detach().float() if torch.is_tensor(probs) else torch.tensor(np.array(probs, dtype=np.float32))
    y = torch.tensor(np.array(y))
    conf, pred = probs.max(1); acc = (pred == y).float(); e = 0.0
    edges = torch.linspace(0, 1, bins + 1)
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            e += m.float().mean().item() * abs(acc[m].mean().item() - conf[m].mean().item())
    return round(e, 4)

CAL_NAMES = [n for n in ("val", "dev") if n in DS]
cal_logits = torch.cat([logits_of(trainer, n) for n in CAL_NAMES])
cal_y = torch.tensor(np.concatenate([{"val": VAL, "dev": DEV}[n].y.values for n in CAL_NAMES]))
log_t = torch.zeros(1, requires_grad=True)
opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=200)
def closure():
    opt.zero_grad(); loss = torch.nn.functional.cross_entropy(cal_logits / log_t.exp(), cal_y); loss.backward(); return loss
opt.step(closure)
TEMPERATURE = float(log_t.detach().exp().clamp(0.05, 20))
print(f"temperature {TEMPERATURE:.3f} (fitted on {'+'.join(CAL_NAMES)}) | ECE raw {ece(torch.softmax(cal_logits, 1), cal_y)} -> {ece(torch.softmax(cal_logits / TEMPERATURE, 1), cal_y)}")

TUNE = DEV if ("dev" in DS and (DEV.y == 2).any() and (DEV.y == 0).any()) else VAL
TUNE_NAME = "external dev" if TUNE is DEV else "validation (no usable dev set)"
P_tune = torch.softmax(logits_of(trainer, "dev" if TUNE is DEV else "val") / TEMPERATURE, 1).numpy()
grid = []
for t in np.round(np.arange(0.05, 0.505, 0.01), 2):
    p = P_tune.argmax(1); p[P_tune[:, 2] >= t] = 2; cm = cm_of(TUNE.y, p)
    grid.append({"threshold": t, "macro_f1": f1_score(TUNE.y, p, labels=sorted(TUNE.y.unique()), average="macro"),
                 "phish_recall": cm[2, 2] / max(cm[2].sum(), 1), "legit_to_phish": cm[0, 2] / max(cm[0].sum(), 1)})
grid = pd.DataFrame(grid)
ok = grid[grid.legit_to_phish <= CFG["TARGET_DEV_MAX_LEGIT_TO_PHISH"]]
best = (ok.sort_values(["phish_recall", "macro_f1", "threshold"], ascending=[False, False, False]) if len(ok)
        else grid.sort_values(["legit_to_phish", "threshold"], ascending=[True, False])).iloc[0]
PHISH_THRESHOLD = float(best.threshold)
print(f"phishing threshold {PHISH_THRESHOLD} on {TUNE_NAME}: phishing recall {best.phish_recall:.3f}, "
      f"legit->phishing {best.legit_to_phish:.3f}, macro-F1 {best.macro_f1:.3f}{'' if len(ok) else ' (LEGIT LIMIT NOT REACHED)'}")
grid.to_csv(REPORTS / "dev_threshold_grid.csv", index=False)

#%% [code]
# argmax metrics of this seed (used later in the seed-stability comparison)
def argmax_eval(trn):
    row = {}
    for name, frame in [("val", VAL), ("test", TEST), ("dev", DEV), ("external", EXT)]:
        if name not in DS:
            continue
        p = logits_of(trn, name).argmax(1).numpy(); cm = cm_of(frame.y, p)
        row[f"{name}_macro_f1"] = f1_score(frame.y, p, labels=sorted(frame.y.unique()), average="macro")
        if cm[2].sum():
            row[f"{name}_phish_recall"] = cm[2, 2] / cm[2].sum()
        if cm[0].sum():
            row[f"{name}_legit_false_alert"] = (cm[0, 1] + cm[0, 2]) / cm[0].sum()
        row[f"_{name}_pred"] = p
    return row
SEED_RUNS = {SEED: argmax_eval(trainer)}

#%% [markdown]
## 8. Save the model and prove it reloads

#%% [code]
trainer.save_model(str(OUT)); tok.save_pretrained(str(OUT))
INFER_CFG = {"labels": EP.ID2LABEL, "max_length": CFG["MAX_LENGTH"], "tail_tokens": CFG["TAIL_TOKENS"],
             "temperature": TEMPERATURE, "phishing_threshold": PHISH_THRESHOLD, "uncertain_below": CFG["UNCERTAIN_BELOW"],
             "base_model": CFG["MODEL_NAME"], "trained": time.strftime("%Y-%m-%d %H:%M"), "version": "v6"}
(OUT / "inference_config.json").write_text(json.dumps(INFER_CFG, indent=2))
shutil.copy(WORK / "email_preprocess.py", OUT / "email_preprocess.py")
(OUT / "training_args.bin").unlink(missing_ok=True)
saved_map = {int(k): v for k, v in json.loads((OUT / "config.json").read_text())["id2label"].items()}
assert saved_map == EP.ID2LABEL, saved_map
del trainer
if DEVICE == "cuda":
    torch.cuda.empty_cache()

check = f'''
import sys; sys.path.insert(0, {str(OUT)!r})
import email_preprocess as EP
clf = EP.EmailClassifier({str(OUT)!r})
r = clf.predict("Account notice", "Please verify your password at http://login-check.example")
assert set(r["probabilities"]) == set(EP.LABELS) and abs(sum(r["probabilities"].values()) - 1) < 1e-3
print("reload OK:", r["prediction"], r["probabilities"])
'''
r = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True, timeout=600,
                   env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
print(r.stdout.strip() or r.stderr[-2000:]); assert r.returncode == 0, "saved model does not reload"
print("model folder:", OUT, sorted(p.name for p in OUT.iterdir()))

#%% [markdown]
## 9. Evaluation
All predictions go through the **saved** model folder and `EmailClassifier`, the same path the website uses.
*Malicious caught* = phishing the model called SPAM or PHISHING (both give a warning on the website).

#%% [code]
CLF = EP.EmailClassifier(OUT)

def predict_df(frame, subjects=None, bodies=None, clf=None, ep=None):
    clf, ep = clf or CLF, ep or EP
    texts = (frame.text.tolist() if subjects is None and ep is EP
             else [ep.build_text(s, b) for s, b in zip(subjects if subjects is not None else frame.subject,
                                                        bodies if bodies is not None else frame.body)])
    probs, trunc = clf.probs_batch(texts, batch_size=CFG["EVAL_BATCH"])
    probs = np.asarray(probs)
    dec = [ep.decide(p, clf.cfg["phishing_threshold"], clf.cfg["uncertain_below"]) for p in probs]
    out = frame[["row_id", "source", "label", "y"]].copy().reset_index(drop=True)
    out["pred"] = [d[0] for d in dec]; out["verdict"] = [d[1] for d in dec]
    out["p_legit"], out["p_spam"], out["p_phish"] = probs[:, 0], probs[:, 1], probs[:, 2]
    return out

def metrics(y, p, probs=None):
    y, p = np.asarray(y), np.asarray(p); cm = cm_of(y, p); n = cm.sum(1)
    present = [i for i in range(3) if n[i]]
    m = {"n_legit": int(n[0]), "n_spam": int(n[1]), "n_phish": int(n[2]),
         "macro_f1": f1_score(y, p, labels=present, average="macro") if len(present) > 1 else np.nan,
         "accuracy": (y == p).mean(),
         "phish_recall": cm[2, 2] / n[2] if n[2] else np.nan,
         "phish_malicious_caught": (cm[2, 1] + cm[2, 2]) / n[2] if n[2] else np.nan,
         "phish_to_legit": cm[2, 0] / n[2] if n[2] else np.nan,
         "legit_false_alert": (cm[0, 1] + cm[0, 2]) / n[0] if n[0] else np.nan,
         "legit_to_phish": cm[0, 2] / n[0] if n[0] else np.nan,
         "spam_recall": cm[1, 1] / n[1] if n[1] else np.nan}
    if probs is not None:
        m["ece"] = ece(probs, y)
    return m

def bootstrap(y, p, B, keys=("macro_f1", "phish_recall", "phish_to_legit", "legit_false_alert")):
    y, p = np.asarray(y), np.asarray(p); rs = np.random.RandomState(SEED); vals = {k: [] for k in keys}
    for _ in range(B):
        i = rs.randint(0, len(y), len(y)); m = metrics(y[i], p[i])
        for k in keys:
            if not np.isnan(m[k]):
                vals[k].append(m[k])
    return {k: f"[{np.percentile(v, 2.5):.3f}, {np.percentile(v, 97.5):.3f}]" if v else "-" for k, v in vals.items()}

def report(pred, title, fname):
    probs = pred[["p_legit", "p_spam", "p_phish"]].values
    rows = {s: {**metrics(g.y, g.pred, g[["p_legit", "p_spam", "p_phish"]].values),
                "uncertain_rate": (g.verdict == "UNCERTAIN").mean()} for s, g in pred.groupby("source")}
    rows["ALL"] = {**metrics(pred.y, pred.pred, probs), "uncertain_rate": (pred.verdict == "UNCERTAIN").mean()}
    t = pd.DataFrame(rows).T
    ci = pd.DataFrame({s: bootstrap(g.y, g.pred, CFG["BOOTSTRAP"]) for s, g in [*pred.groupby("source"), ("ALL", pred)]}).T
    print(f"\n=== {title} ===\n", t.round(4).to_string(), "\n\n95% bootstrap intervals:\n", ci.to_string())
    t.to_csv(REPORTS / f"{fname}_metrics.csv"); ci.to_csv(REPORTS / f"{fname}_ci95.csv")
    return t

def plot_cm(pred, title, fname):
    cm = cm_of(pred.y, pred.pred); rown = cm / np.maximum(cm.sum(1, keepdims=True), 1)
    plt.figure(figsize=(4.2, 3.6)); plt.imshow(rown, cmap="Blues", vmin=0, vmax=1)
    for i in range(3):
        for j in range(3):
            plt.text(j, i, f"{cm[i, j]}\n{rown[i, j]:.0%}", ha="center", va="center", fontsize=8,
                     color="white" if rown[i, j] > 0.5 else "black")
    plt.xticks(range(3), LABELS, rotation=20); plt.yticks(range(3), LABELS)
    plt.xlabel("predicted"); plt.ylabel("true"); plt.title(title)
    savefig(fname)

PRED_TEST = predict_df(TEST)
INTERNAL = report(PRED_TEST, "INTERNAL TEST (held-out emails from training sources)", "internal_test")
plot_cm(PRED_TEST, "Internal test", "cm_internal")
print(classification_report(PRED_TEST.y, PRED_TEST.pred, labels=[0, 1, 2], target_names=LABELS, digits=3, zero_division=0))
DEV_REPORT = report(predict_df(DEV), "EXTERNAL DEV (used to tune temperature and threshold)", "external_dev") if len(DEV) else None

#%% [code]
EXTERNAL = None
if len(EXT):
    PRED_EXT = predict_df(EXT)
    EXTERNAL = report(PRED_EXT, "LOCKED EXTERNAL TEST (never used for training or tuning)", "external")
    plot_cm(PRED_EXT, "Locked external test", "cm_external")
    PRED_EXT.to_csv(REPORTS / "external_predictions.csv.gz", index=False)
    miss = PRED_EXT[(PRED_EXT.y == 2) & (PRED_EXT.pred == 0)].merge(EXT[["row_id", "text"]], on="row_id")
    fa = PRED_EXT[(PRED_EXT.y == 0) & (PRED_EXT.pred != 0)].merge(EXT[["row_id", "text"]], on="row_id")
    miss.assign(text=miss.text.str[:400]).to_csv(REPORTS / "external_phishing_missed_as_legit.csv", index=False)
    fa.assign(text=fa.text.str[:400]).to_csv(REPORTS / "external_legit_false_alerts.csv", index=False)
    print(f"\nPHISHING predicted LEGITIMATE (dangerous): {len(miss)} | LEGITIMATE flagged: {len(fa)}")

    # Breakdowns: phishing by year and by language (marker words)
    ph = PRED_EXT[PRED_EXT.y == 2].merge(EXT[["row_id", "year", "subject", "body"]], on="row_id")
    if len(ph):
        ph["lang"] = [language_of(s, b) for s, b in zip(ph.subject, ph.body)]
        BY_YEAR = ph.groupby(ph.year.fillna(0).astype(int)).apply(lambda g: pd.Series(metrics(g.y, g.pred))[["n_phish", "phish_recall", "phish_malicious_caught", "phish_to_legit"]])
        BY_LANG = ph.groupby("lang").apply(lambda g: pd.Series(metrics(g.y, g.pred))[["n_phish", "phish_recall", "phish_malicious_caught", "phish_to_legit"]])
        print("\nlocked test phishing by year:\n", BY_YEAR.round(3).to_string())
        print("\nlocked test phishing by language:\n", BY_LANG.round(3).to_string())
        BY_YEAR.to_csv(REPORTS / "external_phishing_by_year.csv"); BY_LANG.to_csv(REPORTS / "external_phishing_by_language.csv")

# Reliability diagram (calibration) on everything evaluated
allp = pd.concat([PRED_TEST] + ([PRED_EXT] if EXTERNAL is not None else []))
P = allp[["p_legit", "p_spam", "p_phish"]].values; conf = P.max(1); correct = (P.argmax(1) == allp.y.values)
bins = np.linspace(0, 1, 11); idx = np.clip(np.digitize(conf, bins) - 1, 0, 9)
acc = [correct[idx == b].mean() if (idx == b).any() else np.nan for b in range(10)]
fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
ax[0].plot([0, 1], [0, 1], "k--", lw=1); ax[0].plot((bins[:-1] + bins[1:]) / 2, acc, "o-")
ax[0].set_xlabel("confidence"); ax[0].set_ylabel("accuracy"); ax[0].set_title("Reliability (internal + external)")
ax[1].hist(conf, bins=20); ax[1].set_xlabel("top-class probability"); ax[1].set_title("Confidence distribution")
savefig("calibration")

#%% [markdown]
### 9.1 Previous model on the same locked test
If your v5 output is attached as an input, it is scored on exactly the same emails, so the two can be compared fairly.
It is loaded with **its own** `email_preprocess.py` and settings.

#%% [code]
COMPARISON = None
def find_previous_model():
    if CFG["PREVIOUS_MODEL_DIR"]:
        return Path(CFG["PREVIOUS_MODEL_DIR"])
    for cfg_file in sorted(Path(CFG["INPUT_ROOT"]).rglob("inference_config.json")):
        d = cfg_file.parent
        if d.resolve() != OUT.resolve() and (d / "email_preprocess.py").exists():
            return d
    return None

prev_dir = find_previous_model()
if prev_dir is None or not len(EXT):
    print("No previous model attached (or no locked test) -> comparison skipped.")
else:
    spec = importlib.util.spec_from_file_location("prev_email_preprocess", prev_dir / "email_preprocess.py")
    PEP = importlib.util.module_from_spec(spec); spec.loader.exec_module(PEP)
    prev = PEP.EmailClassifier(prev_dir)
    PRED_PREV = predict_df(EXT, clf=prev, ep=PEP)
    keys = ["phish_recall", "phish_malicious_caught", "phish_to_legit", "legit_false_alert", "macro_f1"]
    rows = {}
    for label, pr in [(f"previous ({prev.cfg.get('trained', '?')})", PRED_PREV), ("v6", PRED_EXT)]:
        for s, g in [*pr.groupby("source"), ("ALL", pr)]:
            rows[(s, label)] = {k: metrics(g.y, g.pred)[k] for k in keys}
    COMPARISON = pd.DataFrame(rows).T
    print("Same locked test, previous model vs v6:\n", COMPARISON.round(3).to_string())
    COMPARISON.to_csv(REPORTS / "comparison_previous_vs_v6.csv")
    del prev
    if DEVICE == "cuda":
        torch.cuda.empty_cache()

#%% [markdown]
## 10. Model stability tests
1. **Determinism** — same email twice, alone vs in a batch → identical output?
2. **Perturbation robustness** — small, meaning-preserving edits. `reply_quoted` and `legal_footer` were **not** used in training.
3. **Seed stability** — retrain with other random seeds; how much do the metrics move and how often do the models disagree?

#%% [code]
# 10.1 Determinism
probe = strat_sample(pd.concat([TEST, EXT]), "label", 50)
a = predict_df(probe); b = predict_df(probe)
single = np.array([CLF.probs_batch([t])[0][0] for t in probe.text[:30]])
DETERMINISM = {
    "max_prob_diff_repeat": float(np.abs(a[["p_legit", "p_spam", "p_phish"]].values - b[["p_legit", "p_spam", "p_phish"]].values).max()),
    "max_prob_diff_single_vs_batch": float(np.abs(single - a[["p_legit", "p_spam", "p_phish"]].values[:30]).max()),
    "label_changes_repeat": int((a.pred != b.pred).sum())}
print(DETERMINISM, "->", "STABLE" if DETERMINISM["label_changes_repeat"] == 0 and DETERMINISM["max_prob_diff_single_vs_batch"] < 1e-3 else "CHECK")

#%% [code]
# 10.2 Perturbation robustness (on the locked test + internal test)
stab = strat_sample(pd.concat([TEST, EXT]), "label", CFG["STABILITY_PER_CLASS"])
base_pred = predict_df(stab)
rows = []
for name, fn in PERTURB.items():
    sb = [fn(str(s), str(b)) for s, b in zip(stab.subject, stab.body)]
    pp = predict_df(stab, [x[0] for x in sb], [x[1] for x in sb])
    r = {"perturbation": name, "seen_in_training": name in AUGMENT_EDITS, "flip_rate_all": (pp.pred != base_pred.pred).mean(),
         "mean_abs_change_p_phish": np.abs(pp.p_phish - base_pred.p_phish).mean(),
         "accuracy_change": (pp.pred == stab.y).mean() - (base_pred.pred == stab.y).mean()}
    for lab in LABELS:
        m = (stab.label == lab).values
        r[f"flip_{lab.lower()}"] = (pp.pred[m] != base_pred.pred[m]).mean() if m.any() else np.nan
    caught = ((base_pred.pred == 2) & (stab.y == 2)).values
    r["caught_phish_now_legit"] = (pp.pred[caught] == 0).mean() if caught.any() else np.nan
    rows.append(r)
ROBUST = pd.DataFrame(rows).set_index("perturbation")
print(ROBUST.round(4).to_string()); ROBUST.to_csv(REPORTS / "stability_perturbations.csv")
ax = ROBUST[["flip_legitimate", "flip_spam", "flip_phishing"]].plot(kind="barh", figsize=(8, 5))
ax.set_xlabel("share of predictions that changed"); ax.set_title("Prediction flips under small edits (reply_quoted, legal_footer unseen)")
savefig("stability_perturbations")

#%% [code]
# 10.3 Seed stability (retrains the model; each extra seed costs about one training run)
for s in CFG["EXTRA_SEEDS"]:
    print(f"\n--- retraining with seed {s} ---")
    trn, _ = train_model(s, TMP / f"run_seed{s}")
    SEED_RUNS[s] = argmax_eval(trn)
    del trn
    if DEVICE == "cuda":
        torch.cuda.empty_cache()
SEED_TABLE = pd.DataFrame({s: {k: v for k, v in r.items() if not k.startswith("_")} for s, r in SEED_RUNS.items()}).T
if len(SEED_RUNS) > 1:
    seed_summary = SEED_TABLE.agg(["mean", "std", "min", "max"])
    print(SEED_TABLE.round(4).to_string(), "\n\nacross seeds:\n", seed_summary.round(4).to_string())
    key = "_external_pred" if "_external_pred" in SEED_RUNS[SEED] else "_test_pred"
    agree = {f"{SEED} vs {s}": float((SEED_RUNS[SEED][key] == r[key]).mean()) for s, r in SEED_RUNS.items() if s != SEED}
    print(f"\nprediction agreement with main model on {key[1:-5]} set:", {k: round(v, 4) for k, v in agree.items()})
    SEED_TABLE.to_csv(REPORTS / "stability_seeds.csv")
else:
    agree = {}
    print("EXTRA_SEEDS is empty -> seed stability skipped")

#%% [markdown]
## 11. Summary

#%% [code]
def fmt(x):
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.3f}"
ext_all = EXTERNAL.loc["ALL"] if EXTERNAL is not None else None
TARGETS = []
if ext_all is not None:
    for name, val, tgt, hi in [("external phishing recall", ext_all.phish_recall, CFG["TARGET_EXT_PHISH_RECALL"], True),
                               ("external phishing -> legitimate", ext_all.phish_to_legit, CFG["TARGET_EXT_PHISH_TO_LEGIT"], False),
                               ("external legit false alerts", ext_all.legit_false_alert, CFG["TARGET_EXT_LEGIT_FALSE_ALERT"], False)]:
        res = "NOT MEASURED" if np.isnan(val) else ("PASS" if (val >= tgt if hi else val <= tgt) else "FAIL")
        TARGETS.append((name, fmt(val), tgt, res))
print("Internal test : macro-F1", fmt(INTERNAL.loc["ALL"].macro_f1), "| phishing recall", fmt(INTERNAL.loc["ALL"].phish_recall),
      "| legit false alerts", fmt(INTERNAL.loc["ALL"].legit_false_alert))
if ext_all is not None:
    print("Locked test   : macro-F1", fmt(ext_all.macro_f1), "| phishing recall", fmt(ext_all.phish_recall),
          "| malicious caught", fmt(ext_all.phish_malicious_caught), "| legit false alerts", fmt(ext_all.legit_false_alert))
for t in TARGETS:
    print(f"  target {t[0]:<32} {t[1]:>6} (target {t[2]}) -> {t[3]}")
if COMPARISON is not None:
    print("\nPrevious vs v6 on the same locked test (ALL):\n", COMPARISON.loc["ALL"].round(3).to_string())
print("Stability     : worst perturbation flip rate", fmt(ROBUST.flip_rate_all.max()), f"({ROBUST.flip_rate_all.idxmax()})",
      "| seed agreement", {k: round(v, 3) for k, v in agree.items()} or "not run")
summary = {"version": "v6", "internal": INTERNAL.loc["ALL"].to_dict(), "external": None if ext_all is None else ext_all.to_dict(),
           "external_dev": None if DEV_REPORT is None else DEV_REPORT.loc["ALL"].to_dict(),
           "targets": TARGETS, "determinism": DETERMINISM, "perturbation_worst": ROBUST.flip_rate_all.max(),
           "seed_agreement": agree, "inference_config": INFER_CFG, "dedup": DEDUP, "shortcut_check": SHORTCUT,
           "comparison_previous_vs_v6_all": None if COMPARISON is None else COMPARISON.loc["ALL"].to_dict(),
           "data": LOAD_LOG, "phishing_pot_commit": PHISHING_POT_COMMIT,
           "split_design": {"phishing_pot": f"train <= {CFG['POT_TRAIN_MAX_YEAR']}, dev {CFG['POT_DEV_YEAR']}, test >= {CFG['POT_TEST_MIN_YEAR']}",
                            "enron": CFG["ENRON_SPLIT"], "fully_unseen_test_sources": ["Ling", "TREC_06"]}}
(REPORTS / "summary.json").write_text(json.dumps(summary, indent=2, default=lambda o: None if isinstance(o, float) and np.isnan(o) else str(o)))
print("\nSaved:", OUT.name + "/", "and", REPORTS.name + "/ (", len(list(REPORTS.rglob('*'))), "files )")
print("Use as an advisory tool. A low phishing score is not a safety guarantee.")
