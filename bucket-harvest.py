#!/usr/bin/env python3
"""
Cross-platform wrapper for bucket harvest script.
Usage: python bucket-harvest.py <owner/repo>
Example: python bucket-harvest.py google/guava
"""
import sys
import subprocess
import os

def main():
    if len(sys.argv) < 2:
        print("Usage: python bucket-harvest.py <owner/repo>")
        print("Example: python bucket-harvest.py google/guava")
        sys.exit(1)
    
    script_path = os.path.join("scripts", "bucket_harvest", "repo_to_issues", "collect_recent_issues.py")
    
    if not os.path.exists(script_path):
        print(f"Error: Could not find {script_path}")
        sys.exit(1)
    
    # Run the actual script with all arguments passed through
    subprocess.run([sys.executable, script_path] + sys.argv[1:])

if __name__ == "__main__":
    main()