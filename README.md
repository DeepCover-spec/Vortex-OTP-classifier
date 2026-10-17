# Vortex OTP Classifier

> First-time mobile-banking users and pensioners in Sri Lanka are tricked by SMS and WhatsApp messages
> in Sinhala, Tamil and Singlish that impersonate their bank to steal one-time passwords (OTPs)
> ("your account is blocked, share the code to reactivate"). We build a scam checker that flags these
> messages and detects when scammers switch to a new impersonated bank, new wording or a new language
> mix, before it silently fails.

## Who it protects and why now
TODO (P1 + P5): 3-4 lines. Link [IMPACT.md](IMPACT.md).

## Quick start
```bash
git clone https://github.com/DeepCover-spec/Vortex-OTP-classifier.git
cd Vortex-OTP-classifier
cp .env.example .env
docker compose up --build
# UI:  http://localhost:8501     API docs:  http://localhost:8000/docs
```
Without Docker (Python 3.11): `pip install -r requirements.txt`, `make train`,
`uvicorn api.main:app`, `streamlit run ui/app.py`. On Windows use `.\run.ps1 train`.

## Architecture
TODO (P1): docs/architecture.png plus one paragraph.

## Data
TODO (P2 + P1): sources with licences, test set, shifted set. UCI SMS Spam Collection (CC BY 4.0,
ham only). Synthetic generator with fictional banks and masked numbers. Mendeley set considered and
rejected (no licence stated).

## Results
TODO (P2): held-out test and shifted metrics table, baselines, per-language table.

## Monitoring and drift response
TODO (P3): signals, thresholds and how they were chosen, alert, safe fallback, human review,
retraining with promotion gate.

## Model card and limits
TODO (P2): intended use, data, metrics, known limits (synthetic data, dialect coverage, not a
replacement for bank verification).

## Impact
TODO (P5): summary and link to [IMPACT.md](IMPACT.md).

## AI tools used
TODO (all): list each tool and what it was used for. Every AI-written part was reviewed and run by
a team member before commit.

## Team
| Role | Name |
|------|------|
| P1 Lead, repo, integration | |
| P2 Data, model, evaluation | |
| P3 Monitoring, drift response | |
| P4 Backend, DevOps | |
| P5 Front end, impact, pitch | |
