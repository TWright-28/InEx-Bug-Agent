"""
Convert your 21K classification results to the format merge_classifications expects
"""

import json

def convert_classification_format(input_file, output_file="results_21k_converted.jsonl"):
    """
    Convert your classification format to our results format
    
    Input format:  {project, issue_number, predicted_label, ...}
    Output format: {repo, number, classification, ...}
    """
    print(f"Converting {input_file}...")
    
    converted = 0
    
    with open(input_file, 'r', encoding='utf-8') as f_in:
        with open(output_file, 'w', encoding='utf-8') as f_out:
            for line in f_in:
                if not line.strip():
                    continue
                
                original = json.loads(line)
                
                # Map predicted_label to classification
                predicted = original.get('predicted_label', 'Unknown')
                
                if predicted == 'Not a Bug':
                    classification = 'NOT_A_BUG'
                elif predicted == 'Intrinsic':
                    classification = 'INTRINSIC'
                elif predicted == 'Extrinsic':
                    classification = 'EXTRINSIC'
                else:
                    classification = 'UNKNOWN'
                
                # Create new format
                converted_result = {
                    'timestamp': original.get('timestamp', ''),
                    'repo': original.get('project', ''),
                    'number': original.get('issue_number', 0),
                    'title': original.get('title', ''),
                    'url': original.get('html_url', ''),
                    'state': 'unknown',
                    'classification': classification,
                    'reasoning': original.get('reasoning', ''),
                    'probabilities': original.get('probabilities', {}),
                    'raw_response': original.get('full_response', '')
                }
                
                f_out.write(json.dumps(converted_result, ensure_ascii=False) + '\n')
                converted += 1
                
                if converted % 1000 == 0:
                    print(f"  Converted {converted}...")
    
    print(f"✓ Converted {converted} classifications")
    print(f"✓ Saved to: {output_file}")
    
    return output_file

if __name__ == "__main__":
    convert_classification_format('classified_23k_bugs.jsonl')