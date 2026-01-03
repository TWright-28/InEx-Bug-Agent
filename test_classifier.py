from tools.classifier import BugClassifier

# Create classifier
classifier = BugClassifier()

# Test with a sample issue
test_issue = {
    'number': 12345,
    'title': 'App crashes after Node.js upgrade to v20',
    'body': 'After upgrading from Node 18 to 20, the application crashes with module resolution errors.',
    'state': 'open',
    'url': 'https://github.com/test/repo/issues/12345'
}

# Classify it
result = classifier.classify(test_issue)

print(f"\nClassification: {result['classification']}")
print(f"Reasoning: {result['reasoning']}")