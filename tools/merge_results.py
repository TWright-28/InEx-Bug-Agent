import json

def merge_classifications(collected_file, results_file, output_file):
    
    # Load collected data
    print(f"Loading collected data from {collected_file}...")
    collected = {}
    with open(collected_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                issue = json.loads(line)
                key = (issue['owner'], issue['repo'], issue['number'])
                collected[key] = issue
    
    print(f"  Loaded {len(collected)} issues")
    
    # Load classification results
    print(f"Loading classifications from {results_file}...")
    classifications = {}
    with open(results_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                result = json.loads(line)
                # Parse repo into owner/repo
                repo_parts = result['repo'].split('/')
                if len(repo_parts) == 2:
                    owner, repo = repo_parts
                    key = (owner, repo, result['number'])
                    classifications[key] = result
    
    print(f"  Loaded {len(classifications)} classifications")
    
    # Merge classifications into collected data
    print(f"Merging...")
    merged_count = 0
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for key, issue in collected.items():
            if key in classifications:
                # Get classification result
                result = classifications[key]
                
                # Map classification to analysis script format
                classification = result['classification']
                if classification == 'NOT_A_BUG':
                    final_class = 'Not  a Bug'  # Two spaces to match analysis script
                else:
                    final_class = classification.capitalize()
                
                # Add ALL classification fields to issue
                issue['final_classification'] = final_class
                issue['classification'] = result['classification']  # Original format (INTRINSIC, etc.)
                issue['classification_reasoning'] = result.get('reasoning', '')
                issue['classification_probabilities'] = result.get('probabilities', {})
                issue['classification_raw_response'] = result.get('raw_response', '')
                issue['classification_timestamp'] = result.get('timestamp', '')
                issue['classification_url'] = result.get('url', '')  # From results if present
                
                merged_count += 1
            else:
                # No classification found - mark as Unknown
                issue['final_classification'] = 'Unknown'
                issue['classification'] = 'UNKNOWN'
                issue['classification_reasoning'] = 'Not classified'
                issue['classification_probabilities'] = {}
                issue['classification_raw_response'] = ''
                issue['classification_timestamp'] = ''
                issue['classification_url'] = ''
            
            # Write to output
            f.write(json.dumps(issue, ensure_ascii=False) + '\n')
    
    print(f" Merged {merged_count}/{len(collected)} issues")
    print(f" Saved to: {output_file}")
    
    return merged_count

if __name__ == "__main__":
    # Example usage
    import sys
    if len(sys.argv) != 4:
        print("Usage: python merge_results.py <collected.jsonl> <results.jsonl> <output.jsonl>")
        sys.exit(1)
    
    merge_classifications(sys.argv[1], sys.argv[2], sys.argv[3])