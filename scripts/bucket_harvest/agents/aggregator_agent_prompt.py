"""
Aggregator Agent Prompt Template

This module contains the prompt template for the aggregator agent that
performs final ranking and selection of issues from all batch results.
"""

def create_aggregator_prompt(batch_results, criteria, repo_name, total_issues_processed):
    """
    Create a detailed prompt for the aggregator agent to rank all candidates.
    
    Args:
        batch_results (List[str]): Results from all batch agents
        criteria (str): Selection criteria loaded from user/selection-criteria.md  
        repo_name (str): Repository name for context
        total_issues_processed (int): Total number of issues analyzed
        
    Returns:
        str: Formatted prompt for the aggregator agent
    """
    
    # Combine all batch results
    all_candidates = ""
    total_candidates = 0
    
    for i, result in enumerate(batch_results, 1):
        all_candidates += f"\n## BATCH {i} RESULTS\n{result}\n"
        # Count candidates (assuming 3 per batch)
        total_candidates += result.count("**Candidate")
    
    prompt = f"""You are the final aggregator agent responsible for selecting the TOP 5 GitHub issues from all batch analysis results.

## Your Mission
Cross-analyze all candidate issues from {len(batch_results)} batches and select the 5 BEST overall issues that meet the selection criteria.

## Repository Context  
Repository: {repo_name.replace('_', '/')}
Total issues processed: {total_issues_processed}
Candidate issues to review: ~{total_candidates}
Batches analyzed: {len(batch_results)}

## Selection Criteria (Your North Star)
{criteria}

## All Candidate Issues from Batch Agents
{all_candidates}

## Your Analysis Process
1. **Review** all ~{total_candidates} candidate issues from the batches
2. **Cross-compare** scores and rationales across different batches  
3. **Identify** any duplicate issues or overlapping problems
4. **Re-evaluate** using the selection criteria with fresh perspective
5. **Rank** the TOP 5 issues globally (not just within individual batches)
6. **Validate** that your selections truly meet the SWE-focused criteria

## Scoring Weights for Final Ranking
Use these weights to calculate final composite scores:
- SWE Relevance: 30% (Must be true software engineering)
- Impact: 30% (Significant codebase improvement potential)  
- Viability: 25% (Well-documented, feasible to implement)
- Risk: 15% (Low breaking change risk, contained scope)

## Required Output Format

# 🏆 Top 5 GitHub Issues - Final Analysis Results

## Selection Methodology
[Brief explanation of how you cross-compared batches and made final selections]

---

### #1: Issue #{'{'}issue_id{'}'} - {'{'}title{'}'}
- **SWE Relevance**: X/10  
- **Impact**: X/10
- **Viability**: X/10
- **Risk**: X/10  
- **Final Composite Score**: X.X/10
- **GitHub URL**: https://github.com/{repo_name.replace('_', '/')}/issues/{'{'}issue_id{'}'}
- **Why #1**: [Detailed rationale explaining why this issue ranks highest overall. What makes it stand out from all other candidates?]
- **Implementation Notes**: [Key considerations for approaching this issue]

### #2: Issue #{'{'}issue_id{'}'} - {'{'}title{'}'}
- **SWE Relevance**: X/10
- **Impact**: X/10  
- **Viability**: X/10
- **Risk**: X/10
- **Final Composite Score**: X.X/10  
- **GitHub URL**: https://github.com/{repo_name.replace('_', '/')}/issues/{'{'}issue_id{'}'}
- **Why #2**: [Detailed rationale for second place ranking]
- **Implementation Notes**: [Key considerations for this issue]

### #3: Issue #{'{'}issue_id{'}'} - {'{'}title{'}'}
- **SWE Relevance**: X/10
- **Impact**: X/10
- **Viability**: X/10  
- **Risk**: X/10
- **Final Composite Score**: X.X/10
- **GitHub URL**: https://github.com/{repo_name.replace('_', '/')}/issues/{'{'}issue_id{'}'}  
- **Why #3**: [Detailed rationale for third place ranking]
- **Implementation Notes**: [Key considerations for this issue]

### #4: Issue #{'{'}issue_id{'}'} - {'{'}title{'}'}
- **SWE Relevance**: X/10
- **Impact**: X/10
- **Viability**: X/10
- **Risk**: X/10  
- **Final Composite Score**: X.X/10
- **GitHub URL**: https://github.com/{repo_name.replace('_', '/')}/issues/{'{'}issue_id{'}'}
- **Why #4**: [Detailed rationale for fourth place ranking]  
- **Implementation Notes**: [Key considerations for this issue]

### #5: Issue #{'{'}issue_id{'}'} - {'{'}title{'}'}
- **SWE Relevance**: X/10
- **Impact**: X/10
- **Viability**: X/10
- **Risk**: X/10
- **Final Composite Score**: X.X/10  
- **GitHub URL**: https://github.com/{repo_name.replace('_', '/')}/issues/{'{'}issue_id{'}'}
- **Why #5**: [Detailed rationale for fifth place ranking]
- **Implementation Notes**: [Key considerations for this issue]

---

## 📊 Analysis Summary

### Key Statistics
- **Total candidates reviewed**: {total_candidates}
- **Batches processed**: {len(batch_results)}  
- **Selection criteria applied**: [Brief summary of how criteria guided selections]

### Selection Patterns  
- **Common themes**: [What types of issues rose to the top?]
- **Key differentiators**: [What separated the top 5 from the rest?]
- **Excluded categories**: [What types of issues were consistently excluded?]

### Confidence Assessment
- **High confidence selections**: [Which issues are you most confident about?]
- **Considerations**: [Any caveats or additional factors to consider?]

## 🎯 Recommendation Priority
**Start with Issue #{'{'}top_issue_id{'}'}** - [One sentence summary of why this is the best starting point]

---

## Quality Assurance Checklist
Before finalizing, verify that your top 5:
- ✅ Are all genuine software engineering problems (not docs/frontend only)  
- ✅ Have significant potential impact on the codebase
- ✅ Are well-documented with clear problem statements
- ✅ Have reasonable implementation scope (not massive architectural changes)
- ✅ Don't duplicate each other or solve overlapping problems

## Final Validation
Double-check that each of your top 5 selections:
1. **Meets ALL selection criteria** from the user requirements
2. **Has higher composite score** than issues you excluded  
3. **Represents genuine value** for an open source contributor
4. **Is actionable** with the information provided in the issue

Your recommendations will directly influence which issue gets implemented, so ensure your analysis is thorough and your rationale is compelling.
"""
    
    return prompt