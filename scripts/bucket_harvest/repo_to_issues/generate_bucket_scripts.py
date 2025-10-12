#!/usr/bin/env python3
"""
GitHub Issues Bash Script Generator (Refined Strategy)
Generates parallel bash scripts for processing issue buckets.

This script implements Phase 2 of the refined bucket strategy:
- Reads issue_buckets.csv created by create_issue_buckets.py
- Generates individual process_bucket_N.sh scripts for each bucket
- Each script processes its assigned issue IDs using GitHub CLI
- Creates .{repo}/ directory structure for markdown output

Usage:
    python generate_bucket_scripts.py <owner/repo>
    
Example:
    python generate_bucket_scripts.py facebook/react
"""

import os
import sys
import csv
from typing import List, Dict, Any

def load_bucket_csv(repo_name: str) -> List[Dict[str, Any]]:
    """
    Load the issue buckets CSV file.
    
    Args:
        repo_name: Repository name in format 'owner/repo'
        
    Returns:
        List of issue dictionaries with bucket assignments
    """
    repo_dir = repo_name.replace('/', '_')
    data_dir = os.path.join('scripts', 'bucket_harvest', 'repo_to_issues', 'data', repo_dir)
    csv_path = os.path.join(data_dir, 'issue_buckets.csv')
    
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Bucket CSV not found: {csv_path}")
    
    print(f"Loading bucket data from: {csv_path}")
    
    issues = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            issues.append({
                'issue_id': int(row['issue_id']),
                'bucket_id': int(row['bucket_id']),
                'date_created': row['date_created']
            })
    
    print(f"Loaded {len(issues)} issues from bucket CSV")
    return issues

def group_issues_by_bucket(issues: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    """
    Group issues by bucket ID.
    
    Args:
        issues: List of issue dictionaries
        
    Returns:
        Dictionary mapping bucket_id to list of issues
    """
    buckets = {}
    
    for issue in issues:
        bucket_id = issue['bucket_id']
        if bucket_id not in buckets:
            buckets[bucket_id] = []
        buckets[bucket_id].append(issue)
    
    print(f"Grouped issues into {len(buckets)} buckets:")
    for bucket_id in sorted(buckets.keys()):
        count = len(buckets[bucket_id])
        print(f"  Bucket {bucket_id}: {count} issues")
    
    return buckets

def create_bash_script(bucket_id: int, bucket_issues: List[Dict[str, Any]], repo_name: str, output_dir: str) -> str:
    """
    Create a bash script for processing a specific bucket.
    
    Args:
        bucket_id: Bucket identifier
        bucket_issues: List of issues in this bucket
        repo_name: Repository name in format 'owner/repo'
        output_dir: Directory to save the script
        
    Returns:
        Path to the created bash script
    """
    repo_short_name = repo_name.split('/')[1]  # Extract repo name from owner/repo
    script_filename = f"process_bucket_{bucket_id}.sh"
    script_path = os.path.join(output_dir, script_filename)
    
    # Create issue ID list for the script
    issue_ids = [str(issue['issue_id']) for issue in bucket_issues]
    issue_list = ' '.join(issue_ids)
    
    script_content = f'''#!/bin/bash
# GitHub Issues Bucket Processor - Bucket {bucket_id}
# Generated for repository: {repo_name}
# Processing {len(bucket_issues)} issues

REPO="{repo_name}"
BUCKET_ID={bucket_id}
OUTPUT_DIR=".{repo_short_name}"
ISSUES=({issue_list})

echo "🚀 Starting bucket $BUCKET_ID processing for $REPO"
echo "📁 Output directory: $OUTPUT_DIR"
echo "📊 Processing ${{#ISSUES[@]}} issues"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Initialize counters
PROCESSED=0
FAILED=0
TOTAL=${{#ISSUES[@]}}

# Process each issue in this bucket
for ISSUE_ID in "${{ISSUES[@]}}"; do
    echo "  Processing issue #$ISSUE_ID ($((PROCESSED + FAILED + 1))/$TOTAL)"
    
    # Fetch issue details using GitHub CLI
    ISSUE_FILE="$OUTPUT_DIR/$ISSUE_ID.md"
    
    # Get issue data as JSON
    ISSUE_JSON=$(gh api repos/$REPO/issues/$ISSUE_ID 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        # Extract metadata
        TITLE=$(echo "$ISSUE_JSON" | jq -r '.title')
        URL=$(echo "$ISSUE_JSON" | jq -r '.html_url')
        CREATED_AT=$(echo "$ISSUE_JSON" | jq -r '.created_at[:10]')
        LABELS=$(echo "$ISSUE_JSON" | jq -r '.labels[]?.name' | tr '\\n' '; ' | sed 's/; $//')
        AUTHOR=$(echo "$ISSUE_JSON" | jq -r '.user.login')
        STATE=$(echo "$ISSUE_JSON" | jq -r '.state')
        BODY=$(echo "$ISSUE_JSON" | jq -r '.body // ""')
        
        # Start writing the markdown file
        cat > "$ISSUE_FILE" << EOF
# Issue #$ISSUE_ID: $TITLE

**GitHub URL:** $URL  
**Created:** $CREATED_AT  
**Author:** $AUTHOR  
**State:** $STATE  
**Labels:** $LABELS  

---

## Issue Description

$BODY

---

## Comments
EOF
        
        # Fetch and append comments
        COMMENTS_JSON=$(gh api repos/$REPO/issues/$ISSUE_ID/comments --paginate 2>/dev/null)
        
        if [ $? -eq 0 ]; then
            echo "$COMMENTS_JSON" | jq -r '.[] | "### Comment by **\\(.user.login)** on \\(.created_at[:10])\\n\\n\\(.body)\\n"' >> "$ISSUE_FILE"
        else
            echo "*No comments or failed to fetch comments*" >> "$ISSUE_FILE"
        fi
        
        PROCESSED=$((PROCESSED + 1))
        echo "    ✅ Created $ISSUE_FILE"
    else
        echo "    ❌ Failed to fetch issue #$ISSUE_ID"
        FAILED=$((FAILED + 1))
        
        # Create placeholder file for failed issues
        cat > "$ISSUE_FILE" << EOF
# Issue #$ISSUE_ID: [FAILED TO FETCH]

**GitHub URL:** https://github.com/$REPO/issues/$ISSUE_ID  
**Status:** Failed to fetch issue details  

---

## Error

Could not retrieve issue data via GitHub CLI.
EOF
    fi
    
    # Small delay to respect rate limits
    sleep 0.2
done

echo ""
echo "🏁 Bucket $BUCKET_ID completed:"
echo "   ✅ Processed: $PROCESSED issues"
echo "   ❌ Failed: $FAILED issues"
echo "   📁 Output: $OUTPUT_DIR/"
echo ""
'''
    
    # Write the script file
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    # Make script executable
    os.chmod(script_path, 0o755)
    
    print(f"  ✅ Created {script_filename} ({len(bucket_issues)} issues)")
    return script_path

def create_parallel_runner_script(bucket_scripts: List[str], repo_name: str, output_dir: str) -> str:
    """
    Create a master script to run all bucket scripts in parallel.
    
    Args:
        bucket_scripts: List of paths to bucket processing scripts
        repo_name: Repository name
        output_dir: Directory to save the runner script
        
    Returns:
        Path to the runner script
    """
    runner_filename = "run_all_buckets.sh"
    runner_path = os.path.join(output_dir, runner_filename)
    
    script_names = [os.path.basename(script) for script in bucket_scripts]
    
    runner_content = f'''#!/bin/bash
# Parallel Bucket Runner for {repo_name}
# Runs all bucket processing scripts simultaneously

REPO="{repo_name}"
SCRIPTS=({' '.join(script_names)})

echo "🚀 Starting parallel processing for $REPO"
echo "📊 Running ${{#SCRIPTS[@]}} bucket scripts in parallel"
echo ""

# Start all scripts in background
PIDS=()
for SCRIPT in "${{SCRIPTS[@]}}"; do
    if [ -f "$SCRIPT" ]; then
        echo "Starting $SCRIPT..."
        ./"$SCRIPT" &
        PIDS+=($!)
    else
        echo "❌ Script not found: $SCRIPT"
    fi
done

echo ""
echo "⏳ Waiting for all buckets to complete..."
echo "   You can monitor progress in separate terminal windows"

# Wait for all background processes
for PID in "${{PIDS[@]}}"; do
    wait $PID
done

echo ""
echo "🎉 All bucket processing completed!"
echo "📁 Check .{repo_name.split('/')[1]}/ directory for results"
echo "📊 Each issue should have its own .md file"
'''
    
    with open(runner_path, 'w', encoding='utf-8') as f:
        f.write(runner_content)
    
    # Make script executable
    os.chmod(runner_path, 0o755)
    
    print(f"📜 Created parallel runner: {runner_filename}")
    return runner_path

def create_generation_report(repo_name: str, bucket_scripts: List[str], runner_script: str, issues: List[Dict[str, Any]]) -> str:
    """
    Create a report of the script generation process.
    
    Args:
        repo_name: Repository name
        bucket_scripts: List of generated bucket scripts
        runner_script: Path to runner script
        issues: List of all issues
        
    Returns:
        Path to the report file
    """
    repo_dir = repo_name.replace('/', '_')
    output_dir = os.path.join('scripts', 'bucket_harvest', 'repo_to_issues', 'data', repo_dir)
    report_path = os.path.join(output_dir, 'script_generation_report.txt')
    
    # Count issues per bucket
    bucket_counts = {}
    for issue in issues:
        bucket_id = issue['bucket_id']
        bucket_counts[bucket_id] = bucket_counts.get(bucket_id, 0) + 1
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"Bash Script Generation Report\\n")
        f.write(f"============================\\n\\n")
        f.write(f"Repository: {repo_name}\\n")
        f.write(f"Generated: {os.path.basename(__file__)} at {os.popen('date').read().strip()}\\n")
        f.write(f"Total issues: {len(issues)}\\n")
        f.write(f"Total buckets: {len(bucket_scripts)}\\n\\n")
        
        f.write(f"Generated Scripts:\\n")
        for script_path in bucket_scripts:
            script_name = os.path.basename(script_path)
            bucket_id = int(script_name.split('_')[2].split('.')[0])
            issue_count = bucket_counts.get(bucket_id, 0)
            f.write(f"  - {script_name}: {issue_count} issues\\n")
        
        f.write(f"  - {os.path.basename(runner_script)}: Master parallel runner\\n\\n")
        
        f.write(f"Execution Instructions:\\n")
        f.write(f"1. Individual bucket: ./{os.path.basename(bucket_scripts[0])}\\n")
        f.write(f"2. All buckets in parallel: ./{os.path.basename(runner_script)}\\n")
        f.write(f"3. Individual terminals: Run each process_bucket_N.sh in separate terminal\\n\\n")
        
        f.write(f"Expected Output:\\n")
        f.write(f"- Directory: .{repo_name.split('/')[1]}/\\n")
        f.write(f"- Files: {len(issues)} individual .md files (one per issue)\\n")
        f.write(f"- Format: issue_id.md (e.g., 1234.md, 5678.md)\\n")
    
    print(f"📋 Generation report saved: {os.path.basename(report_path)}")
    return report_path

def main():
    """Main entry point for the script."""
    if len(sys.argv) != 2:
        print("Usage: python generate_bucket_scripts.py <owner/repo>")
        print("Example: python generate_bucket_scripts.py facebook/react")
        sys.exit(1)
    
    repo_name = sys.argv[1]
    
    # Validate repository format
    if '/' not in repo_name:
        print("❌ Repository must be in format 'owner/repo'")
        sys.exit(1)
    
    try:
        print(f"🎯 Generating bash scripts for {repo_name}")
        print()
        
        # Load bucket CSV data
        issues = load_bucket_csv(repo_name)
        
        if not issues:
            print("No issues found in bucket CSV.")
            return
        
        # Group issues by bucket
        buckets = group_issues_by_bucket(issues)
        
        # Set up output directory
        repo_dir = repo_name.replace('/', '_')
        output_dir = os.path.join('scripts', 'bucket_harvest', 'repo_to_issues', 'data', repo_dir)
        
        print(f"\\nGenerating bash scripts in: {output_dir}")
        print()
        
        # Generate individual bucket scripts
        bucket_scripts = []
        for bucket_id in sorted(buckets.keys()):
            bucket_issues = buckets[bucket_id]
            script_path = create_bash_script(bucket_id, bucket_issues, repo_name, output_dir)
            bucket_scripts.append(script_path)
        
        # Generate parallel runner script
        runner_script = create_parallel_runner_script(bucket_scripts, repo_name, output_dir)
        
        # Create generation report
        report_path = create_generation_report(repo_name, bucket_scripts, runner_script, issues)
        
        print()
        print(f"🎉 Script generation completed successfully!")
        print(f"📁 Output directory: {output_dir}")
        print(f"📊 Generated {len(bucket_scripts)} bucket scripts + 1 runner script")
        print()
        print(f"🚀 Execution options:")
        print(f"   1. Run all in parallel: ./{os.path.basename(runner_script)}")
        print(f"   2. Run individual bucket: ./process_bucket_1.sh")
        print(f"   3. Run in separate terminals for real-time monitoring")
        print()
        print(f"📁 Expected output: .{repo_name.split('/')[1]}/ directory with .md files")
        
    except Exception as e:
        print(f"❌ Error during script generation: {str(e)}")
        raise

if __name__ == "__main__":
    main()