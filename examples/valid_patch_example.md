# Valid APOS Patch Example

The extension pairs the first `apos-patch` block with the immediately following source code block.

```apos-patch
{
  "patch_id": "patch-valid-python-001",
  "project_root": "C:/Users/DO/Desktop/test-project",
  "target": "workspace/active_code.py",
  "language": "python",
  "sha256": "96e6925e27d3a5750df8e9498ba8152c6c9992d8b25a9eafaef23d352717b028"
}
```

```python
def main():
    print("APOS test")


if __name__ == "__main__":
    main()
```
