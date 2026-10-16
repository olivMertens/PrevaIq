<#
.SYNOPSIS
    WorkbenchIQ — Index ALL policies (PDF + JSON) into the correct persona RAG tables.

.DESCRIPTION
    Indexes policy PDF documents via Document Intelligence and JSON policy files
    into PostgreSQL for RAG semantic search. Each file is routed to the correct
    persona table based on its category.

    Requires: DATABASE_BACKEND=postgresql, AZURE_OPENAI_* env vars set.

.PARAMETER Local
    Use PyMuPDF for PDF extraction instead of Azure Document Intelligence.

.PARAMETER Force
    Delete existing chunks before reindexing.

.EXAMPLE
    .\scripts\index-all-policies.ps1 -Local -Force
    .\scripts\index-all-policies.ps1
#>

param(
    [switch]$Local,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot)

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " WorkbenchIQ — Policy Indexer" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Index JSON policies (underwriting) into policy_chunks
Write-Host ">>> [1/4] Indexing Life & Health Underwriting policies..." -ForegroundColor Yellow
$forceFlag = if ($Force) { "--force" } else { "" }
uv run python scripts/index_policies.py --policies prompts/life-health-underwriting-policies.json $forceFlag
Write-Host "    Done" -ForegroundColor Green

# Step 2: Index JSON policies (habitation claims) into policy_chunks
Write-Host ""
Write-Host ">>> [2/4] Indexing Habitation claims policies (tempête, inondation, cat-nat)..." -ForegroundColor Yellow
uv run python scripts/index_policies.py --policies prompts/habitation-claims-policies.json $forceFlag
Write-Host "    Done" -ForegroundColor Green

# Step 3: Index policy PDFs into correct persona tables
Write-Host ""
Write-Host ">>> [3/4] Indexing policy PDF documents (4 PDFs → Document Intelligence)..." -ForegroundColor Yellow
$localFlag = if ($Local) { "--local" } else { "" }
uv run python scripts/index_pdf_policies.py --dir assets/pdf $forceFlag $localFlag
Write-Host "    Done" -ForegroundColor Green

# Step 4: Show summary
Write-Host ""
Write-Host ">>> [4/4] Index summary" -ForegroundColor Yellow
uv run python scripts/index_policies.py --stats

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Indexing Complete!" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Tables populated:" -ForegroundColor Gray
Write-Host "  policy_chunks                  ← Underwriting + Habitation CG + PDF Habitation" -ForegroundColor Gray
Write-Host "  claim_policy_chunks            ← PDF Auto + PDF Flotte Auto" -ForegroundColor Gray
Write-Host "  health_claims_policy_chunks    ← PDF Santé" -ForegroundColor Gray
Write-Host ""
Write-Host "RAG search is now available via Ask IQ for all personas." -ForegroundColor Green
