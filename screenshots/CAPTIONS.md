# ML Phil screenshots

Captured 11 November 2026 from the running Docker build (`ml_phil`), both real models loaded.
Email model: **v6** (trained 2026-11-11 09:44). URL model: **v6** (`mlphil_url_v6`). Shots 02–05, 08, 09 and mobile/01 were retaken after the URL switch from v5.
Desktop shots: 1440 × 900 at 2× (2880 px wide). Phone shots: 390 px wide at 3×.
`light/` and `dark/` hold the same 12 shots in each theme. All example inputs are fictional (`.xyz`, `.example`) except `kiit.ac.in`.

| File | Suggested caption |
|---|---|
| 01_home.png | Home page: the two checks, URL and email. |
| 02_url_high_risk.png | URL check, High phishing risk: score 100/100 with band marks, what to do, evidence, and the address shown defanged (never clickable). |
| 03_url_no_warning.png | URL check, no warning signs: shown as "not a safety guarantee", never as "safe". |
| 04_url_suspicious.png | URL check, Suspicious band (83.5; Suspicious from 78.0, High from 95.5). |
| 05_email_phishing_with_links.png | Email check: overall High risk banner, the email model's probabilities, and every link in the email checked by the URL model. |
| 06_email_spam.png | The "90% off" promotional example: v6 classifies it as PHISHING (74.7%), where v5 said spam. phishing_pot, which v6 trained on, labels everything as phishing, including some promotional mail. |
| 07_email_legitimate.png | Email check with no phishing or spam pattern found (advisory only). |
| 08_email_eml_upload.png | Uploaded .eml file: links taken from the HTML (including the hidden href target); the attachment was ignored. |
| 09_how_it_works.png | How it works: both model pipelines, their limits, and both models' measured results read from their training reports (URL: test and external feeds with 95% ranges and pass/fail against the targets; email: with an explanation of how the test was kept apart from training). |
| 10_about.png | About: what is stored, technology used, dataset credits and licences. |
| 11_login.png | Log in page. |
| 12_signup.png | Sign up page. |
| mobile/01_url_high_risk.png | Phone layout, URL check. |
| mobile/02_email_phishing.png | Phone layout, email check with link table. |
