# BUCKET Strategy for Large Repository Issue Processing

**Version:** 1.0  
**Created:** 2025-09-06  
**Author:** Claude Code Assistant  

## Overview

The BUCKET strategy is a parallel processing approach designed to efficiently handle large numbers of GitHub issues/PRs from repositories like Google Guava, Shopify, Databricks, etc. It overcomes GitHub CLI output limits and API rate limiting through intelligent distribution and parallel processing.

## Strategy Benefits

✅ **Parallel Processing**: True concurrent execution across multiple terminal processes  
✅ **Fault Tolerance**: If one bucket fails, others continue processing  
✅ **Scalable**: Easily adjust bucket count based on repository size  
✅ **Rate Limit Friendly**: Distributes API calls across time and processes  
✅ **Resume Capability**: Failed buckets can be reprocessed individually  
✅ **Memory Efficient**: Processes data in manageable chunks  

## How It Works

### Phase 1: Bucket Creation
1. **Fetch Issue IDs**: Extract all open issue numbers, along with date_created using GitHub CLI
2. **Filter**: Filter only the 100 most recent open issues, using date_created.
3. **Generate CSV**: Create `issue_buckets.csv` with format: `issue_id; bucket_id; date_created` with bucket id being 1-10.

### Phase 2: Parallel Processing  
1. **Generate Scripts**: Create N processing scripts (`process_bucket_0.sh` through `process_bucket_N-1.sh`)
2. **Run in Parallel**: Execute all scripts simultaneously in separate terminals
3. **Individual Results**: Each script generates `.{repo}/issues_list/{issue_id}.md`

the output will include a .md with 

metadata: github url, date created, labels
main body: issue description, comment details appended below. 


## expected output

if the repo was called sdf-cli then output would be 100 issues

```
.sdf-cli/
3454.md
2343.md
2355.md
2343.md
```
---

**Note**: This strategy was successfully implemented for Google Guava repository (627 open issues) and can be adapted for any GitHub repository. Modify bucket counts and processing logic based on your specific requirements.