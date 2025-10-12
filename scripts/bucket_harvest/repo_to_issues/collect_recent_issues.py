#!/usr/bin/env python3
"""
GitHub Recent Issues Collector (Simplified Approach)
Collects the 100 most recent GitHub issues from a repository using parallel processing.

This simplified script replaces the bucket strategy with direct parallel processing:
- Fetches 100 most recent open issues using GitHub CLI
- Processes them in parallel using ThreadPoolExecutor 
- Creates individual markdown files with comprehensive issue details
- Same output format and directory structure as bucket approach

Usage:
    python collect_recent_issues.py <owner/repo>
    
Example:
    python collect_recent_issues.py facebook/react
"""

import os
import sys
import json
import subprocess
import time
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Thread-local storage for progress tracking
thread_local = threading.local()

def parse_rate_limit_error(error_output: str) -> Optional[datetime]:
    """Parse rate limit error to extract reset time."""
    timestamp_match = re.search(r'timestamp (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC', error_output)
    if timestamp_match:
        timestamp_str = timestamp_match.group(1)
        try:
            error_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            reset_time = error_time + timedelta(hours=1)
            return reset_time
        except ValueError:
            pass
    return None

def fetch_open_issues(repo_full_name: str, max_issues: int = 100) -> List[Dict[str, Any]]:
    """Fetch open issues from repository using GitHub CLI."""
    print(f"Fetching open issues from {repo_full_name}...")
    print(f"Target: {max_issues} issues (100 most recent open issues)")
    
    issues = []
    page = 1
    per_page = 50
    
    while len(issues) < max_issues:
        print(f"  Fetching page {page} ({per_page} issues per page)...")
        
        try:
            # Get raw API response without JQ filtering to track actual API count
            cmd = [
                'gh', 'api', 
                f'/repos/{repo_full_name}/issues',
                '--method', 'GET',
                '-F', 'state=open',
                '-F', f'per_page={per_page}',
                '-F', f'page={page}',
                '-F', 'sort=created',
                '-F', 'direction=desc'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
            
            if not result.stdout or not result.stdout.strip():
                print(f"    No more data from API (page {page} was empty)")
                break
            
            # Parse raw response and filter for issues only
            try:
                raw_data = json.loads(result.stdout)
                raw_count = len(raw_data)  # Total items returned by API (issues + PRs)
                
                # Filter to issues only (exclude PRs)
                page_issues = []
                for item in raw_data:
                    if item.get('pull_request') is None:  # This is an issue, not a PR
                        page_issues.append({
                            'number': item.get('number'),
                            'created_at': item.get('created_at')
                        })
                
                issues.extend(page_issues)
                print(f"    OK Fetched {len(page_issues)} issues from {raw_count} API items (total: {len(issues)})")
                
                # Check if we've reached the end based on raw API response count
                if raw_count < per_page:
                    print(f"    Reached end of API data (got {raw_count} < {per_page})")
                    break
                
            except json.JSONDecodeError as e:
                print(f"    Error parsing API response: {e}")
                break
            
            page += 1
            
            if page <= 3:
                print(f"    Waiting 2 seconds before next page...")
                time.sleep(2)
            
        except subprocess.CalledProcessError as e:
            error_output = e.stderr or e.stdout or str(e)
            print(f"    GitHub CLI error on page {page}: {error_output}")
            
            # If we already have some issues, return them instead of failing completely
            if issues:
                print(f"    Returning {len(issues)} issues collected so far due to error")
                break
            
            if "rate limit exceeded" in error_output.lower():
                reset_time = parse_rate_limit_error(error_output)
                
                if reset_time:
                    now = datetime.utcnow()
                    wait_seconds = max((reset_time - now).total_seconds(), 60)
                    wait_minutes = wait_seconds / 60
                    
                    print(f"    ⏰ Rate limit hit. Reset time: {reset_time.strftime('%H:%M:%S')} UTC")
                    print(f"    💤 Need to wait ~{wait_minutes:.1f} minutes")
                else:
                    print(f"    ⏰ Rate limit hit. Waiting 60 minutes as fallback...")
                    wait_seconds = 3600
                
                if issues:
                    print(f"    📊 Returning {len(issues)} issues collected so far")
                    return issues
                else:
                    raise
            else:
                print(f"    ERROR on page {page}: {error_output}")
                raise
    
    print(f"Successfully fetched {len(issues)} open issues")
    return issues

def filter_recent_issues(issues: List[Dict[str, Any]], limit: int = 100) -> List[Dict[str, Any]]:
    """Filter to most recent issues by creation date."""
    print(f"Filtering to {limit} most recent issues...")
    
    sorted_issues = sorted(issues, key=lambda x: x['created_at'], reverse=True)
    recent_issues = sorted_issues[:limit]
    
    print(f"Selected {len(recent_issues)} most recent issues")
    if recent_issues:
        oldest_date = recent_issues[-1]['created_at'][:10]
        newest_date = recent_issues[0]['created_at'][:10]
        print(f"Date range: {oldest_date} to {newest_date}")
    
    return recent_issues

def process_single_issue(repo_name: str, issue_data: Dict[str, Any], output_dir: str, progress_lock: threading.Lock) -> Dict[str, Any]:
    """Process a single issue and create its markdown file."""
    issue_id = issue_data['number']
    
    try:
        # Fetch issue details using GitHub CLI
        cmd = ['gh', 'api', f'repos/{repo_name}/issues/{issue_id}']
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        issue_json = json.loads(result.stdout)
        
        # Extract metadata
        title = issue_json.get('title', 'No Title')
        url = issue_json.get('html_url', f'https://github.com/{repo_name}/issues/{issue_id}')
        created_at = issue_json.get('created_at', '')[:10]
        labels = '; '.join([label['name'] for label in issue_json.get('labels', [])])
        author = issue_json.get('user', {}).get('login', 'Unknown')
        state = issue_json.get('state', 'unknown')
        body = issue_json.get('body') or ''
        
        # Create markdown file
        issue_file = os.path.join(output_dir, f"{issue_id}.md")
        
        with open(issue_file, 'w', encoding='utf-8') as f:
            f.write(f"# Issue #{issue_id}: {title}\n\n")
            f.write(f"**GitHub URL:** {url}  \n")
            f.write(f"**Created:** {created_at}  \n")
            f.write(f"**Author:** {author}  \n")
            f.write(f"**State:** {state}  \n")
            f.write(f"**Labels:** {labels}  \n\n")
            f.write("---\n\n")
            f.write("## Issue Description\n\n")
            f.write(f"{body}\n\n")
            f.write("---\n\n")
            f.write("## Comments\n\n")
            
            # Fetch comments
            try:
                comments_cmd = ['gh', 'api', f'repos/{repo_name}/issues/{issue_id}/comments', '--paginate']
                comments_result = subprocess.run(comments_cmd, capture_output=True, text=True, check=True)
                
                if comments_result.stdout.strip():
                    comments = json.loads(comments_result.stdout)
                    if comments:
                        for comment in comments:
                            comment_author = comment.get('user', {}).get('login', 'Unknown')
                            comment_date = comment.get('created_at', '')[:10]
                            comment_body = comment.get('body', '')
                            f.write(f"### Comment by **{comment_author}** on {comment_date}\n\n")
                            f.write(f"{comment_body}\n\n")
                    else:
                        f.write("*No comments*\n")
                else:
                    f.write("*No comments*\n")
            except:
                f.write("*Failed to fetch comments*\n")
        
        with progress_lock:
            return {"status": "success", "issue_id": issue_id, "file": issue_file}
            
    except Exception as e:
        # Create placeholder file for failed issues
        issue_file = os.path.join(output_dir, f"{issue_id}.md")
        
        with open(issue_file, 'w', encoding='utf-8') as f:
            f.write(f"# Issue #{issue_id}: [FAILED TO FETCH]\n\n")
            f.write(f"**GitHub URL:** https://github.com/{repo_name}/issues/{issue_id}  \n")
            f.write(f"**Status:** Failed to fetch issue details  \n\n")
            f.write("---\n\n")
            f.write("## Error\n\n")
            f.write(f"Could not retrieve issue data: {str(e)}\n")
        
        with progress_lock:
            return {"status": "failed", "issue_id": issue_id, "error": str(e)}

def process_issues_parallel(repo_name: str, issues: List[Dict[str, Any]], output_dir: str, max_workers: int = 10) -> Dict[str, int]:
    """Process issues in parallel using ThreadPoolExecutor."""
    print(f"Processing {len(issues)} issues in parallel ({max_workers} threads)")
    print(f"Output directory: {output_dir}")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Progress tracking
    progress_lock = threading.Lock()
    processed = 0
    failed = 0
    total = len(issues)
    
    # Process issues in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_issue = {
            executor.submit(process_single_issue, repo_name, issue, output_dir, progress_lock): issue 
            for issue in issues
        }
        
        # Process completed tasks
        for future in as_completed(future_to_issue):
            result = future.result()
            
            if result["status"] == "success":
                processed += 1
                print(f"  SUCCESS Issue #{result['issue_id']} ({processed + failed}/{total})")
            else:
                failed += 1
                print(f"  FAILED Issue #{result['issue_id']} failed: {result.get('error', 'Unknown error')} ({processed + failed}/{total})")
            
            # Small delay to avoid overwhelming the API
            time.sleep(0.1)
    
    print(f"\nProcessing completed:")
    print(f"   Processed: {processed} issues")
    print(f"   Failed: {failed} issues")
    print(f"   Output: {output_dir}/")
    
    return {"processed": processed, "failed": failed}

def create_summary_report(repo_name: str, results: Dict[str, int], output_dir: str) -> str:
    """Create a summary report of the collection process."""
    summary_path = os.path.join(output_dir, 'collection_summary.txt')
    
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(f"GitHub Recent Issues Collection Summary\n")
        f.write(f"=====================================\n\n")
        f.write(f"Repository: {repo_name}\n")
        f.write(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Strategy: 100 most recent open issues (parallel processing)\n")
        f.write(f"Total processed: {results['processed']}\n")
        f.write(f"Total failed: {results['failed']}\n")
        f.write(f"Success rate: {results['processed']/(results['processed']+results['failed'])*100:.1f}%\n\n")
        
        f.write(f"Output:\n")
        f.write(f"- Directory: {os.path.basename(output_dir)}/\n")
        f.write(f"- Files: {results['processed']} individual .md files\n")
        f.write(f"- Format: issue_id.md (e.g., 1234.md, 5678.md)\n\n")
        
        f.write(f"Usage:\n")
        f.write(f"- Individual files contain full issue details including comments\n")
        f.write(f"- Perfect for LLM analysis due to structured markdown format\n")
    
    print(f"Summary report saved: {os.path.basename(summary_path)}")
    return summary_path

def main():
    """Main entry point for the script."""
    if len(sys.argv) != 2:
        print("Usage: python collect_recent_issues.py <owner/repo>")
        print("Example: python collect_recent_issues.py facebook/react")
        sys.exit(1)
    
    repo_full_name = sys.argv[1]
    
    # Validate repository format
    if '/' not in repo_full_name:
        print("❌ Repository must be in format 'owner/repo'")
        sys.exit(1)
    
    try:
        print(f"Collecting recent issues from {repo_full_name}")
        print(f"Strategy: 100 most recent open issues with parallel processing")
        print()
        
        # Phase 1: Fetch issues
        all_issues = fetch_open_issues(repo_full_name, max_issues=100)
        
        if not all_issues:
            print("No open issues found in repository.")
            return
        
        # Phase 2: Filter to most recent 100
        recent_issues = filter_recent_issues(all_issues, limit=100)
        
        # Phase 3: Set up output directory
        repo_short_name = repo_full_name.split('/')[1]
        base_dir = os.path.join('scripts', 'bucket_harvest', 'repo_to_issues', 'data', repo_full_name.replace('/', '_'))
        output_dir = os.path.join(base_dir, f'.{repo_short_name}')
        
        # Phase 4: Process issues in parallel
        results = process_issues_parallel(repo_full_name, recent_issues, output_dir)
        
        # Phase 5: Create summary report
        summary_path = create_summary_report(repo_full_name, results, base_dir)
        
        print()
        print(f"Collection completed successfully!")
        print(f"Output directory: {output_dir}")
        print(f"Markdown files: {results['processed']} issues")
        print(f"Summary: {os.path.basename(summary_path)}")
        
    except subprocess.CalledProcessError as e:
        error_output = e.stderr or e.stdout or str(e)
        if "rate limit exceeded" in error_output.lower():
            print()
            print("GitHub API Rate Limit Exceeded")
            print("=" * 40)
            reset_time = parse_rate_limit_error(error_output)
            if reset_time:
                now = datetime.utcnow()
                wait_minutes = max((reset_time - now).total_seconds() / 60, 1)
                print(f"Rate limit resets at: {reset_time.strftime('%H:%M:%S')} UTC")
                print(f"Wait approximately: {wait_minutes:.0f} minutes")
            else:
                print(f"Wait approximately: 60 minutes")
            print()
            print("Alternative options:")
            print("1. Wait for rate limit reset and try again")
            print("2. Try a smaller repository with fewer issues")
            print("3. Check your GitHub authentication:")
            print("   gh auth status")
            print("   gh auth refresh")
        else:
            print(f"Error during collection: {str(e)}")
        sys.exit(1)
        
    except FileNotFoundError:
        print("Error: GitHub CLI (gh) not found. Please install GitHub CLI first.")
        print("Visit: https://cli.github.com/")
        sys.exit(1)
        
    except Exception as e:
        print(f"Error during collection: {str(e)}")
        raise

if __name__ == "__main__":
    main()