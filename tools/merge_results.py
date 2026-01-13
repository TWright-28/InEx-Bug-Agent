import json

def merge_classifications(collected_file, results_file, output_file):
    
    print(f"Loading collected data from {collected_file}...")
    collected = {}
    with open(collected_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                issue = json.loads(line)
                key = (issue['owner'], issue['repo'], issue['number'])
                collected[key] = issue
    
    print(f"  Loaded {len(collected)} issues")
    
    print(f"Loading classifications from {results_file}...")
    classifications = {}
    with open(results_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                result = json.loads(line)
                repo_parts = result['repo'].split('/')
                if len(repo_parts) == 2:
                    owner, repo = repo_parts
                    key = (owner, repo, result['number'])
                    classifications[key] = result
    
    print(f"  Loaded {len(classifications)} classifications")
    
    print(f"Merging...")
    merged_count = 0
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for key, issue in collected.items():
            if key in classifications:

                result = classifications[key]
                
                classification = result['classification']
                if classification == 'NOT_A_BUG':
                    final_class = 'Not  a Bug'  #convert to match data
                else:
                    final_class = classification.capitalize()
                
                issue['final_classification'] = final_class
                issue['classification'] = result['classification']
                issue['classification_reasoning'] = result.get('reasoning', '')
                issue['classification_probabilities'] = result.get('probabilities', {})
                issue['classification_raw_response'] = result.get('raw_response', '')
                issue['classification_timestamp'] = result.get('timestamp', '')
                issue['classification_url'] = result.get('url', '') 
                
                merged_count += 1
            else:
                issue['final_classification'] = 'Unknown'
                issue['classification'] = 'UNKNOWN'
                issue['classification_reasoning'] = 'Not classified'
                issue['classification_probabilities'] = {}
                issue['classification_raw_response'] = ''
                issue['classification_timestamp'] = ''
                issue['classification_url'] = ''
            
            f.write(json.dumps(issue, ensure_ascii=False) + '\n')
    
    print(f" Merged {merged_count}/{len(collected)} issues")
    print(f" Saved to: {output_file}")
    
    return merged_count

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 4:
        print("Usage: python merge_results.py <collected.jsonl> <results.jsonl> <output.jsonl>")
        sys.exit(1)
    
    merge_classifications(sys.argv[1], sys.argv[2], sys.argv[3])