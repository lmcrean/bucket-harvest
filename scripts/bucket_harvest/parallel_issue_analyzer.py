#!/usr/bin/env python3
"""
Parallel Issue Analyzer for GitHub Repositories

Analyzes collected GitHub issues using parallel Claude agents to identify
the top 5 most relevant issues based on user-defined selection criteria.

Architecture:
- 10 Batch Agents (parallel): Each analyzes 10 issues
- 1 Aggregator Agent (sequential): Ranks all candidates 

Usage:
    python parallel_issue_analyzer.py <repo_name>
    
Example:
    python parallel_issue_analyzer.py google_guava
    
The script will:
1. Read issues from data/<repo_name>/.{repo}/
2. Load criteria from user/selection-criteria.md
3. Launch 10 parallel batch agents 
4. Launch 1 aggregator agent
5. Save results to .notes/issue-analysis-{repo}-{timestamp}.md
"""

import sys
import os
import json
import glob
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

# Add the project root to the path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def load_selection_criteria() -> str:
    """Load selection criteria from user/selection-criteria.md"""
    criteria_path = project_root / "user" / "selection-criteria.md"
    
    if not criteria_path.exists():
        raise FileNotFoundError(f"Selection criteria not found at {criteria_path}")
    
    with open(criteria_path, 'r', encoding='utf-8') as f:
        return f.read()

def load_exclusions() -> List[str]:
    """Load issue IDs to exclude from user/exclusions.txt"""
    exclusions_path = project_root / "user" / "exclusions.txt"
    
    if not exclusions_path.exists():
        return []
    
    with open(exclusions_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def get_issue_files(repo_input: str) -> List[str]:
    """Get all issue markdown files for a repository"""
    # Handle both formats: 'owner/repo' or 'owner_repo'
    if '/' in repo_input:
        # Format: shopify/cli -> shopify_cli and .cli
        org, repo = repo_input.split('/', 1)
        repo_name = f"{org}_{repo}"
        issue_dir = f".{repo}"
    elif '_' in repo_input:
        # Legacy format: shopify_cli -> .cli
        org, repo = repo_input.split('_', 1)
        repo_name = repo_input
        issue_dir = f".{repo}"
    else:
        # Single name format
        repo_name = repo_input
        issue_dir = f".{repo_input}"
    
    data_path = Path(__file__).parent / "repo_to_issues" / "data" / repo_name / issue_dir
    
    if not data_path.exists():
        raise FileNotFoundError(f"Issue data directory not found at {data_path}")
    
    # Get all .md files except any that might be summaries
    issue_files = sorted(glob.glob(str(data_path / "*.md")))
    
    # Filter out any non-numeric filenames (like summaries)
    numeric_issues = []
    for file_path in issue_files:
        filename = os.path.basename(file_path)
        issue_id = filename.replace('.md', '')
        if issue_id.isdigit():
            numeric_issues.append(file_path)
    
    return sorted(numeric_issues, key=lambda x: int(os.path.basename(x).replace('.md', '')))

def filter_excluded_issues(issue_files: List[str], exclusions: List[str]) -> List[str]:
    """Remove excluded issues from the list"""
    if not exclusions:
        return issue_files
    
    filtered = []
    for file_path in issue_files:
        issue_id = os.path.basename(file_path).replace('.md', '')
        if issue_id not in exclusions:
            filtered.append(file_path)
    
    return filtered

def normalize_repo_name(repo_input: str) -> str:
    """Convert repo input to consistent format for file naming"""
    if '/' in repo_input:
        return repo_input.replace('/', '_')
    return repo_input

def create_issue_batches(issue_files: List[str], batch_size: int = 10) -> List[List[str]]:
    """Split issue files into batches for parallel processing"""
    batches = []
    for i in range(0, len(issue_files), batch_size):
        batch = issue_files[i:i + batch_size]
        batches.append(batch)
    return batches

def read_issue_content(file_path: str) -> str:
    """Read and return the content of an issue file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def create_batch_agent_prompt(batch_files: List[str], batch_number: int, criteria: str) -> str:
    """Create a detailed prompt for a batch agent"""
    
    # Read all issues in this batch
    batch_content = f"# Batch {batch_number} Issues\n\n"
    
    for i, file_path in enumerate(batch_files, 1):
        issue_id = os.path.basename(file_path).replace('.md', '')
        issue_content = read_issue_content(file_path)
        batch_content += f"## Issue {i}: #{issue_id}\n\n{issue_content}\n\n---\n\n"
    
    prompt = f"""You are analyzing GitHub issues to find the best candidates based on specific selection criteria.

## Your Task
Analyze the {len(batch_files)} issues in Batch {batch_number} and identify the TOP 3 most suitable candidates.

## Selection Criteria
{criteria}

## Scoring Framework
Score each issue on a 1-10 scale for:
1. **SWE Relevance** (1-10): Pure software engineering vs docs/frontend
2. **Impact Score** (1-10): Significance of potential codebase improvement
3. **Viability Score** (1-10): Implementation feasibility + problem documentation quality
4. **Risk Score** (1-10): Low risk of breaking changes/scope creep (10 = lowest risk)

## Issues to Analyze
{batch_content}

## Required Output Format
Return your analysis as a structured response with:

### TOP 3 CANDIDATES FROM BATCH {batch_number}

#### Candidate 1: Issue #[ID]
- **Title**: [Issue title]
- **SWE Relevance**: X/10
- **Impact**: X/10
- **Viability**: X/10  
- **Risk**: X/10
- **Composite Score**: X.X/10
- **Rationale**: [2-3 sentences explaining why this issue meets the criteria]

#### Candidate 2: Issue #[ID]
[Same format]

#### Candidate 3: Issue #[ID]
[Same format]

Focus on issues that are clearly software engineering problems with high impact potential and low implementation risk. Exclude documentation-only or frontend-only fixes as specified in the criteria.
"""
    return prompt

def create_aggregator_agent_prompt(batch_results: List[str], criteria: str) -> str:
    """Create a prompt for the aggregator agent to rank all candidates"""
    
    all_candidates = "\n\n".join([f"## Batch {i+1} Results\n{result}" for i, result in enumerate(batch_results)])
    
    prompt = f"""You are the final aggregator analyzing candidates from 10 different batches of GitHub issues.

## Your Task
Review all candidate issues from the batch agents and select the TOP 5 OVERALL best issues that meet the selection criteria.

## Selection Criteria
{criteria}

## Candidate Issues from All Batches
{all_candidates}

## Your Analysis Process
1. Review all ~30 candidate issues from the batches
2. Cross-compare scores and rationales across batches
3. Identify any duplicates or overlapping issues
4. Re-evaluate using the selection criteria
5. Rank the TOP 5 issues globally (not just within batches)

## Required Output Format

# Top 5 GitHub Issues - Final Recommendations

## Selection Methodology
Brief description of how you cross-compared and ranked the issues.

### #1: Issue #[ID] - [Title]
- **SWE Relevance**: X/10
- **Impact**: X/10
- **Viability**: X/10  
- **Risk**: X/10
- **Overall Score**: X.X/10
- **GitHub URL**: https://github.com/google/guava/issues/[ID]
- **Why #1**: [Detailed rationale for top ranking]

### #2: Issue #[ID] - [Title]
[Same format]

### #3: Issue #[ID] - [Title]
[Same format]

### #4: Issue #[ID] - [Title]
[Same format]

### #5: Issue #[ID] - [Title]
[Same format]

## Analysis Summary
- Total candidates reviewed: ~XX
- Selection criteria applied: [Brief summary]
- Key differentiators: [What made the top 5 stand out]

Ensure your top 5 represent the highest-impact, most viable software engineering issues with the lowest risk of scope creep or breaking changes.
"""
    return prompt

def save_results(repo_input: str, aggregator_result: str, criteria: str, total_issues: int, excluded_count: int):
    """Save the final analysis results to .notes/"""
    repo_name = normalize_repo_name(repo_input)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"issue-analysis-{repo_name}-{timestamp}.md"
    
    # Ensure .notes directory exists
    notes_dir = project_root / ".notes"
    notes_dir.mkdir(exist_ok=True)
    
    output_path = notes_dir / filename
    
    # Create comprehensive output
    output_content = f"""# GitHub Issue Analysis: {repo_input}

**Analysis Date**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
**Repository**: {repo_input}  
**Issues Processed**: {total_issues}  
**Excluded Issues**: {excluded_count}  
**Processing Method**: 10 Parallel Batch Agents + 1 Aggregator Agent  

## Selection Criteria Applied

{criteria}

---

{aggregator_result}

---

## Methodology Notes

This analysis used a parallel agent architecture:
1. **Stage 1**: 10 Claude agents processed issues in batches of 10
2. **Stage 2**: 1 aggregator agent cross-compared all ~30 candidates  
3. **Scoring**: 4-dimensional scoring (SWE Relevance, Impact, Viability, Risk)
4. **Final Ranking**: Top 5 issues selected based on composite scores and rationales

## Next Steps

1. Review the GitHub URLs for each recommended issue
2. Read the full issue descriptions and comment threads
3. Add any issues you decide against to `user/exclusions.txt`
4. Begin implementation on your selected issue

---

*Generated by Claude Code Parallel Issue Analyzer*
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output_content)
    
    return output_path

def main():
    if len(sys.argv) != 2:
        print("Usage: python parallel_issue_analyzer.py <owner/repo>")
        print("Example: python parallel_issue_analyzer.py shopify/cli")
        print("Example: python parallel_issue_analyzer.py google/guava")
        sys.exit(1)
    
    repo_input = sys.argv[1]
    repo_name = normalize_repo_name(repo_input)
    
    try:
        print(f"[ANALYZE] Analyzing issues for {repo_input}...")
        
        # Load configuration
        print("[CONFIG] Loading selection criteria...")
        criteria = load_selection_criteria()
        
        print("[CONFIG] Loading exclusions...")
        exclusions = load_exclusions()
        
        # Get and filter issues
        print("[COLLECT] Collecting issue files...")
        issue_files = get_issue_files(repo_input)
        print(f"   Found {len(issue_files)} total issues")
        
        filtered_files = filter_excluded_issues(issue_files, exclusions)
        excluded_count = len(issue_files) - len(filtered_files)
        if excluded_count > 0:
            print(f"   Excluded {excluded_count} issues")
        
        print(f"   Processing {len(filtered_files)} issues")
        
        # Create batches
        batches = create_issue_batches(filtered_files)
        print(f"[BATCH] Created {len(batches)} batches for parallel processing")
        
        # This is where we would launch the Claude agents
        # For now, we'll create the prompts and show the structure
        print("\n[AGENTS] Ready to launch parallel agents:")
        print(f"   - {len(batches)} batch agents (analyzing {len(filtered_files)} issues)")
        print("   - 1 aggregator agent (final ranking)")
        
        # Create batch prompts for verification
        print("\n[PROMPTS] Batch agent prompts created:")
        for i, batch in enumerate(batches):
            prompt = create_batch_agent_prompt(batch, i+1, criteria)
            print(f"   Batch {i+1}: {len(batch)} issues (ready for Claude agent)")
        
        print(f"\n[SUCCESS] System ready! Run with Claude Code Task agents to process {len(filtered_files)} issues.")
        print(f"   Results will be saved to .notes/issue-analysis-{repo_name}-<timestamp>.md")
        
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()