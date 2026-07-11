#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Parse SKILL.md frontmatter and generate a mermaid architecture diagram on the fly.

No file is saved. Every run prints the latest graph based on the current
frontmatter.

Usage:
  python render_architecture.py            # print both layer 1 + 2
  python render_architecture.py --layer 1  # phase swimlane
  python render_architecture.py --layer 2  # agent/model tier
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import re


# ── Constants ────────────────────────────────────────────────────────────────

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

PHASE_ORDER = ["init", "-1", "0", "1", "2", "3", "4", "any"]

PHASE_LABELS = {
    "init": "Init · Hub initialization",
    "-1":   "Phase -1 · Discovery",
    "0":    "Phase 0 · Ingest & Graph",
    "1":    "Phase 1 · Fanout",
    "2":    "Phase 2 · Draft",
    "3":    "Phase 3 · Integrate",
    "4":    "Phase 4 · Confirm & Publish",
    "any":  "Utilities · callable anytime",
}

# Gates to insert at phase boundaries (between the preceding phase and the next)
GATES_BETWEEN = {
    ("-1", "0"):  "discovery-exit-gate",
    ("0",  "1"):  "policy-entry-gate / graph-exit-gate",
    ("2",  "3"):  "draft-complete-gate",
    ("3",  "4"):  "integration-exit-gate",
}

MODEL_TIER = {
    "opus":          "OPUS",
    "claude-opus":   "OPUS",
    "sonnet":        "SONNET",
    "claude-sonnet": "SONNET",
    "haiku":         "HAIKU",
    "claude-haiku":  "HAIKU",
}


# ── Parser ───────────────────────────────────────────────────────────────────

def _parse_fm_field(fm: str, field: str) -> str | None:
    m = re.search(rf"^{field}:\s*(.+)$", fm, re.MULTILINE)
    return m.group(1).strip() if m else None


def load_skills() -> list[dict]:
    skills = []
    for path in sorted(glob.glob(str(SKILLS_DIR / "*/SKILL.md"))):
        text = Path(path).read_text(encoding="utf-8-sig")
        if not text.startswith("---"):
            continue
        parts = text.split("---", 2)
        if len(parts) < 2:
            continue
        fm = parts[1]
        name = _parse_fm_field(fm, "name")
        if not name:
            continue
        data = {
            "name":   name,
            "phase":  _parse_fm_field(fm, "phase") or "any",
            "agent":  _parse_fm_field(fm, "agent"),
            "model":  _parse_fm_field(fm, "model") or "sonnet",
            "effort": _parse_fm_field(fm, "effort") or "medium",
        }
        skills.append(data)
    return skills


def node_id(name: str) -> str:
    return name.replace("-", "_")


def effort_suffix(effort: str) -> str:
    return {"high": " ↑↑", "medium": " ↑", "low": ""}.get(effort, "")


# ── Layer 1: phase swimlane ────────────────────────────────────────────────────

def render_layer1(skills: list[dict]) -> str:
    by_phase: dict[str, list[dict]] = {p: [] for p in PHASE_ORDER}
    for s in skills:
        phase = str(s.get("phase", "any"))
        if phase not in by_phase:
            phase = "any"
        by_phase[phase].append(s)

    lines = [
        "```mermaid",
        "flowchart TD",
        "  %% Layer 1: Phase Swimlane",
        "  classDef gate fill:#111,color:#fff,stroke:#111",
        "  classDef util fill:#e7d8ff,stroke:#6a3d9a",
        "  classDef opus fill:#ffb3b3,stroke:#7a0000",
        "",
    ]

    prev_phase_key = None
    for phase in PHASE_ORDER:
        group = by_phase.get(phase, [])
        if not group:
            continue

        label = PHASE_LABELS[phase]
        sg_id = "SG_" + phase.replace("-", "NEG")

        if phase == "any":
            lines.append(f"  subgraph {sg_id} [\"{label}\"]")
            for s in group:
                nid = node_id(s["name"])
                suf = effort_suffix(s["effort"])
                lines.append(f"    {nid}[/{s['name']}{suf}/]")
            lines.append("  end")
            for s in group:
                nid = node_id(s["name"])
                lines.append(f"  class {nid} util")
            lines.append("")
            continue

        lines.append(f"  subgraph {sg_id} [\"{label}\"]")
        for s in group:
            nid = node_id(s["name"])
            suf = effort_suffix(s["effort"])
            tier = MODEL_TIER.get(s.get("model", ""), "")
            if tier == "OPUS":
                lines.append(f"    {nid}[/{s['name']}{suf}/]:::opus")
            else:
                lines.append(f"    {nid}[/{s['name']}{suf}/]")
        lines.append("  end")
        lines.append("")

        # insert a gate
        if prev_phase_key is not None:
            gate_key = (prev_phase_key, phase)
            if gate_key in GATES_BETWEEN:
                gate_label = GATES_BETWEEN[gate_key]
                gate_id = "GATE_" + phase.replace("-", "NEG")
                prev_sg = "SG_" + prev_phase_key.replace("-", "NEG")
                curr_sg = "SG_" + phase.replace("-", "NEG")
                lines.append(f'  {gate_id}{{"{gate_label}"}}:::gate')
                lines.append(f"  {prev_sg} --> {gate_id} --> {curr_sg}")
                lines.append("")
            else:
                prev_sg = "SG_" + prev_phase_key.replace("-", "NEG")
                curr_sg = "SG_" + phase.replace("-", "NEG")
                lines.append(f"  {prev_sg} --> {curr_sg}")
                lines.append("")

        prev_phase_key = phase

    lines.append("```")
    return "\n".join(lines)


# ── Layer 2: agent/model tier ──────────────────────────────────────────────────

def render_layer2(skills: list[dict]) -> str:
    # classify tiers
    tiers: dict[str, list[dict]] = {"OPUS": [], "SONNET": [], "OTHER": []}
    for s in skills:
        tier = MODEL_TIER.get(s.get("model", ""), "OTHER")
        tiers[tier].append(s)

    # agent -> skills mapping
    agent_map: dict[str, list[str]] = {}
    for s in skills:
        agent = s.get("agent")
        if agent:
            agent_map.setdefault(agent, []).append(s["name"])

    lines = [
        "```mermaid",
        "flowchart LR",
        "  %% Layer 2: Agent/Model Tier",
        "  classDef opus   fill:#ffb3b3,stroke:#7a0000",
        "  classDef sonnet fill:#b3d9ff,stroke:#003d7a",
        "  classDef other  fill:#e2e3e5,stroke:#383d41",
        "  classDef agent  fill:#ffe066,stroke:#806600,stroke-width:2px",
        "",
    ]

    if tiers["OPUS"]:
        lines.append("  subgraph OPUS_TIER [\"opus tier · cost ↑↑\"]")
        for s in tiers["OPUS"]:
            nid = node_id(s["name"])
            lines.append(f"    {nid}[/{s['name']}/]:::opus")
        lines.append("  end")
        lines.append("")

    if tiers["SONNET"]:
        lines.append("  subgraph SONNET_TIER [\"sonnet tier\"]")
        for s in tiers["SONNET"]:
            nid = node_id(s["name"])
            lines.append(f"    {nid}[/{s['name']}/]:::sonnet")
        lines.append("  end")
        lines.append("")

    if tiers["OTHER"]:
        lines.append("  subgraph OTHER_TIER [\"other tier\"]")
        for s in tiers["OTHER"]:
            nid = node_id(s["name"])
            lines.append(f"    {nid}[/{s['name']}/]:::other")
        lines.append("  end")
        lines.append("")

    # agent nodes + connections
    for agent_name, skill_names in sorted(agent_map.items()):
        aid = node_id(agent_name)
        lines.append(f"  {aid}[(\"{agent_name}\")]:::agent")
        for sname in skill_names:
            lines.append(f"  {node_id(sname)} --> {aid}")
        lines.append("")

    lines.append("```")
    return "\n".join(lines)


# ── Statistics summary ──────────────────────────────────────────────────────

def render_summary(skills: list[dict]) -> str:
    phase_counts = {}
    for s in skills:
        p = str(s.get("phase", "any"))
        phase_counts[p] = phase_counts.get(p, 0) + 1

    model_counts = {}
    for s in skills:
        m = s.get("model", "unknown")
        model_counts[m] = model_counts.get(m, 0) + 1

    agent_counts = {}
    for s in skills:
        a = s.get("agent")
        if a:
            agent_counts[a] = agent_counts.get(a, 0) + 1

    lines = [
        "## Statistics summary",
        f"- Total SKILLs: {len(skills)}",
        "",
        "### Phase distribution",
    ]
    for p in PHASE_ORDER:
        if p in phase_counts:
            lines.append(f"  - {PHASE_LABELS[p]}: {phase_counts[p]}")

    lines += ["", "### Model distribution"]
    for m, c in sorted(model_counts.items()):
        lines.append(f"  - {m}: {c}")

    lines += ["", "### Agent reuse"]
    for a, c in sorted(agent_counts.items()):
        skill_names = [s["name"] for s in skills if s.get("agent") == a]
        lines.append(f"  - {a}: {c} skill(s) ({', '.join(skill_names)})")

    return "\n".join(lines)


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    # Force UTF-8 since Windows CP949 stdout rejects unicode characters
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="orange-pm architecture mermaid generator")
    parser.add_argument(
        "--layer",
        choices=["1", "2", "all"],
        default="all",
        help="Layer to print (1=phase swimlane, 2=agent tier, all=both)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print the statistics summary",
    )
    args = parser.parse_args()

    skills = load_skills()
    if not skills:
        sys.exit(f"No SKILL.md files found: {SKILLS_DIR}")

    if args.layer in ("1", "all"):
        print("## Layer 1 — Phase Swimlane\n")
        print(render_layer1(skills))
        print()

    if args.layer in ("2", "all"):
        print("## Layer 2 — Agent / Model Tier\n")
        print(render_layer2(skills))
        print()

    if args.summary or args.layer == "all":
        print(render_summary(skills))


if __name__ == "__main__":
    main()
