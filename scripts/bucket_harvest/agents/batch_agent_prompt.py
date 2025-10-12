"""
Batch Agent Prompt Template

This module contains the standardized prompt template for batch agents
that analyze groups of 10 GitHub issues in parallel.
"""

def create_batch_prompt(batch_files, batch_number, criteria, repo_name):
    """
    Create a detailed prompt for a batch agent to analyze 10 GitHub issues.
    
    Args:
        batch_files (List[str]): List of file paths for issues in this batch
        batch_number (int): The batch number (1-10)  
        criteria (str): Selection criteria loaded from user/selection-criteria.md
        repo_name (str): Repository name for context
        
    Returns:
        str: Formatted prompt for the batch agent
    """
    
    # Read all issues in this batch
    batch_content = f"# Batch {batch_number} Issues for {repo_name}\n\n"
    
    for i, file_path in enumerate(batch_files, 1):
        import os
        issue_id = os.path.basename(file_path).replace('.md', '')
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                issue_content = f.read()
        except Exception as e:
            issue_content = f"Error reading issue file: {e}"
            
        batch_content += f"## Issue {i}: #{issue_id}\n\n{issue_content}\n\n---\n\n"
    
    prompt = f"""You are a specialized GitHub issue analyzer focusing on software engineering issues.

## Your Mission
Analyze the {len(batch_files)} issues in Batch {batch_number} and identify the TOP 3 most suitable candidates based on the selection criteria.

## Repository Context
Repository: {repo_name.replace('_', '/')}
Batch: {batch_number}/10  
Issues in this batch: {len(batch_files)}

## Selection Criteria
{criteria}

## Scoring Framework
Rate each issue on a 1-10 scale:

1. **SWE Relevance** (1-10): 
   - 10 = Core software engineering (APIs, algorithms, data structures, performance)
   - 5 = Mixed technical/non-technical  
   - 1 = Documentation-only or frontend-only

2. **Impact Score** (1-10):
   - 10 = Affects many users, core functionality, or major performance gains
   - 5 = Moderate impact on specific use cases
   - 1 = Minor edge case or cosmetic improvement

3. **Viability Score** (1-10):
   - 10 = Well-documented problem, clear reproduction steps, obvious solution path
   - 5 = Some documentation, need investigation  
   - 1 = Vague problem description, unclear requirements

4. **Risk Score** (1-10):
   - 10 = Low risk of breaking changes, well-contained scope
   - 5 = Some risk of scope creep or compatibility issues
   - 1 = High risk of major breaking changes or architectural changes

## Issues to Analyze
{batch_content}

## Required Output Format
Provide your analysis in this exact format:

### BATCH {batch_number} ANALYSIS RESULTS

#### TOP 3 CANDIDATES:

**Candidate 1: Issue #{'{'}issue_id{'}'} - {'{'}title{'}')**
- SWE Relevance: X/10
- Impact: X/10  
- Viability: X/10
- Risk: X/10
- Composite Score: X.X/10 (weighted average)
- Rationale: [2-3 sentences explaining why this is your top choice from this batch]

**Candidate 2: Issue #{'{'}issue_id{'}'} - {'{'}title{'}')**
- SWE Relevance: X/10
- Impact: X/10
- Viability: X/10  
- Risk: X/10
- Composite Score: X.X/10
- Rationale: [2-3 sentences explaining the selection]

**Candidate 3: Issue #{'{'}issue_id{'}'} - {'{'}title{'}')**
- SWE Relevance: X/10
- Impact: X/10
- Viability: X/10
- Risk: X/10  
- Composite Score: X.X/10
- Rationale: [2-3 sentences explaining the selection]

#### BATCH SUMMARY:
- Issues analyzed: {len(batch_files)}
- Excluded issues: [List any issues that clearly don't meet criteria]
- Key patterns: [Any patterns you noticed in this batch]

## Analysis Guidelines
- **Prioritize** issues with high SWE relevance and impact
- **Avoid** documentation-only fixes or frontend-only changes  
- **Favor** well-documented problems with clear technical solutions
- **Consider** implementation feasibility and risk of scope creep
- **Focus** on issues that would meaningfully improve the codebase

Calculate composite scores using: (SWE_Relevance * 0.3 + Impact * 0.3 + Viability * 0.25 + Risk * 0.15)
"""
    
    return prompt