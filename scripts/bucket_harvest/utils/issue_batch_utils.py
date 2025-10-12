"""
Issue Batch Utilities

Helper functions for processing GitHub issues in batches for parallel analysis.
"""

import os
import json
import glob
from pathlib import Path
from typing import List, Dict, Tuple, Optional

def load_selection_criteria(project_root: Path) -> str:
    """Load selection criteria from user/selection-criteria.md"""
    criteria_path = project_root / "user" / "selection-criteria.md"
    
    if not criteria_path.exists():
        raise FileNotFoundError(f"Selection criteria not found at {criteria_path}")
    
    with open(criteria_path, 'r', encoding='utf-8') as f:
        return f.read()

def load_exclusions(project_root: Path) -> List[str]:
    """Load issue IDs to exclude from user/exclusions.txt"""
    exclusions_path = project_root / "user" / "exclusions.txt"
    
    if not exclusions_path.exists():
        return []
    
    with open(exclusions_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def get_issue_files(repo_name: str, base_path: Path) -> List[str]:
    """
    Get all issue markdown files for a repository.
    
    Args:
        repo_name (str): Repository name (e.g., 'google_guava')
        base_path (Path): Base path to the bucket_harvest directory
        
    Returns:
        List[str]: Sorted list of issue file paths
    """
    # Convert repo_name format: google_guava -> .guava
    if '_' in repo_name:
        org, repo = repo_name.split('_', 1)
        issue_dir = f".{repo}"
    else:
        issue_dir = f".{repo_name}"
    
    data_path = base_path / "data" / repo_name / issue_dir
    
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

def filter_excluded_issues(issue_files: List[str], exclusions: List[str]) -> Tuple[List[str], int]:
    """
    Remove excluded issues from the list.
    
    Args:
        issue_files (List[str]): List of issue file paths
        exclusions (List[str]): List of issue IDs to exclude
        
    Returns:
        Tuple[List[str], int]: (filtered_files, excluded_count)
    """
    if not exclusions:
        return issue_files, 0
    
    filtered = []
    excluded_count = 0
    
    for file_path in issue_files:
        issue_id = os.path.basename(file_path).replace('.md', '')
        if issue_id not in exclusions:
            filtered.append(file_path)
        else:
            excluded_count += 1
    
    return filtered, excluded_count

def create_issue_batches(issue_files: List[str], batch_size: int = 10) -> List[List[str]]:
    """
    Split issue files into batches for parallel processing.
    
    Args:
        issue_files (List[str]): List of issue file paths
        batch_size (int): Number of issues per batch (default: 10)
        
    Returns:
        List[List[str]]: List of batches, each containing file paths
    """
    batches = []
    for i in range(0, len(issue_files), batch_size):
        batch = issue_files[i:i + batch_size]
        batches.append(batch)
    return batches

def read_issue_content(file_path: str) -> str:
    """
    Read and return the content of an issue file.
    
    Args:
        file_path (str): Path to the issue markdown file
        
    Returns:
        str: Content of the issue file
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading issue file {file_path}: {e}"

def extract_issue_metadata(issue_content: str) -> Dict[str, str]:
    """
    Extract basic metadata from an issue markdown file.
    
    Args:
        issue_content (str): Content of the issue markdown file
        
    Returns:
        Dict[str, str]: Dictionary with issue metadata
    """
    metadata = {
        'title': '',
        'url': '',
        'created': '',
        'author': '', 
        'state': '',
        'labels': ''
    }
    
    lines = issue_content.split('\n')
    
    # Extract title (first line that starts with #)
    for line in lines:
        if line.startswith('# Issue #'):
            metadata['title'] = line.replace('# Issue #', '').strip()
            break
    
    # Extract other metadata
    for line in lines:
        if line.startswith('**GitHub URL:**'):
            metadata['url'] = line.replace('**GitHub URL:**', '').strip()
        elif line.startswith('**Created:**'):
            metadata['created'] = line.replace('**Created:**', '').strip()
        elif line.startswith('**Author:**'):
            metadata['author'] = line.replace('**Author:**', '').strip()
        elif line.startswith('**State:**'):
            metadata['state'] = line.replace('**State:**', '').strip()
        elif line.startswith('**Labels:**'):
            metadata['labels'] = line.replace('**Labels:**', '').strip()
    
    return metadata

def get_issue_id_from_path(file_path: str) -> str:
    """
    Extract issue ID from file path.
    
    Args:
        file_path (str): Path to issue file
        
    Returns:
        str: Issue ID
    """
    return os.path.basename(file_path).replace('.md', '')

def validate_batch_structure(batches: List[List[str]]) -> Dict[str, any]:
    """
    Validate the structure of issue batches.
    
    Args:
        batches (List[List[str]]): List of batches
        
    Returns:
        Dict[str, any]: Validation results
    """
    total_issues = sum(len(batch) for batch in batches)
    max_batch_size = max(len(batch) for batch in batches) if batches else 0
    min_batch_size = min(len(batch) for batch in batches) if batches else 0
    
    return {
        'total_batches': len(batches),
        'total_issues': total_issues,
        'max_batch_size': max_batch_size,
        'min_batch_size': min_batch_size,
        'is_valid': len(batches) > 0 and total_issues > 0,
        'batch_sizes': [len(batch) for batch in batches]
    }

def create_exclusions_template(project_root: Path) -> str:
    """
    Create a template exclusions file if it doesn't exist.
    
    Args:
        project_root (Path): Project root directory
        
    Returns:
        str: Path to exclusions file
    """
    exclusions_path = project_root / "user" / "exclusions.txt"
    
    if not exclusions_path.exists():
        # Ensure user directory exists
        exclusions_path.parent.mkdir(exist_ok=True)
        
        # Create template file
        template_content = """# GitHub Issue Exclusions
# Add issue IDs (one per line) that you want to exclude from analysis
# Example:
# 1234
# 5678
# 9012

"""
        with open(exclusions_path, 'w', encoding='utf-8') as f:
            f.write(template_content)
    
    return str(exclusions_path)

def format_batch_summary(batches: List[List[str]], exclusions: List[str]) -> str:
    """
    Create a formatted summary of batch processing setup.
    
    Args:
        batches (List[List[str]]): List of batches
        exclusions (List[str]): List of excluded issue IDs
        
    Returns:
        str: Formatted summary string
    """
    validation = validate_batch_structure(batches)
    
    summary = f"""📊 Batch Processing Summary:
   • Total batches: {validation['total_batches']}
   • Total issues: {validation['total_issues']}
   • Batch sizes: {validation['batch_sizes']}
   • Excluded issues: {len(exclusions)}
   • Ready for parallel processing: {'✅' if validation['is_valid'] else '❌'}
"""
    
    if exclusions:
        summary += f"   • Excluded IDs: {', '.join(exclusions[:10])}{'...' if len(exclusions) > 10 else ''}\n"
    
    return summary

def save_batch_metadata(batches: List[List[str]], output_path: Path, repo_name: str) -> str:
    """
    Save batch metadata for debugging and tracking.
    
    Args:
        batches (List[List[str]]): List of batches
        output_path (Path): Directory to save metadata
        repo_name (str): Repository name
        
    Returns:
        str: Path to saved metadata file
    """
    metadata = {
        'repo_name': repo_name,
        'total_batches': len(batches),
        'total_issues': sum(len(batch) for batch in batches),
        'batch_details': []
    }
    
    for i, batch in enumerate(batches, 1):
        batch_info = {
            'batch_number': i,
            'issue_count': len(batch),
            'issue_ids': [get_issue_id_from_path(path) for path in batch]
        }
        metadata['batch_details'].append(batch_info)
    
    metadata_path = output_path / f"batch_metadata_{repo_name}.json"
    
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    return str(metadata_path)