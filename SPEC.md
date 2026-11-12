# TrueNexus — Specification (as built, 12 Nov 2026)

An integrated machine learning system for URL and email phishing detection. Final-year B.Tech project, KIIT, Bhubaneswar.
Team: Vishwesh Shukla, Amrita Bhattacharyya, Jonnadula Hansika, Adriti Purkayastha, Anusha Bakshi, Shantanu Roy.
Supervisor: Ms. Indu Chaudhary, Assistant Professor.

## Scope
* **URL check:** string analysis only. LightGBM + character n-gram model, `mlphil_url_v6`. Output: score 0–100, band Low / Suspicious / High (Suspicious ≥ 78.0, High ≥ 95.5), plain-language evidence.
* **Email check:** pasted text or an uploaded `.eml` file (up to 2 MB; attachments ignored). DistilBERT 3-class model v6 (LEGITIMATE / SPAM / PHISHING, with UNCERTAIN), threshold 0.05. Every link in the email is also checked by the URL model (up to 20); the worst signal sets the overall result.
* **Accounts:** sign up, log in, log out, delete account (SQLite, Argon2id password hashes, hashed session tokens, HttpOnly SameSite=Strict cookie). Checks work without an account. *(Replaces the earlier "no database, no login".)*
* **Pages:** Home, URL, Email, How it works (measured results read from the model reports), About, Log in, Sign up, Account.
* **Deployment:** Docker Compose project `ml_phil`; only the frontend port is published; backend healthcheck; models mounted read-only.

## Stack
React + Vite + TypeScript + Tailwind; FastAPI (Python 3.12); SQLite; nginx in Docker. Tests: pytest, vitest + Testing Library + MSW, Playwright.

## Hard rules (unchanged)
R1 never fetch or open a submitted URL · R2 never say "safe" · R3 fail closed (UNAVAILABLE, never Low/LEGITIMATE) · R4 URLs shown defanged, never clickable · R5 email shown as plain text only · R6 never store or log email bodies or URLs · R7 model code and folders imported unchanged · R8 no invented metrics (read from reports, else "not yet available") · R9 no stack traces, paths or versions in API responses.
Added: accounts store only name, email, password hash and session hashes, never checked content.

## Known limits
* Email v6: flags many modern genuine service emails (receipts, one-time codes); promotional mail may be called PHISHING.
* URL v6: meets 4 of 6 acceptance targets (OpenPhish 61.9% vs 75%; internal phishing recall 76.3% vs 85%); adding `?lang=en` lowers ~18% of phishing one band.
* Advisory only; not a safety guarantee.
