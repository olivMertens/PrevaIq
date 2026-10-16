"""WorkbenchIQ Agent Framework — Microsoft Agent Framework integration.

This package provides agentic wrappers around the existing workbench pipeline,
organized into 4 phases of migration:

- Phase 1: ChatAgent — Ask IQ chat with tool use (RAG search, policy lookup)
- Phase 2: AnalysisAgent — Prompt-based analysis with dynamic tool selection
- Phase 3: DocumentAgent — Content Understanding with intelligent retry
- Phase 4: Workflow — Multi-agent orchestration (Document → Analysis → Risk)
"""

from __future__ import annotations
