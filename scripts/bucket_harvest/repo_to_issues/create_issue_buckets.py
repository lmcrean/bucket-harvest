#!/usr/bin/env python3
"""
GitHub Issues Bucket Creator (Refined Strategy)
Creates bucket CSV for 100 most recent open issues from a target repository.

This script implements Phase 1 of the refined bucket strategy:
- Fetches all open issues with creation dates using GitHub CLI
- Filters to 100 most recent issues by date_created
- Generates issue_buckets.csv with format: issue_id; bucket_id; date_created
- Distributes issues across 10 buckets for parallel processing

Usage:
    python create_issue_buckets.py <owner/repo>
    
Example:
    python create_issue_buckets.py facebook/react
"""

import os
import sys
import csv
import json
import subprocess
import time
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

def parse_rate_limit_error(error_output: str) -> Optional[datetime]:
    """
    Parse rate limit error to extract reset time.
    
    Args:
        error_output: Error message from GitHub CLI
        
    Returns:
        Reset time as datetime object, or None if not parseable
    """
    # Try to extract timestamp from error message
    timestamp_match = re.search(r'timestamp (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC', error_output)
    if timestamp_match:
        timestamp_str = timestamp_match.group(1)
        try:
            # Parse the timestamp and add 1 hour for rate limit reset
            error_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            reset_time = error_time + timedelta(hours=1)
            return reset_time
        except ValueError:
            pass
    
    return None

def fetch_open_issues_batch(repo_full_name: str, max_issues: int = 150) -> List[Dict[str, Any]]:
    """
    Fetch open issues from repository using batched approach to avoid rate limits.
    
    Args:
        repo_full_name: Repository in format 'owner/repo'
        max_issues: Maximum number of issues to fetch
        
    Returns:
        List of issue dictionaries with number and created_at
    """
    print(f"Fetching open issues from {repo_full_name} (batch approach)...")
    print(f"Target: {max_issues} issues (fetching extra to ensure we have enough recent ones)")
    
    issues = []
    page = 1
    per_page = 50  # Smaller batches to reduce API impact
    
    while len(issues) < max_issues:
        print(f"  Fetching page {page} ({per_page} issues per page)...")
        
        try:
            # Use GitHub CLI to fetch one page of issues
            cmd = [
                'gh', 'api', 
                f'/repos/{repo_full_name}/issues',
                '-f', 'state=open',
                '-f', f'per_page={per_page}',
                '-f', f'page={page}',
                '-f', 'sort=created',
                '-f', 'direction=desc',
                '-q', '.[] | select(.pull_request == null) | {number: .number, created_at: .created_at}'
            ]
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                check=True
            )
            
            # Parse JSON lines output
            page_issues = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    try:
                        issue_data = json.loads(line)
                        page_issues.append(issue_data)
                    except json.JSONDecodeError as e:
                        print(f"    Warning: Could not parse JSON line: {line[:50]}... Error: {e}")
                        continue
            
            if not page_issues:
                print(f"    No more issues found (page {page} was empty)")
                break
            
            issues.extend(page_issues)
            print(f"    ✅ Fetched {len(page_issues)} issues (total: {len(issues)})")
            
            # If we got fewer than per_page, we've reached the end
            if len(page_issues) < per_page:
                print(f"    Reached end of issues (got {len(page_issues)} < {per_page})")
                break
            
            page += 1
            
            # Add delay between pages to respect rate limits
            if page <= 3:  # Be more aggressive with delays for first few pages
                print(f"    Waiting 2 seconds before next page...")
                time.sleep(2)
            
        except subprocess.CalledProcessError as e:
            error_output = e.stderr or e.stdout or str(e)
            
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
                
                print(f"    You can:")
                print(f"    1. Wait {wait_seconds/60:.0f} minutes and run the script again")
                print(f"    2. Try with a smaller repository that has fewer issues")
                print(f"    3. Use the existing {len(issues)} issues if that's enough")
                
                # For now, return what we have
                if issues:
                    print(f"    📊 Returning {len(issues)} issues collected so far")
                    return issues
                else:
                    raise
            else:
                print(f"    ❌ Error on page {page}: {error_output}")
                raise
    
    print(f"✅ Successfully fetched {len(issues)} open issues")
    return issues

def fetch_open_issues(repo_full_name: str) -> List[Dict[str, Any]]:
    """
    Fetch open issues with automatic fallback to batch mode.
    
    Args:
        repo_full_name: Repository in format 'owner/repo'
        
    Returns:
        List of issue dictionaries with number and created_at
    """
    try:
        # Try batch approach directly (more reliable)
        return fetch_open_issues_batch(repo_full_name)
        
    except subprocess.CalledProcessError as e:
        print(f"Error running GitHub CLI: {e}")
        if e.stderr:
            print(f"stderr: {e.stderr}")
        if e.stdout:
            print(f"stdout: {e.stdout}")
        raise
    except FileNotFoundError:
        print("Error: GitHub CLI (gh) not found. Please install GitHub CLI first.")
        print("Visit: https://cli.github.com/")
        sys.exit(1)

def filter_recent_issues(issues: List[Dict[str, Any]], limit: int = 100) -> List[Dict[str, Any]]:
    """
    Filter to most recent issues by creation date.
    
    Args:
        issues: List of issue dictionaries
        limit: Maximum number of issues to return
        
    Returns:
        List of most recent issues
    """
    print(f"Filtering to {limit} most recent issues...")
    
    # Sort by created_at in descending order (most recent first)
    sorted_issues = sorted(
        issues, 
        key=lambda x: x['created_at'], 
        reverse=True
    )
    
    # Take the most recent N issues
    recent_issues = sorted_issues[:limit]
    
    print(f"Selected {len(recent_issues)} most recent issues")
    if recent_issues:
        oldest_date = recent_issues[-1]['created_at'][:10]
        newest_date = recent_issues[0]['created_at'][:10]
        print(f"Date range: {oldest_date} to {newest_date}")
    
    return recent_issues

def distribute_into_buckets(issues: List[Dict[str, Any]], bucket_count: int = 10) -> List[Dict[str, Any]]:
    """
    Distribute issues into buckets for parallel processing.
    
    Args:
        issues: List of issue dictionaries
        bucket_count: Number of buckets to create
        
    Returns:
        List of issue dictionaries with bucket_id assigned
    """
    print(f"Distributing {len(issues)} issues into {bucket_count} buckets...")
    
    bucketed_issues = []
    
    for i, issue in enumerate(issues):
        # Assign bucket ID (1-based indexing)
        bucket_id = (i % bucket_count) + 1
        
        bucketed_issues.append({
            'issue_id': issue['number'],
            'bucket_id': bucket_id,
            'date_created': issue['created_at'][:10]  # Extract date part only
        })
    
    # Print bucket distribution
    bucket_counts = {}
    for issue in bucketed_issues:
        bucket_id = issue['bucket_id']
        bucket_counts[bucket_id] = bucket_counts.get(bucket_id, 0) + 1
    
    print("Bucket distribution:")
    for bucket_id in sorted(bucket_counts.keys()):
        count = bucket_counts[bucket_id]
        print(f"  Bucket {bucket_id}: {count} issues")
    
    return bucketed_issues

def create_bucket_csv(bucketed_issues: List[Dict[str, Any]], repo_name: str) -> str:
    """
    Create the issue_buckets.csv file.
    
    Args:
        bucketed_issues: List of issues with bucket assignments
        repo_name: Repository name for output directory
        
    Returns:
        Path to the created CSV file
    """
    # Create output directory
    repo_dir = repo_name.replace('/', '_')
    output_dir = os.path.join('scripts', 'bucket_harvest', 'repo_to_issues', 'data', repo_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    # Create CSV file
    csv_filename = 'issue_buckets.csv'
    csv_path = os.path.join(output_dir, csv_filename)
    
    print(f"Creating bucket CSV: {csv_path}")
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        
        # Write header
        writer.writerow(['issue_id', 'bucket_id', 'date_created'])
        
        # Write issue data
        for issue in bucketed_issues:
            writer.writerow([
                issue['issue_id'],
                issue['bucket_id'],
                issue['date_created']
            ])
    
    print(f"✅ Created {csv_filename} with {len(bucketed_issues)} issues")
    return csv_path

def create_summary_report(repo_name: str, bucketed_issues: List[Dict[str, Any]], csv_path: str) -> str:
    """
    Create a summary report of the bucket creation process.
    
    Args:
        repo_name: Repository name
        bucketed_issues: List of bucketed issues
        csv_path: Path to created CSV file
        
    Returns:
        Path to summary report
    """
    repo_dir = repo_name.replace('/', '_')
    output_dir = os.path.join('scripts', 'bucket_harvest', 'repo_to_issues', 'data', repo_dir)
    summary_path = os.path.join(output_dir, 'bucket_creation_summary.txt')
    
    # Calculate bucket statistics
    bucket_counts = {}
    for issue in bucketed_issues:
        bucket_id = issue['bucket_id']
        bucket_counts[bucket_id] = bucket_counts.get(bucket_id, 0) + 1
    
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(f"GitHub Issues Bucket Creation Summary\n")
        f.write(f"====================================\n\n")
        f.write(f"Repository: {repo_name}\n")
        f.write(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Strategy: 100 most recent open issues\n")
        f.write(f"Total issues: {len(bucketed_issues)}\n")
        f.write(f"Bucket count: {len(bucket_counts)}\n\n")
        
        if bucketed_issues:
            oldest_date = min(issue['date_created'] for issue in bucketed_issues)
            newest_date = max(issue['date_created'] for issue in bucketed_issues)
            f.write(f"Date range: {oldest_date} to {newest_date}\n\n")
        
        f.write(f"Bucket Distribution:\n")
        for bucket_id in sorted(bucket_counts.keys()):
            count = bucket_counts[bucket_id]
            f.write(f"  Bucket {bucket_id}: {count} issues\n")
        
        f.write(f"\nFiles Created:\n")
        f.write(f"  - {os.path.basename(csv_path)}\n")
        f.write(f"  - {os.path.basename(summary_path)}\n")
        
        f.write(f"\nNext Steps:\n")
        f.write(f"1. Run generate_bucket_scripts.py to create processing scripts\n")
        f.write(f"2. Execute the generated bash scripts in parallel terminals\n")
        f.write(f"3. Find individual issue markdown files in .{repo_name.split('/')[1]}/ directory\n")
    
    print(f"📋 Summary report saved: {summary_path}")
    return summary_path

def main():
    """Main entry point for the script."""
    if len(sys.argv) != 2:
        print("Usage: python create_issue_buckets.py <owner/repo>")
        print("Example: python create_issue_buckets.py facebook/react")
        sys.exit(1)
    
    repo_full_name = sys.argv[1]
    
    # Validate repository format
    if '/' not in repo_full_name:
        print("❌ Repository must be in format 'owner/repo'")
        sys.exit(1)
    
    try:
        print(f"🎯 Creating issue buckets for {repo_full_name}")
        print(f"Strategy: 100 most recent open issues distributed across 10 buckets")
        print()
        
        # Phase 1: Fetch all open issues
        all_issues = fetch_open_issues(repo_full_name)
        
        if not all_issues:
            print("No open issues found in repository.")
            return
        
        # Phase 2: Filter to most recent 100
        recent_issues = filter_recent_issues(all_issues, limit=100)
        
        # Phase 3: Distribute into buckets
        bucketed_issues = distribute_into_buckets(recent_issues, bucket_count=10)
        
        # Phase 4: Create CSV file
        csv_path = create_bucket_csv(bucketed_issues, repo_full_name)
        
        # Phase 5: Create summary report
        summary_path = create_summary_report(repo_full_name, bucketed_issues, csv_path)
        
        print()
        print(f"🎉 Bucket creation completed successfully!")
        print(f"📁 Output directory: {os.path.dirname(csv_path)}")
        print(f"📊 CSV file: {os.path.basename(csv_path)}")
        print(f"📋 Summary: {os.path.basename(summary_path)}")
        print()
        print(f"🚀 Next step: Run generate_bucket_scripts.py {repo_full_name}")
        
    except subprocess.CalledProcessError as e:
        error_output = e.stderr or e.stdout or str(e)
        if "rate limit exceeded" in error_output.lower():
            print()
            print("🛑 GitHub API Rate Limit Exceeded")
            print("=" * 40)
            reset_time = parse_rate_limit_error(error_output)
            if reset_time:
                now = datetime.utcnow()
                wait_minutes = max((reset_time - now).total_seconds() / 60, 1)
                print(f"⏰ Rate limit resets at: {reset_time.strftime('%H:%M:%S')} UTC")
                print(f"💤 Wait approximately: {wait_minutes:.0f} minutes")
            else:
                print(f"💤 Wait approximately: 60 minutes")
            print()
            print("📋 Alternative options:")
            print("1. Wait for rate limit reset and try again")
            print("2. Try a smaller repository with fewer issues:")
            print("   python create_issue_buckets.py vuejs/vue-router")
            print("   python create_issue_buckets.py facebook/create-react-app")
            print("3. Check your GitHub authentication:")
            print("   gh auth status")
            print("   gh auth refresh")
        else:
            print(f"❌ Error during bucket creation: {str(e)}")
        sys.exit(1)
        
    except Exception as e:
        print(f"❌ Error during bucket creation: {str(e)}")
        raise

if __name__ == "__main__":
    main()