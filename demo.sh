#!/usr/bin/env bash
# demo.sh — Live demo script for judges
# Usage: bash demo.sh
# Assumes the server is running: uvicorn main:app --reload

BASE="http://localhost:8000"
SEP="────────────────────────────────────────────────────────"

echo ""
echo "$SEP"
echo "  🏦  LOAN WORKFLOW DECISION ENGINE — LIVE DEMO"
echo "$SEP"

# ── 1. Health Check ─────────────────────────────────────────────────────────
echo ""
echo "▶  1. HEALTH CHECK"
curl -s "$BASE/health" | python3 -m json.tool
sleep 1

# ── 2. Auto-Reject (credit score < 500) ─────────────────────────────────────
echo ""
echo "$SEP"
echo "▶  2. AUTO-REJECT — Credit score 400 (hard reject rule R003)"
curl -s -X POST "$BASE/applications" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-reject-001" \
  -d '{
    "request_id": "DEMO-REJ-001",
    "name": "Bad Credit Barry",
    "age": 35,
    "income": 50000,
    "loan_amount": 100000,
    "credit_score": 400,
    "documents_submitted": true
  }' | python3 -m json.tool
sleep 1

# ── 3. Auto-Approve (credit score ≥ 750) ────────────────────────────────────
echo ""
echo "$SEP"
echo "▶  3. AUTO-APPROVE — Credit score 800, strong income"
curl -s -X POST "$BASE/applications" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-approve-001" \
  -d '{
    "request_id": "DEMO-APP-001",
    "name": "Alice Excellent",
    "age": 42,
    "income": 120000,
    "loan_amount": 300000,
    "credit_score": 800,
    "documents_submitted": true
  }' | python3 -m json.tool
sleep 1

# ── 4. AI Review — Ambiguous Case ───────────────────────────────────────────
echo ""
echo "$SEP"
echo "▶  4. AI-ASSISTED REVIEW — Borderline credit (620), missing docs"
echo "   (AI agent will analyze and recommend)"
curl -s -X POST "$BASE/applications" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-ai-001" \
  -d '{
    "request_id": "DEMO-AI-001",
    "name": "Borderline Bob",
    "age": 29,
    "income": 45000,
    "loan_amount": 80000,
    "credit_score": 615,
    "documents_submitted": false
  }' | python3 -m json.tool
sleep 1

# ── 5. Idempotency (duplicate key) ──────────────────────────────────────────
echo ""
echo "$SEP"
echo "▶  5. IDEMPOTENCY — Same key as request #3 → cached result"
curl -s -X POST "$BASE/applications" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-approve-001" \
  -d '{
    "request_id": "DEMO-APP-001",
    "name": "Alice Excellent",
    "age": 42,
    "income": 120000,
    "loan_amount": 300000,
    "credit_score": 800,
    "documents_submitted": true
  }' | python3 -m json.tool
sleep 1

# ── 6. Full Audit Trail ──────────────────────────────────────────────────────
echo ""
echo "$SEP"
echo "▶  6. AUDIT TRAIL — Full event log for DEMO-REJ-001"
curl -s "$BASE/applications/DEMO-REJ-001/audit" | python3 -m json.tool
sleep 1

# ── 7. View Live Config ──────────────────────────────────────────────────────
echo ""
echo "$SEP"
echo "▶  7. LIVE CONFIG — Current rules (no restart needed to change)"
curl -s "$BASE/config/rules" | python3 -m json.tool

echo ""
echo "$SEP"
echo "  ✅  Demo complete. All scenarios demonstrated."
echo "$SEP"
echo ""