#!/usr/bin/env python3
"""
Organization Repository Bucket Creator (Generic)
Discovers active repositories for any GitHub organization and splits them into buckets for parallel processing.

This script consolidates the functionality from individual org-specific scripts into a reusable tool
that works with any GitHub organization (google, nvidia, microsoft, shopify, etc.).

Usage:
    python create_org_buckets.py <org_name> [--buckets N] [--days N]
    
Examples:
    python create_org_buckets.py google
    python create_org_buckets.py nvidia --buckets 20 --days 60
    python create_org_buckets.py microsoft --buckets 5 --days 14
"""

import os
import sys
import csv
import time
import requests
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dotenv import load_dotenv
import math

# Load environment variables
load_dotenv()

# Fix Windows console encoding for emoji support
if sys.platform == 'win32':
    import io
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    else:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    else:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


class OrganizationBucketCreator:
    """Create buckets of active organization repositories for parallel processing."""
    
    def __init__(self, org_name: str, days_back: int = 30, num_buckets: int = 10):
        """
        Initialize the bucket creator.
        
        Args:
            org_name: GitHub organization name
            days_back: Number of days back to consider for "active" repositories
            num_buckets: Number of buckets to create
        """
        self.org_name = org_name.lower()
        self.days_back = days_back
        self.num_buckets = num_buckets
        
        self.token = os.getenv('API_GITHUB_TOKEN')
        if not self.token:
            raise ValueError("API_GITHUB_TOKEN not found in environment variables")
        
        self.headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitHub-Library-Org-Bucket-Creator'
        }
        
        self.base_url = 'https://api.github.com'
        self.cutoff_date = datetime.now() - timedelta(days=days_back)
        
        # Output directory
        self.output_dir = os.path.join('scripts', 'bucket_harvest', 'org_to_repos', 'data', org_name.lower())
        os.makedirs(self.output_dir, exist_ok=True)
        
        print(f"🎯 Organization: {org_name}")
        print(f"📅 Activity cutoff: {self.cutoff_date.strftime('%Y-%m-%d')} ({days_back} days ago)")
        print(f"🗂️  Target buckets: {num_buckets}")
        print(f"📁 Output directory: {self.output_dir}")
        print()
        
    def _make_request(self, url: str, params: Optional[Dict] = None) -> Optional[requests.Response]:
        """Make authenticated request with rate limiting and error handling."""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                response = requests.get(url, headers=self.headers, params=params)
                
                # Handle rate limiting
                if response.status_code == 403 and 'rate limit' in response.text.lower():
                    if 'X-RateLimit-Reset' in response.headers:
                        reset_time = int(response.headers['X-RateLimit-Reset'])
                        wait_time = max(reset_time - int(time.time()), 60)
                        print(f"    ⏰ Rate limit hit. Waiting {wait_time} seconds until {datetime.fromtimestamp(reset_time).strftime('%H:%M:%S')}...")
                        time.sleep(wait_time)
                    else:
                        print(f"    ⏰ Rate limit hit. Waiting 60 seconds...")
                        time.sleep(60)
                    
                    retry_count += 1
                    continue
                
                if response.status_code == 200:
                    return response
                elif response.status_code == 404:
                    print(f"    ❌ Organization '{self.org_name}' not found (404)")
                    return None
                else:
                    print(f"    ❌ API request failed: {response.status_code} for {url}")
                    if retry_count < max_retries - 1:
                        print(f"    🔄 Retrying in 5 seconds... (attempt {retry_count + 2}/{max_retries})")
                        time.sleep(5)
                        retry_count += 1
                        continue
                    return None
                    
            except requests.exceptions.RequestException as e:
                if retry_count < max_retries - 1:
                    print(f"    🔄 Request error: {e}. Retrying in 5 seconds...")
                    time.sleep(5)
                    retry_count += 1
                    continue
                else:
                    print(f"    ❌ Request error after {max_retries} attempts: {e}")
                    return None
        
        return None
    
    def get_all_repositories(self) -> List[Dict]:
        """Get all repositories for the organization with batch processing."""
        print(f"📡 Fetching all repositories for {self.org_name}...")
        
        all_repos = []
        page = 1
        per_page = 100
        
        while True:
            print(f"  📄 Fetching page {page}...")
            
            url = f"{self.base_url}/orgs/{self.org_name}/repos"
            params = {
                'page': page,
                'per_page': per_page,
                'sort': 'pushed',
                'direction': 'desc'
            }
            
            response = self._make_request(url, params)
            if not response:
                print(f"    ❌ Failed to fetch page {page}")
                break
            
            repos = response.json()
            if not repos:
                print(f"    ✅ No more repositories (page {page} empty)")
                break
                
            all_repos.extend(repos)
            print(f"    ✅ Page {page}: {len(repos)} repositories (total: {len(all_repos)})")
            
            if len(repos) < per_page:
                print(f"    🏁 Reached end of repositories (got {len(repos)} < {per_page})")
                break
                
            page += 1
            
            # Add delay to respect rate limits
            time.sleep(0.5)
        
        print(f"📊 Total repositories found: {len(all_repos)}")
        return all_repos
    
    def filter_active_repositories(self, repos: List[Dict]) -> List[Dict]:
        """Filter repositories to only include those with recent activity."""
        print(f"🔍 Filtering for active repositories (pushed within last {self.days_back} days)...")
        
        active_repos = []
        
        for repo in repos:
            # Skip if archived or disabled
            if repo.get('archived', False) or repo.get('disabled', False):
                continue
                
            pushed_at = repo.get('pushed_at')
            if not pushed_at:
                continue
                
            try:
                # Parse the pushed_at date
                pushed_date = datetime.fromisoformat(pushed_at.replace('Z', '+00:00'))
                if pushed_date.replace(tzinfo=None) >= self.cutoff_date:
                    active_repos.append({
                        'name': repo['name'],
                        'full_name': repo['full_name'],
                        'pushed_at': pushed_at,
                        'github_url': repo['html_url'],
                        'stars': repo.get('stargazers_count', 0),
                        'language': repo.get('language', ''),
                        'description': (repo.get('description', '') or '').replace('\n', ' ').strip(),
                        'open_issues': repo.get('open_issues_count', 0),
                        'forks': repo.get('forks_count', 0)
                    })
            except (ValueError, TypeError) as e:
                print(f"    ⚠️  Could not parse date for {repo['name']}: {e}")
                continue
        
        # Sort by most recent activity first
        active_repos.sort(key=lambda x: x['pushed_at'], reverse=True)
        
        print(f"✅ Active repositories: {len(active_repos)} out of {len(repos)}")
        if active_repos:
            newest_push = active_repos[0]['pushed_at'][:10]
            oldest_push = active_repos[-1]['pushed_at'][:10]
            print(f"    📅 Activity range: {oldest_push} to {newest_push}")
        
        return active_repos
    
    def create_buckets(self, repos: List[Dict]):
        """Split repositories into buckets and create CSV files."""
        if not repos:
            print("❌ No repositories to bucket!")
            return
        
        print(f"🗂️  Creating {self.num_buckets} buckets from {len(repos)} active repositories...")
        
        # Calculate bucket size
        bucket_size = math.ceil(len(repos) / self.num_buckets)
        
        created_buckets = 0
        for i in range(self.num_buckets):
            bucket_num = i + 1
            start_idx = i * bucket_size
            end_idx = min(start_idx + bucket_size, len(repos))
            
            bucket_repos = repos[start_idx:end_idx]
            
            if not bucket_repos:
                continue
            
            # Create bucket CSV file
            bucket_filename = f"org_bucket_{bucket_num}.csv"
            bucket_filepath = os.path.join(self.output_dir, bucket_filename)
            
            with open(bucket_filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    'repo_name', 'full_name', 'github_url', 'stars', 
                    'language', 'description', 'open_issues', 'forks', 'pushed_at'
                ])
                
                for repo in bucket_repos:
                    writer.writerow([
                        repo['name'],
                        repo['full_name'], 
                        f"{repo['github_url']}   ",  # Add spaces for clickability
                        repo['stars'],
                        repo['language'],
                        repo['description'],
                        repo['open_issues'],
                        repo['forks'],
                        repo['pushed_at']
                    ])
            
            print(f"  ✅ Bucket {bucket_num}: {len(bucket_repos)} repos → {bucket_filename}")
            created_buckets += 1
        
        print(f"📁 All {created_buckets} buckets created in: {self.output_dir}")
        
        # Create summary file
        self._create_summary_report(repos, created_buckets, bucket_size)
        
    def _create_summary_report(self, repos: List[Dict], created_buckets: int, bucket_size: int):
        """Create a summary report of the bucket creation process."""
        summary_file = os.path.join(self.output_dir, "org_bucket_summary.txt")
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(f"{self.org_name.title()} Organization Repository Buckets\n")
            f.write(f"{'=' * (len(self.org_name) + 35)}\n\n")
            f.write(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Organization: {self.org_name}\n")
            f.write(f"Activity cutoff: {self.cutoff_date.strftime('%Y-%m-%d')} ({self.days_back} days ago)\n")
            f.write(f"Total active repositories: {len(repos)}\n")
            f.write(f"Number of buckets: {created_buckets}\n")
            f.write(f"Average bucket size: ~{bucket_size} repos each\n\n")
            
            if repos:
                # Calculate some statistics
                total_stars = sum(repo['stars'] for repo in repos)
                avg_stars = total_stars / len(repos)
                languages = {}
                for repo in repos:
                    lang = repo['language'] or 'Unknown'
                    languages[lang] = languages.get(lang, 0) + 1
                
                f.write(f"Repository Statistics:\n")
                f.write(f"- Total stars across all repos: {total_stars:,}\n")
                f.write(f"- Average stars per repo: {avg_stars:.1f}\n")
                f.write(f"- Most common languages:\n")
                
                sorted_langs = sorted(languages.items(), key=lambda x: x[1], reverse=True)[:5]
                for lang, count in sorted_langs:
                    f.write(f"  • {lang}: {count} repos\n")
                f.write(f"\n")
            
            f.write(f"Bucket files created:\n")
            for i in range(created_buckets):
                bucket_filename = f"org_bucket_{i+1}.csv"
                start_idx = i * bucket_size
                end_idx = min(start_idx + bucket_size, len(repos))
                bucket_count = end_idx - start_idx
                if bucket_count > 0:
                    f.write(f"  • {bucket_filename}: {bucket_count} repositories\n")
            
            f.write(f"\nNext Steps:\n")
            f.write(f"1. Run generate_org_scripts.py {self.org_name} to create processing scripts\n")
            f.write(f"2. Execute the generated bash scripts to collect detailed metrics\n")
            f.write(f"3. Find final analysis in .{self.org_name}_analysis.csv\n")
        
        print(f"📋 Summary report saved: {os.path.basename(summary_file)}")
    
    def run(self):
        """Main execution method."""
        print(f"{self.org_name.title()} Repository Bucket Creator")
        print(f"{'=' * (len(self.org_name) + 25)}")
        print()
        
        try:
            # Step 1: Get all repositories
            all_repos = self.get_all_repositories()
            if not all_repos:
                print("❌ No repositories found!")
                return
            
            # Step 2: Filter for recent activity
            active_repos = self.filter_active_repositories(all_repos)
            if not active_repos:
                print("❌ No repositories with recent activity found!")
                print(f"💡 Try increasing --days parameter (current: {self.days_back})")
                return
            
            # Step 3: Create buckets
            self.create_buckets(active_repos)
            
            print()
            print(f"🎉 SUCCESS: Buckets created successfully!")
            print(f"📁 Output: {self.output_dir}")
            print(f"🚀 Next: python generate_org_scripts.py {self.org_name}")
            print()
            
        except KeyboardInterrupt:
            print("\n⏹️  Operation interrupted by user.")
        except Exception as e:
            print(f"❌ Error during bucket creation: {e}")
            raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create repository buckets for any GitHub organization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python create_org_buckets.py google
  python create_org_buckets.py nvidia --buckets 20 --days 60  
  python create_org_buckets.py microsoft --buckets 5 --days 14
  
Supported organizations: google, nvidia, microsoft, shopify, databricks, etc.
        """
    )
    
    parser.add_argument(
        'org_name', 
        help='GitHub organization name (e.g., google, nvidia, microsoft)'
    )
    parser.add_argument(
        '--buckets', 
        type=int, 
        default=10,
        help='Number of buckets to create (default: 10)'
    )
    parser.add_argument(
        '--days', 
        type=int, 
        default=30,
        help='Days back to consider for active repositories (default: 30)'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.buckets < 1:
        print("❌ Number of buckets must be at least 1")
        sys.exit(1)
    
    if args.days < 1:
        print("❌ Days back must be at least 1")
        sys.exit(1)
    
    if not args.org_name or not args.org_name.strip():
        print("❌ Organization name cannot be empty")
        sys.exit(1)
    
    try:
        creator = OrganizationBucketCreator(args.org_name.strip(), args.days, args.buckets)
        creator.run()
    except Exception as e:
        print(f"❌ Failed to create buckets: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()