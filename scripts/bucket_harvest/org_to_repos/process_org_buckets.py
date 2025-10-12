#!/usr/bin/env python3
"""
Organization Repository Bucket Processor (Python-Only)
Processes organization repository buckets in parallel using Python threading.

This script replaces the bash script generation approach with direct Python processing,
eliminating dependencies on bash, jq, bc, and other Unix tools while providing
the same comprehensive repository analysis with health scoring.

Usage:
    python process_org_buckets.py <org_name> [--workers N]
    
Examples:
    python process_org_buckets.py google
    python process_org_buckets.py nvidia --workers 10
    python process_org_buckets.py microsoft --workers 3
"""

import os
import sys
import csv
import time
import requests
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import threading

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

# Thread-safe counter for progress tracking
class ProgressCounter:
    def __init__(self, total: int):
        self.total = total
        self.processed = 0
        self.failed = 0
        self.lock = threading.Lock()
    
    def increment_processed(self):
        with self.lock:
            self.processed += 1
    
    def increment_failed(self):
        with self.lock:
            self.failed += 1
    
    def get_status(self) -> Tuple[int, int, int]:
        with self.lock:
            return self.processed, self.failed, self.total


class OrganizationBucketProcessor:
    """Process organization repository buckets in parallel using Python."""
    
    def __init__(self, org_name: str, max_workers: int = 5):
        """
        Initialize the bucket processor.
        
        Args:
            org_name: Organization name
            max_workers: Maximum number of parallel workers
        """
        self.org_name = org_name.lower()
        self.max_workers = max_workers
        
        self.token = os.getenv('API_GITHUB_TOKEN')
        if not self.token:
            raise ValueError("API_GITHUB_TOKEN not found in environment variables")
        
        self.headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitHub-Library-Org-Bucket-Processor'
        }
        
        self.base_url = 'https://api.github.com'
        self.data_dir = os.path.join('scripts', 'bucket_harvest', 'org_to_repos', 'data', org_name.lower())
        
        # Rate limiting
        self.request_delay = 0.2  # Seconds between requests
        self.last_request_time = 0
        self.rate_limit_lock = threading.Lock()
        
        print(f"🎯 Organization: {org_name}")
        print(f"🧵 Max workers: {max_workers}")
        print(f"📁 Data directory: {self.data_dir}")
        print()
        
    def _make_request_with_rate_limit(self, url: str, params: Optional[Dict] = None) -> Optional[requests.Response]:
        """Make rate-limited request to GitHub API."""
        with self.rate_limit_lock:
            # Ensure minimum delay between requests
            elapsed = time.time() - self.last_request_time
            if elapsed < self.request_delay:
                time.sleep(self.request_delay - elapsed)
            
            self.last_request_time = time.time()
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=self.headers, params=params)
                
                # Handle rate limiting
                if response.status_code == 403 and 'rate limit' in response.text.lower():
                    if 'X-RateLimit-Reset' in response.headers:
                        reset_time = int(response.headers['X-RateLimit-Reset'])
                        wait_time = max(reset_time - int(time.time()), 60)
                        print(f"    ⏰ Rate limit hit. Waiting {wait_time} seconds...")
                        time.sleep(wait_time)
                    else:
                        time.sleep(60)
                    continue
                
                if response.status_code == 200:
                    return response
                elif response.status_code == 404:
                    return None  # Repository not found
                else:
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    return None
                    
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                print(f"    ❌ Request error after {max_retries} attempts: {e}")
                return None
        
        return None
    
    def load_all_buckets(self) -> List[Dict[str, Any]]:
        """Load all bucket CSV files and return combined repository list."""
        if not os.path.exists(self.data_dir):
            raise FileNotFoundError(f"Data directory not found: {self.data_dir}")
        
        print(f"📂 Loading bucket data from: {self.data_dir}")
        
        all_repos = []
        bucket_files = [f for f in os.listdir(self.data_dir) if f.startswith('org_bucket_') and f.endswith('.csv')]
        
        if not bucket_files:
            raise FileNotFoundError(f"No bucket CSV files found in {self.data_dir}")
        
        for bucket_file in sorted(bucket_files):
            bucket_path = os.path.join(self.data_dir, bucket_file)
            bucket_repos = []
            
            try:
                with open(bucket_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        bucket_repos.append({
                            'repo_name': row['repo_name'],
                            'full_name': row['full_name'],
                            'github_url': row['github_url'].strip(),
                            'stars': int(row['stars']) if row['stars'].isdigit() else 0,
                            'language': row['language'],
                            'description': row['description'],
                            'open_issues': int(row['open_issues']) if row['open_issues'].isdigit() else 0,
                            'forks': int(row['forks']) if row['forks'].isdigit() else 0,
                            'pushed_at': row['pushed_at']
                        })
                
                all_repos.extend(bucket_repos)
                print(f"  ✅ {bucket_file}: {len(bucket_repos)} repositories")
                
            except Exception as e:
                print(f"  ❌ Error loading {bucket_file}: {e}")
                continue
        
        print(f"📊 Total repositories to process: {len(all_repos)}")
        return all_repos
    
    def get_repository_metrics(self, repo: Dict[str, Any], progress: ProgressCounter) -> Dict[str, Any]:
        """
        Get detailed metrics for a single repository.
        
        Args:
            repo: Repository basic info
            progress: Progress counter for tracking
            
        Returns:
            Dictionary with complete repository metrics
        """
        repo_name = repo['repo_name']
        full_name = repo['full_name']
        
        try:
            # Get basic repository data (already have most of this, but get fresh data)
            repo_url = f"{self.base_url}/repos/{full_name}"
            repo_response = self._make_request_with_rate_limit(repo_url)
            
            if not repo_response:
                progress.increment_failed()
                return {
                    'repo': repo_name,
                    'star_count': 0,
                    'contributor_count': 0,
                    'github_url': repo['github_url'],
                    'primary_language': 'Unknown',
                    'description': 'Failed to fetch repository data',
                    'commits_last_30d': 0,
                    'closed_pr_last_30d': 0,
                    'repo_health_score': 0.0
                }
            
            repo_data = repo_response.json()
            
            # Extract basic info
            star_count = repo_data.get('stargazers_count', 0)
            primary_language = repo_data.get('language', 'Unknown') or 'Unknown'
            description = (repo_data.get('description', '') or '').replace('\n', ' ').strip()
            if not description:
                description = 'No description available'
            
            # Get contributor count (approximate using first page)
            contributors_url = f"{self.base_url}/repos/{full_name}/contributors"
            contributors_response = self._make_request_with_rate_limit(contributors_url, {'per_page': 100})
            
            if contributors_response:
                contributors = contributors_response.json()
                contributor_count = len(contributors) if isinstance(contributors, list) else 1
            else:
                contributor_count = 1
            
            # Get commits from last 30 days
            thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
            commits_url = f"{self.base_url}/repos/{full_name}/commits"
            commits_response = self._make_request_with_rate_limit(commits_url, {
                'since': thirty_days_ago,
                'per_page': 100
            })
            
            if commits_response:
                commits = commits_response.json()
                commits_last_30d = len(commits) if isinstance(commits, list) else 0
            else:
                commits_last_30d = 0
            
            # Get closed PRs from last 30 days  
            pulls_url = f"{self.base_url}/repos/{full_name}/pulls"
            pulls_response = self._make_request_with_rate_limit(pulls_url, {
                'state': 'closed',
                'since': thirty_days_ago,
                'per_page': 100
            })
            
            if pulls_response:
                pulls = pulls_response.json()
                closed_pr_last_30d = len(pulls) if isinstance(pulls, list) else 0
            else:
                closed_pr_last_30d = 0
            
            # Calculate health score
            repo_health_score = (commits_last_30d + closed_pr_last_30d) / 2.0
            
            progress.increment_processed()
            
            # Progress indicator
            processed, failed, total = progress.get_status()
            print(f"    ✅ {repo_name}: ⭐{star_count} 📝{commits_last_30d} 🔀{closed_pr_last_30d} Health:{repo_health_score:.1f} ({processed + failed}/{total})")
            
            return {
                'repo': repo_name,
                'star_count': star_count,
                'contributor_count': contributor_count,
                'github_url': repo['github_url'],
                'primary_language': primary_language,
                'description': f'"{description}"',  # Quote description for CSV safety
                'commits_last_30d': commits_last_30d,
                'closed_pr_last_30d': closed_pr_last_30d,
                'repo_health_score': repo_health_score
            }
            
        except Exception as e:
            progress.increment_failed()
            print(f"    ❌ Error processing {repo_name}: {e}")
            return {
                'repo': repo_name,
                'star_count': 0,
                'contributor_count': 0,
                'github_url': repo['github_url'],
                'primary_language': 'Unknown',
                'description': f'"Error: {str(e)}"',
                'commits_last_30d': 0,
                'closed_pr_last_30d': 0,
                'repo_health_score': 0.0
            }
    
    def process_repositories_parallel(self, repositories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process repositories in parallel using ThreadPoolExecutor."""
        print(f"🚀 Starting parallel processing with {self.max_workers} workers...")
        
        progress = ProgressCounter(len(repositories))
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all repository processing tasks
            future_to_repo = {
                executor.submit(self.get_repository_metrics, repo, progress): repo 
                for repo in repositories
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_repo):
                repo = future_to_repo[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    print(f"❌ Exception processing {repo['repo_name']}: {e}")
                    progress.increment_failed()
                    # Add fallback result
                    results.append({
                        'repo': repo['repo_name'],
                        'star_count': 0,
                        'contributor_count': 0,
                        'github_url': repo['github_url'],
                        'primary_language': 'Unknown',
                        'description': f'"Exception: {str(e)}"',
                        'commits_last_30d': 0,
                        'closed_pr_last_30d': 0,
                        'repo_health_score': 0.0
                    })
        
        # Final progress report
        processed, failed, total = progress.get_status()
        print()
        print(f"🏁 Processing completed:")
        print(f"   ✅ Processed: {processed} repositories")
        print(f"   ❌ Failed: {failed} repositories") 
        print(f"   📊 Success rate: {processed/total*100:.1f}%")
        
        return results
    
    def save_results(self, results: List[Dict[str, Any]]) -> str:
        """Save results to CSV file, sorted by health score."""
        output_filename = f".{self.org_name}_analysis.csv"
        output_path = os.path.join(self.data_dir, output_filename)
        
        print(f"💾 Saving results to: {output_path}")
        
        # Sort by health score (descending)
        sorted_results = sorted(results, key=lambda x: x['repo_health_score'], reverse=True)
        
        fieldnames = [
            'repo', 'star_count', 'contributor_count', 'github_url', 
            'primary_language', 'description', 'commits_last_30d', 
            'closed_pr_last_30d', 'repo_health_score'
        ]
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(sorted_results)
        
        print(f"📊 Saved {len(sorted_results)} repositories to CSV")
        
        # Show top repositories by health score
        if sorted_results:
            print(f"\n🏆 Top 5 repositories by health score:")
            for i, repo in enumerate(sorted_results[:5], 1):
                health = repo['repo_health_score']
                stars = repo['star_count']
                commits = repo['commits_last_30d']
                prs = repo['closed_pr_last_30d']
                print(f"  {i}. {repo['repo']} (Health: {health}, ⭐{stars}, 📝{commits}, 🔀{prs})")
        
        return output_path
    
    def create_processing_report(self, results: List[Dict[str, Any]], processing_time: float) -> str:
        """Create a processing report with statistics."""
        report_filename = "processing_report.txt"
        report_path = os.path.join(self.data_dir, report_filename)
        
        # Calculate statistics
        total_repos = len(results)
        successful_repos = len([r for r in results if r['repo_health_score'] > 0 or r['star_count'] > 0])
        failed_repos = total_repos - successful_repos
        
        total_stars = sum(r['star_count'] for r in results)
        total_commits = sum(r['commits_last_30d'] for r in results)
        total_prs = sum(r['closed_pr_last_30d'] for r in results)
        
        avg_health_score = sum(r['repo_health_score'] for r in results) / total_repos if total_repos > 0 else 0
        
        # Language distribution
        languages = {}
        for repo in results:
            lang = repo['primary_language']
            languages[lang] = languages.get(lang, 0) + 1
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"{self.org_name.title()} Organization Analysis Report\\n")
            f.write(f"{'=' * (len(self.org_name) + 30)}\\n\\n")
            
            f.write(f"Processing Details:\\n")
            f.write(f"- Processed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n")
            f.write(f"- Organization: {self.org_name}\\n")
            f.write(f"- Processing time: {processing_time:.2f} seconds\\n")
            f.write(f"- Max workers: {self.max_workers}\\n\\n")
            
            f.write(f"Repository Statistics:\\n")
            f.write(f"- Total repositories: {total_repos}\\n")
            f.write(f"- Successfully processed: {successful_repos}\\n")
            f.write(f"- Failed to process: {failed_repos}\\n")
            f.write(f"- Success rate: {successful_repos/total_repos*100:.1f}%\\n\\n")
            
            f.write(f"Metrics Summary:\\n")
            f.write(f"- Total stars: {total_stars:,}\\n")
            f.write(f"- Total commits (30d): {total_commits:,}\\n")
            f.write(f"- Total closed PRs (30d): {total_prs:,}\\n")
            f.write(f"- Average health score: {avg_health_score:.2f}\\n\\n")
            
            f.write(f"Top Programming Languages:\\n")
            sorted_langs = sorted(languages.items(), key=lambda x: x[1], reverse=True)[:10]
            for lang, count in sorted_langs:
                percentage = count / total_repos * 100
                f.write(f"  • {lang}: {count} repos ({percentage:.1f}%)\\n")
            
            f.write(f"\\nTop 10 Repositories by Health Score:\\n")
            for i, repo in enumerate(sorted(results, key=lambda x: x['repo_health_score'], reverse=True)[:10], 1):
                f.write(f"  {i:2d}. {repo['repo']} (Health: {repo['repo_health_score']:.1f}, Stars: {repo['star_count']:,})\\n")
        
        print(f"📋 Processing report saved: {os.path.basename(report_path)}")
        return report_path
    
    def run(self):
        """Main execution method."""
        print(f"{self.org_name.title()} Repository Analysis")
        print(f"{'=' * (len(self.org_name) + 20)}")
        print()
        
        start_time = time.time()
        
        try:
            # Load all repository data from buckets
            repositories = self.load_all_buckets()
            
            if not repositories:
                print("❌ No repositories found in buckets!")
                return
            
            # Process repositories in parallel
            results = self.process_repositories_parallel(repositories)
            
            # Save results
            output_path = self.save_results(results)
            
            # Create processing report
            processing_time = time.time() - start_time
            report_path = self.create_processing_report(results, processing_time)
            
            print()
            print(f"🎉 Analysis completed successfully!")
            print(f"⏱️  Total time: {processing_time:.2f} seconds")
            print(f"📁 Results: {os.path.basename(output_path)}")
            print(f"📋 Report: {os.path.basename(report_path)}")
            print()
            
        except KeyboardInterrupt:
            print("\\n⏹️  Processing interrupted by user.")
        except Exception as e:
            print(f"❌ Error during processing: {e}")
            raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Process organization repository buckets in parallel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python process_org_buckets.py google
  python process_org_buckets.py nvidia --workers 10
  python process_org_buckets.py microsoft --workers 3
  
Note: Run create_org_buckets.py first to generate the bucket data.
        """
    )
    
    parser.add_argument(
        'org_name',
        help='Organization name (must match create_org_buckets.py output)'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=5,
        help='Number of parallel workers (default: 5)'
    )
    
    args = parser.parse_args()
    
    if not args.org_name or not args.org_name.strip():
        print("❌ Organization name cannot be empty")
        sys.exit(1)
    
    if args.workers < 1:
        print("❌ Number of workers must be at least 1")
        sys.exit(1)
    
    if args.workers > 20:
        print("⚠️  Warning: Using more than 20 workers may hit rate limits")
        print("   Consider using fewer workers to avoid GitHub API limits")
    
    try:
        processor = OrganizationBucketProcessor(args.org_name.strip(), args.workers)
        processor.run()
    except Exception as e:
        print(f"❌ Failed to process repositories: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()