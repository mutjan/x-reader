# Testing Patterns

**Analysis Date:** 2026-03-31

## Test Framework

**Runner:**
- Not detected (no pytest/unittest/other testing framework configured)
- Config: Not applicable

**Assertion Library:**
- Not detected, uses print statements for manual verification

**Run Commands:**
```bash
python scripts/test_*.py              # Run individual ad-hoc test scripts
```

## Test File Organization

**Location:**
- Ad-hoc test scripts located in `scripts/` directory, co-located with other utility scripts

**Naming:**
- Test files follow `test_*.py` pattern
- Example: `scripts/test_classification.py`

**Structure:**
```
project-root/
├── scripts/
│   └── test_*.py          # Ad-hoc test scripts
```

## Test Structure

**Suite Organization:**
- No formal test suites observed
- Test scripts are standalone, focused on specific verification tasks
- Example pattern:
  ```python
  #!/usr/bin/env python3
  """
  Verify classification fix effect
  """
  import json
  from src.models.news import ProcessedNewsItem

  # Load test data
  with open('data.json', 'r', encoding='utf-8') as f:
      test_data = json.load(f)

  # Run tests
  for item in test_data:
      # Perform assertions/verifications
      result = process_item(item)
      print(f"Test result: {result}")
  ```

**Patterns:**
- Setup: Load test data at script start
- Teardown: No teardown required for simple scripts
- Assertion: Manual verification via print statements and visual inspection

## Mocking

**Framework:** Not detected

**Patterns:**
- No formal mocking observed
- Test data loaded from JSON files or created inline

**What to Mock:**
- Not defined

**What NOT to Mock:**
- Not defined

## Fixtures and Factories

**Test Data:**
- Test data loaded from local JSON files or created inline in test scripts
- Example:
  ```python
  item = ProcessedNewsItem(
      id=f"test_{i}",
      original_title=result.get("chinese_title", ""),
      source="Test",
      url=f"https://example.com/{i}",
      published_at=datetime.now()
  )
  ```

**Location:**
- Test data stored in root directory or same directory as test scripts

## Coverage

**Requirements:** None enforced
**View Coverage:** Not applicable (no coverage tool configured)

## Test Types

**Unit Tests:**
- Not implemented, only ad-hoc verification scripts exist

**Integration Tests:**
- Not implemented

**E2E Tests:**
- Not used

## Common Patterns

**Async Testing:**
- Not applicable (no async code observed)

**Error Testing:**
- Not implemented

---

*Testing analysis: 2026-03-31*
